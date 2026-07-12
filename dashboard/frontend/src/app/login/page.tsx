import { LoginPageClient } from "./login-client";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { isClerkAuthEnabled } from "@/lib/auth-mode";

type LoginPageProps = {
  searchParams?: Promise<{
    next?: string | string[];
  }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = (await searchParams) ?? {};
  const next = Array.isArray(params.next) ? params.next[0] : params.next;
  const redirectTo = safeRedirectPath(next);

  if (isClerkAuthEnabled()) {
    const session = await auth();
    if (session.userId) {
      redirect(redirectTo);
    }
  }

  return <LoginPageClient redirectTo={redirectTo} />;
}

function safeRedirectPath(next: string | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) {
    return "/";
  }

  if (isAuthSurfacePath(next)) {
    return "/";
  }

  return next;
}

function isAuthSurfacePath(path: string): boolean {
  return (
    path === "/login" ||
    path.startsWith("/login?") ||
    path.startsWith("/login/") ||
    path === "/sign-in" ||
    path.startsWith("/sign-in?") ||
    path.startsWith("/sign-in/") ||
    path === "/sign-up" ||
    path.startsWith("/sign-up?") ||
    path.startsWith("/sign-up/")
  );
}
