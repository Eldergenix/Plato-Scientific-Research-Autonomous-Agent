import { LoginPageClient } from "./login-client";

type LoginPageProps = {
  searchParams?: Promise<{
    next?: string | string[];
  }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = (await searchParams) ?? {};
  const next = Array.isArray(params.next) ? params.next[0] : params.next;

  return <LoginPageClient redirectTo={safeRedirectPath(next)} />;
}

function safeRedirectPath(next: string | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) {
    return "/";
  }

  if (next === "/login" || next.startsWith("/login?")) {
    return "/";
  }

  return next;
}
