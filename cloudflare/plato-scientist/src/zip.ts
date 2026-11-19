/**
 * Read single entries of a zip stored in R2 without loading the archive: the central
 * directory is read with ranged gets, then the one entry is inflated (deflate-raw).
 */

export interface ZipEntry {
  name: string;
  method: number;
  compressedSize: number;
  size: number;
  offset: number;
}

const u16 = (b: Uint8Array, o: number) => b[o] | (b[o + 1] << 8);
const u32 = (b: Uint8Array, o: number) => (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;

async function range(bucket: R2Bucket, key: string, offset: number, length: number): Promise<Uint8Array> {
  const obj = await bucket.get(key, { range: { offset, length } });
  if (!obj) throw new Error("zip object missing");
  return new Uint8Array(await obj.arrayBuffer());
}

export async function entries(bucket: R2Bucket, key: string, size: number): Promise<ZipEntry[]> {
  const tailLen = Math.min(size, 65_557); // EOCD (22) + max comment (65535)
  const tail = await range(bucket, key, size - tailLen, tailLen);
  let eocd = -1;
  for (let i = tail.length - 22; i >= 0; i--) {
    if (u32(tail, i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error("not a zip file");
  const cdSize = u32(tail, eocd + 12);
  const cdOffset = u32(tail, eocd + 16);
  const cd = await range(bucket, key, cdOffset, cdSize);
  const out: ZipEntry[] = [];
  const dec = new TextDecoder();
  for (let p = 0; p + 46 <= cd.length && u32(cd, p) === 0x02014b50; ) {
    const nameLen = u16(cd, p + 28);
    const extraLen = u16(cd, p + 30);
    const commentLen = u16(cd, p + 32);
    out.push({
      method: u16(cd, p + 10),
      compressedSize: u32(cd, p + 20),
      size: u32(cd, p + 24),
      offset: u32(cd, p + 42),
      name: dec.decode(cd.subarray(p + 46, p + 46 + nameLen)),
    });
    p += 46 + nameLen + extraLen + commentLen;
  }
  return out;
}

export async function readEntry(bucket: R2Bucket, key: string, e: ZipEntry): Promise<Uint8Array> {
  const header = await range(bucket, key, e.offset, 30);
  if (u32(header, 0) !== 0x04034b50) throw new Error("bad local header");
  const start = e.offset + 30 + u16(header, 26) + u16(header, 28);
  const raw = await range(bucket, key, start, e.compressedSize);
  if (e.method === 0) return raw;
  if (e.method !== 8) throw new Error(`unsupported zip method ${e.method}`);
  const stream = new Blob([raw]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  const out = new Uint8Array(await new Response(stream).arrayBuffer());
  if (out.byteLength !== e.size) throw new Error("zip entry size mismatch");
  return out;
}
