/**
 * A person's research files: uploads, imports from connected services, email attachments
 * and exported publication packages. Bytes live in R2 (`EXPORTS` bucket, `library/` prefix);
 * Postgres keeps the index. Files feed new research threads: data files become datasets,
 * reference files (.bib, .ris, .nbib) become citable papers, documents (PDF, Word, ...)
 * become background the agents read.
 */
import type { Ctx } from "./auth";
import { b64, type Env, hex, HttpError, json, type Sql, sha256 } from "./lib";

export const MAX_FILE_BYTES = 25 * 1024 * 1024;
/** What one research thread may take from the library (the create request carries it as base64). */
export const MAX_CAMPAIGN_MATERIAL_BYTES = 16 * 1024 * 1024;
export const MAX_CAMPAIGN_FILES = 16;

export type Kind = "data" | "reference" | "document" | "image" | "archive" | "other";
export type Source = "upload" | "googledrive" | "dropbox" | "one_drive" | "gmail" | "outlook" | "export";

const KINDS: Record<string, Kind> = {};
for (const e of "csv tsv tab xlsx xls ods json jsonl ndjson parquet feather arrow vcf bcf bed bedgraph gff gff3 gtf fasta fa fna faa fastq fq sam bam h5 hdf5 h5ad loom nc npy npz mat sav dta rds rdata sqlite db mzml mzxml pdb cif sdf mol2 xyz dat".split(" "))
  KINDS[e] = "data";
for (const e of "bib bibtex ris nbib medline enw".split(" ")) KINDS[e] = "reference";
for (const e of "pdf docx doc odt rtf html htm md markdown tex txt epub pptx".split(" ")) KINDS[e] = "document";
for (const e of "png jpg jpeg tif tiff gif svg webp".split(" ")) KINDS[e] = "image";
for (const e of "zip tar gz tgz bz2 xz 7z".split(" ")) KINDS[e] = "archive";

export function extension(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".vcf.gz")) return "vcf";
  if (lower.endsWith(".fastq.gz") || lower.endsWith(".fq.gz")) return "fastq";
  const i = lower.lastIndexOf(".");
  return i > 0 ? lower.slice(i + 1) : "";
}

export function kindOf(name: string): Kind {
  return KINDS[extension(name)] ?? "other";
}

const TYPES: Record<string, string> = {
  csv: "text/csv", tsv: "text/tab-separated-values", json: "application/json", pdf: "application/pdf",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  zip: "application/zip", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", txt: "text/plain",
  md: "text/markdown", tex: "application/x-tex", bib: "application/x-bibtex", vcf: "text/vcard",
  ris: "application/x-research-info-systems", html: "text/html", xml: "application/xml",
};

export function mediaType(name: string, given?: string | null): string {
  // VCF here means Variant Call Format, not vCard: never trust the extension's MIME default for it.
  if (extension(name) === "vcf") return "text/x-vcf";
  const g = (given ?? "").split(";")[0].trim().toLowerCase();
  if (g && g !== "application/octet-stream" && /^[a-z0-9.+-]+\/[a-z0-9.+-]+$/.test(g)) return g;
  return TYPES[extension(name)] ?? "application/octet-stream";
}

