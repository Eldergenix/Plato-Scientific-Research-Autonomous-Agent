"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronLeft, Loader2, AlertCircle } from "lucide-react";
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

export default function DomainsSettingsPage() {
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
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <header className="surface-linear-card p-5">
          <Link
            href="/settings"
            className="inline-flex items-center gap-1 text-[12px] text-(--color-text-tertiary-spec) hover:text-(--color-text-primary)"
          >
            <ChevronLeft size={12} strokeWidth={1.75} />
            Settings
          </Link>
          <h1 className="mt-2 text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
            Domains
          </h1>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            Pick the DomainProfile that retrieval, drafting, and execution will
            consult by default. Each profile bundles its own retrieval
            adapters, keyword extractor, journal presets, executor, and novelty
            corpus.
          </p>
        </header>

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
      </div>

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
    </div>
  );
}
