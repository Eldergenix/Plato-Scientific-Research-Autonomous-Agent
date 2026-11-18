// The one node:crypto API the Worker uses (MD5 for Composio's upload request; Web Crypto
// has no MD5). Provided at runtime by the nodejs_compat flag.
declare module "node:crypto" {
  interface Hash {
    update(data: Uint8Array | string): Hash;
    digest(encoding: "hex"): string;
  }
  export function createHash(algorithm: "md5" | "sha256"): Hash;
}
