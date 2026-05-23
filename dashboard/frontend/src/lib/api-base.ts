export function dashboardApiBase(): string {
  if (process.env.NEXT_PUBLIC_PLATO_AUTH_PROVIDER === "clerk") {
    return "/api/v1";
  }
  return process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1";
}
