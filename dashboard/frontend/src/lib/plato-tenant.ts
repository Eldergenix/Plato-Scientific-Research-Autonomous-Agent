const TENANT_SAFE_RE = /^[A-Za-z0-9._-]{1,64}$/;

function hashTenant(raw: string): string {
  let hash = 0;
  for (let i = 0; i < raw.length; i += 1) {
    hash = (Math.imul(31, hash) + raw.charCodeAt(i)) | 0;
  }
  return Math.abs(hash).toString(36).padStart(7, "0").slice(0, 7);
}

export function toPlatoTenantId(kind: "lab" | "user", id: string): string {
  const raw = `${kind}_${id}`;
  const cleaned = raw
    .replace(/[^A-Za-z0-9._-]/g, "_")
    .replace(/^\.+/, "")
    .replace(/\.+$/, "");
  const bounded =
    cleaned.length <= 64 ? cleaned : `${cleaned.slice(0, 56)}_${hashTenant(cleaned)}`;
  return TENANT_SAFE_RE.test(bounded) ? bounded : `${kind}_${hashTenant(raw)}`;
}
