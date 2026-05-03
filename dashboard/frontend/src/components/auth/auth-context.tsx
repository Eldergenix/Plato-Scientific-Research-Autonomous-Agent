"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { setActiveUserId } from "@/lib/api";

/**
 * Auth context for the dashboard's tenant-id login flow.
 *
 * The cookie set by ``POST /api/v1/auth/login`` is the source of truth on
 * the server. ``user_id`` in localStorage is a redundant client-side hint
 * — useful so the UI can paint the right user-menu state before the
 * ``/me`` round-trip resolves on cold load. It is not consulted on the
 * server.
 *
 * The integration commit will mount ``<AuthProvider>`` in
 * ``app/layout.tsx``. We deliberately do not wire it here so this stream
 * stays isolated; tests can render under the provider directly.
 */

const AUTH_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

const STORAGE_KEY = "plato:user_id";

export interface AuthState {
  user_id: string | null;
  authRequired: boolean;
  loading: boolean;
}

export interface AuthContextValue extends AuthState {
  login: (id: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

function readPersisted(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v && v.length > 0 ? v : null;
  } catch {
    return null;
  }
}

function writePersisted(id: string | null): void {
  // Mirror the persisted hint into the api.ts module-level store so
  // every fetchJson call carries X-Plato-User. The api.ts bootstrap
  // already seeds itself from localStorage on cold load; this keeps
  // the two stores in sync after login/logout/refresh.
  setActiveUserId(id);
  if (typeof window === "undefined") return;
  try {
    if (id === null) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore — private mode, quota, etc. */
  }
}

async function fetchMe(): Promise<{ user_id: string | null; auth_required: boolean }> {
  // Wrap fetch itself in try/catch — when the user is offline, fetch()
  // throws TypeError("Failed to fetch") rather than resolving to a
  // non-ok response. Without this guard the rejection bubbles up to
  // the void-awaited refresh() in useEffect and silently leaves the
  // auth provider's `loading` flag stuck on true forever, blocking
  // every auth-gated UI.
  let r: Response;
  try {
    r = await fetch(`${AUTH_BASE}/auth/me`, {
      method: "GET",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return { user_id: null, auth_required: false };
  }
  if (!r.ok) {
    // Treat any failure as "not signed in, auth not required" — the UI
    // still loads, the user can sign in if they want.
    return { user_id: null, auth_required: false };
  }
  return (await r.json()) as { user_id: string | null; auth_required: boolean };
}

async function postLogin(id: string): Promise<{ user_id: string }> {
  const r = await fetch(`${AUTH_BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: id }),
  });
  if (!r.ok) {
    let detail: unknown;
    try {
      detail = await r.json();
    } catch {
      detail = await r.text();
    }
    const msg =
      typeof detail === "object" && detail && "detail" in detail
        ? JSON.stringify((detail as { detail: unknown }).detail)
        : String(detail);
    throw new Error(`Login failed (${r.status}): ${msg}`);
  }
  return (await r.json()) as { user_id: string };
}

async function postLogout(): Promise<void> {
  await fetch(`${AUTH_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  });
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Seed from localStorage so the first paint already shows the right
  // avatar; ``loading`` stays true until ``/me`` confirms.
  const [user_id, setUserId] = React.useState<string | null>(() => readPersisted());
  const [authRequired, setAuthRequired] = React.useState<boolean>(false);
  const [loading, setLoading] = React.useState<boolean>(true);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    const me = await fetchMe();
    setUserId(me.user_id);
    setAuthRequired(me.auth_required);
    writePersisted(me.user_id);
    setLoading(false);
  }, []);

  const login = React.useCallback(async (id: string) => {
    const trimmed = id.trim();
    if (!trimmed) throw new Error("user_id must be a non-empty string");
    const res = await postLogin(trimmed);
    setUserId(res.user_id);
    writePersisted(res.user_id);
  }, []);

  const logout = React.useCallback(async () => {
    await postLogout();
    setUserId(null);
    writePersisted(null);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  // Client-side guard: when the backend reports auth_required and no
  // user is signed in, send the user to /login. We intentionally
  // skip this when we're already on /login (avoids a redirect loop)
  // and while the initial /me probe is still in flight (avoids a
  // flash-redirect from the localStorage-seeded null state).
  const router = useRouter();
  const pathname = usePathname() ?? "";
  React.useEffect(() => {
    if (loading) return;
    if (!authRequired) return;
    if (user_id) return;
    if (pathname.startsWith("/login")) return;
    router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [authRequired, loading, pathname, router, user_id]);

  const value: AuthContextValue = React.useMemo(
    () => ({ user_id, authRequired, loading, login, logout, refresh }),
    [user_id, authRequired, loading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside an <AuthProvider>");
  }
  return ctx;
}