/** A file name safe for the index, a zip and every OS: no paths, no control characters. */
export function safeName(name: string): string {
  const base = name.replace(/\\/g, "/").split("/").pop() ?? "";
  const clean = base.replace(/[\u0000-\u001f\u007f<>:"|?*]/g, "_").replace(/^\.+/, "").trim();
  return (clean || "file").slice(0, 200);
}

export interface Stored {
  id: string;
  name: string;
  kind: Kind;
  bytes: number;
  sha256: string;
  duplicate: boolean;
}

/** Save bytes to R2 and the index. Idempotent per external file (source, sourceRef). */
export async function store(
  env: Env,
  sql: Sql,
  accountId: string,
  name: string,
  data: Uint8Array,
  source: Source,
  opts: { sourceRef?: string | null; mediaType?: string | null; meta?: Record<string, unknown> } = {},
): Promise<Stored> {
  if (data.byteLength > MAX_FILE_BYTES) throw new HttpError(413, `${name} is larger than 25 MiB`);
  const clean = safeName(name);
  const ref = opts.sourceRef ?? null;
  if (ref) {
    const [dup] = await sql`
      SELECT id, name, kind, bytes, sha256 FROM plato.library_files
       WHERE account_id = ${accountId} AND source = ${source} AND source_ref = ${ref}`;
    if (dup) return { ...(dup as unknown as Stored), bytes: Number(dup.bytes), duplicate: true };
  }
  const digest = hex(await sha256(data));
  const id = crypto.randomUUID();
  const key = `library/${accountId}/${id}`;
  const type = mediaType(clean, opts.mediaType);
  await env.EXPORTS.put(key, data, {
    httpMetadata: { contentType: type },
    sha256: digest,
    customMetadata: { account: accountId, name: clean },
  });
  const kind = kindOf(clean);
  const rows = await sql`
    INSERT INTO plato.library_files (id, account_id, name, media_type, kind, bytes, sha256, source, source_ref, r2_key, meta)
    VALUES (${id}, ${accountId}, ${clean}, ${type}, ${kind}, ${data.byteLength}, ${digest}, ${source}, ${ref}, ${key},
            ${sql.json((opts.meta ?? {}) as never)})
    ON CONFLICT (account_id, source, source_ref) WHERE source_ref IS NOT NULL DO NOTHING
    RETURNING id`;
  if (rows.length === 0) {
    // A concurrent import of the same external file won the race: keep theirs.
    await env.EXPORTS.delete(key);
    const [dup] = await sql`
      SELECT id, name, kind, bytes, sha256 FROM plato.library_files
       WHERE account_id = ${accountId} AND source = ${source} AND source_ref = ${ref}`;
    return { ...(dup as unknown as Stored), bytes: Number(dup.bytes), duplicate: true };
  }
  return { id, name: clean, kind, bytes: data.byteLength, sha256: digest, duplicate: false };
}

async function owned(c: Ctx, id: string) {
  const [row] = await c.sql`
    SELECT id, account_id, name, media_type, kind, bytes, sha256, r2_key FROM plato.library_files WHERE id = ${id}`;
  if (!row || row.account_id !== c.who!.accountId) throw new HttpError(404, "file not found");
  return row;
}

export async function listFiles(c: Ctx): Promise<Response> {
  const rows = await c.sql`
    SELECT id, name, media_type, kind, bytes, sha256, source, meta, created_at
      FROM plato.library_files WHERE account_id = ${c.who!.accountId}
     ORDER BY created_at DESC LIMIT 500`;
  return json({ files: rows, limits: { file_bytes: MAX_FILE_BYTES, thread_bytes: MAX_CAMPAIGN_MATERIAL_BYTES } });
}

/** Upload: the raw file is the body; its name is in ``x-file-name`` (URI-encoded). */
export async function uploadFile(c: Ctx): Promise<Response> {
  const length = Number(c.req.headers.get("content-length") ?? NaN);
  if (!Number.isFinite(length)) throw new HttpError(411, "content-length required");
  if (length > MAX_FILE_BYTES) throw new HttpError(413, "files are limited to 25 MiB");
  let name = "";
  try {
    name = decodeURIComponent(c.req.headers.get("x-file-name") ?? "");
  } catch {
    throw new HttpError(400, "invalid file name");
  }
  if (!name.trim()) throw new HttpError(400, "x-file-name is required");
  const data = new Uint8Array(await c.req.arrayBuffer());
  if (data.byteLength !== length) throw new HttpError(400, "incomplete upload");
  const out = await store(c.env, c.sql, c.who!.accountId!, name, data, "upload", {
    mediaType: c.req.headers.get("content-type"),
  });
  return json(out, 201);
}

export async function downloadFile(c: Ctx, id: string): Promise<Response> {
  const row = await owned(c, id);
  const obj = await c.env.EXPORTS.get(row.r2_key as string);
  if (!obj) throw new HttpError(404, "file not found");
  return new Response(obj.body, {
    headers: {
      "content-type": "application/octet-stream", // never render user files inline on our origin
      "content-disposition": `attachment; filename*=UTF-8''${encodeURIComponent(row.name as string)}`,
      "content-length": String(obj.size),
      "x-content-type-options": "nosniff",
      "cache-control": "private, no-store",
    },
  });
}

export async function deleteFile(c: Ctx, id: string): Promise<Response> {
  const row = await owned(c, id);
  await c.sql`DELETE FROM plato.library_files WHERE id = ${id}`;
  await c.env.EXPORTS.delete(row.r2_key as string);
  return json({ deleted: id });
}

/** The library files a new research thread was given, as the container's create fields. */
export async function campaignInputs(env: Env, sql: Sql, accountId: string, ids: string[]) {
  if (ids.length > MAX_CAMPAIGN_FILES) throw new HttpError(400, `at most ${MAX_CAMPAIGN_FILES} files per thread`);
  const ids_ = `{${ids.join(",")}}`;
  const rows = await sql`
    SELECT id, name, kind, bytes, r2_key FROM plato.library_files
     WHERE account_id = ${accountId} AND id = ANY(${ids_}::uuid[])`;
  if (rows.length !== ids.length) throw new HttpError(404, "a selected file was not found");
  const total = rows.reduce((n, r) => n + Number(r.bytes), 0);
  if (total > MAX_CAMPAIGN_MATERIAL_BYTES) {
    throw new HttpError(413, "the selected files exceed 16 MiB; pick fewer or smaller files");
  }
  const datasets: { file_name: string; content_base64: string; description: string }[] = [];
  const materials: { file_name: string; kind: "reference" | "document"; content_base64: string }[] = [];
  const used = new Set<string>();
  for (const r of rows) {
    const kind = r.kind as Kind;
    if (kind === "archive" || kind === "other") {
      throw new HttpError(422, `${r.name}: unpack archives and pick the files inside`);
    }
    const obj = await env.EXPORTS.get(r.r2_key as string);
    if (!obj) throw new HttpError(404, `${r.name} is missing from storage`);
    const content = b64(new Uint8Array(await obj.arrayBuffer()));
    if (kind === "reference" || kind === "document") {
      materials.push({ file_name: datasetName(r.name as string, used, true), kind, content_base64: content });
    } else {
      datasets.push({ file_name: datasetName(r.name as string, used, false), content_base64: content, description: `${r.name} (from the library)` });
    }
  }
  return { datasets, materials };
}

/** File names the container accepts (``^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$``), unique per thread. */
function datasetName(name: string, used: Set<string>, spaces: boolean): string {
  let base = name.replace(spaces ? /[^A-Za-z0-9._ ()-]+/g : /[^A-Za-z0-9._-]+/g, "_").replace(/^[^A-Za-z0-9]+/, "");
  if (!base) base = "file";
  base = base.slice(0, 120);
  let out = base;
  for (let i = 2; used.has(out.toLowerCase()); i++) out = `${i}_${base}`.slice(0, 128);
  used.add(out.toLowerCase());
  return out;
}
