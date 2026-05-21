type RequestLike = {
  headers: Headers;
  url?: string;
  nextUrl?: {
    host: string;
    protocol: string;
    pathname: string;
    search: string;
  };
};

const HOST_RE = /^(?:localhost|\[[0-9a-fA-F:.]+\]|[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)(?::[0-9]{1,5})?$/;

function firstHeaderValue(value: string | null): string | null {
  const first = value?.split(",", 1)[0]?.trim();
  return first || null;
}

function safeHost(value: string | null): string | null {
  if (!value) return null;
  if (!HOST_RE.test(value)) return null;
  const port = value.match(/:(\d{1,5})$/)?.[1];
  if (port && Number(port) > 65535) return null;
  return value;
}

function safeProto(value: string | null): "http" | "https" | null {
  const proto = value?.replace(/:$/, "").trim().toLowerCase();
  return proto === "http" || proto === "https" ? proto : null;
}

function configuredPublicOrigin(): string | null {
  const raw = process.env.PLATO_PUBLIC_ORIGIN?.trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return url.origin;
  } catch {
    return null;
  }
}

export function publicHost(request: RequestLike): string {
  return (
    safeHost(firstHeaderValue(request.headers.get("host"))) ??
    safeHost(firstHeaderValue(request.headers.get("x-forwarded-host"))) ??
    request.nextUrl?.host ??
    (request.url ? new URL(request.url).host : "localhost")
  );
}

export function publicOrigin(request: RequestLike): string {
  const configured = configuredPublicOrigin();
  if (configured) return configured;

  const host = publicHost(request);
  return `${publicProto(request)}://${host}`;
}

export function publicProto(request: RequestLike): "http" | "https" {
  const host = publicHost(request);
  const fallbackProto = request.nextUrl?.protocol ?? (request.url ? new URL(request.url).protocol : null);
  return (
    safeProto(firstHeaderValue(request.headers.get("x-forwarded-proto"))) ??
    safeProto(fallbackProto) ??
    (host.includes("localhost") ? "http" : "https")
  );
}

export function publicRequestUrl(request: RequestLike): string {
  const pathname = request.nextUrl?.pathname ?? (request.url ? new URL(request.url).pathname : "/");
  const search = request.nextUrl?.search ?? (request.url ? new URL(request.url).search : "");
  return `${publicOrigin(request)}${pathname}${search}`;
}
