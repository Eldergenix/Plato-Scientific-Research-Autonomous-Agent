"use client";

/**
 * Client island for /settings/domains.
 *
 * Owns: domain-list fetch, user-preference fetch, optimistic
 * default-toggle mutation with rollback on failure, and the
 * autohide toast that surfaces success / failure of the toggle.
 *
 * The page.tsx wrapper is a Server Component so it can export its own
 * `metadata` and emit the static breadcrumb / page header on the
 * server. Data-fetching stays on the client so the existing Playwright
 * `page.route` mocks keep working — Next.js dev-server fetches happen
 * outside the browser and would silently bypass the test mocks if we
 * moved them to the RSC.
 */

import * as React from "react";
import { Loader2, AlertCircle } from "lucide-react";
import {
  DomainSelector,
  type DomainProfileLite,
} from "@/components/domain/domain-selector";
import {
  DomainProfileCard,
  type DomainProfileFull,
} from "@/components/domain/domain-profile-card";
import { cn } from "@/lib/utils";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

interface DomainsResponse {
  domains: DomainProfileFull[];
  default: string;
}

interface PreferencesResponse {
  default_domain: string | null;
  default_executor: string | null;
}

export function DomainsClient() {
  const [domains, setDomains] = React.useState<DomainProfileFull[]>([]);
  const [globalDefault, setGlobalDefault] = React.useState<string | null>(null);
  const [userDefault, setUserDefault] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [toast, setToast] = React.useState<{
    kind: "ok" | "err";
    message: string;
  } | null>(null);
  const toastTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [domainsRes, prefsRes] = await Promise.all([
          fetch(`${API_BASE}/domains`).then((r) => {
            if (!r.ok) throw new Error(`/domains ${r.status}`);
            return r.json() as Promise<DomainsResponse>;
          }),
          fetch(`${API_BASE}/user/preferences`).then((r) => {
            if (!r.ok) throw new Error(`/user/preferences ${r.status}`);
            return r.json() as Promise<PreferencesResponse>;
          }),
        ]);
        if (cancelled) return;
        setDomains(domainsRes.domains);
        setGlobalDefault(domainsRes.default);
        setUserDefault(prefsRes.default_domain);
        setSelected(
          prefsRes.default_domain ??
            domainsRes.default ??
            domainsRes.domains[0]?.name ??
            null,
        );
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load domains");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  const showToast = React.useCallback(
    (kind: "ok" | "err", message: string) => {
      setToast({ kind, message });
      if (toastTimer.current) clearTimeout(toastTimer.current);
      toastTimer.current = setTimeout(() => setToast(null), 2800);
    },
    [],
  );

  const onSetDefault = React.useCallback(
    async (name: string) => {
      // Optimistic — flip the pill immediately, roll back on failure.
      const prev = userDefault;
      setUserDefault(name);
      setSaving(true);
      try {
        const r = await fetch(`${API_BASE}/user/preferences`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ default_domain: name }),
        });
        if (!r.ok) {
          const detail = await r.text();
          throw new Error(detail || `PUT ${r.status}`);
        }
        const body = (await r.json()) as PreferencesResponse;
        setUserDefault(body.default_domain);
        showToast("ok", `${name} set as default.`);
      } catch (err) {
        setUserDefault(prev);
        showToast(
          "err",
          err instanceof Error ? err.message : "Failed to update default",
        );
      } finally {
        setSaving(false);
      }
    },
    [userDefault, showToast],
  );

  const liteDomains: DomainProfileLite[] = React.useMemo(
    () =>
      domains.map((d) => ({
        name: d.name,
        retrieval_sources: d.retrieval_sources,
        executor: d.executor,
      })),
    [domains],
  );

  const selectedProfile = React.useMemo(
    () => domains.find((d) => d.name === selected) ?? null,
    [domains, selected],
  );

  return (
    <>
      <section className="surface-linear-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-[15px] font-[510] tracking-[-0.2px] text-(--color-text-primary-strong)">
              Active profile
            </h2>
            <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
              Switching here previews a profile below — it doesn&apos;t change
              your default until you click &ldquo;Set as default&rdquo;.
            </p>
          </div>
          <div className="w-full sm:w-[260px]">
            <DomainSelector
              value={selected}
              onChange={setSelected}
              domains={liteDomains}
              disabled={loading || domains.length === 0}
            />
          </div>
        </div>
        {globalDefault ? (
          <p className="mt-3 text-[11.5px] text-(--color-text-tertiary)">
            Global default:{" "}
            <code className="font-mono text-[11px]">{globalDefault}</code>
            {userDefault ? (
              <>
                {" "}
                · Your default:{" "}
                <code className="font-mono text-[11px]">{userDefault}</code>
              </>
            ) : null}
          </p>
        ) : null}
      </section>

      {loading ? (
        <div
          className="surface-linear-card flex items-center gap-2 p-5 text-[13px] text-(--color-text-tertiary)"
          data-testid="domains-loading"
        >
          <Loader2 size={14} strokeWidth={1.75} className="animate-spin" />
          Loading domain profiles…
        </div>
      ) : error ? (
        <div
          className="surface-linear-card flex items-start gap-2 p-5 text-[13px] text-(--color-status-red)"
          data-testid="domains-error"
          style={{ borderColor: "rgba(235, 87, 87, 0.3)" }}
        >
          <AlertCircle size={14} strokeWidth={1.75} className="mt-0.5" />
          <span>Failed to load: {error}</span>
        </div>
      ) : selectedProfile ? (
        <DomainProfileCard
          profile={selectedProfile}
          isDefault={userDefault === selectedProfile.name}
          saving={saving}
          onSetDefault={() => onSetDefault(selectedProfile.name)}
        />
      ) : (
        <div className="surface-linear-card p-5 text-[13px] text-(--color-text-tertiary)">
          No domains registered.
        </div>
      )}

      {toast ? (
        <div
          role="status"
          data-testid="domains-toast"
          className={cn(
            "fixed bottom-6 left-1/2 -translate-x-1/2 rounded-[8px] border px-3 py-2 text-[12.5px] shadow-[var(--shadow-dialog)]",
            toast.kind === "ok"
              ? "border-(--color-status-emerald)/30 bg-(--color-status-emerald)/12 text-(--color-status-emerald)"
              : "border-(--color-status-red)/30 bg-(--color-status-red)/12 text-(--color-status-red)",
          )}
        >
          {toast.message}
        </div>
      ) : null}
    </>
  );
}
