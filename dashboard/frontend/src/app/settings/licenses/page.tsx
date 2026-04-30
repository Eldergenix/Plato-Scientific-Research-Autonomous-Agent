"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import {
  LicenseStats,
  type LicenseSummary,
} from "@/components/license/license-stats";
import {
  LicenseTable,
  type LicenseDistribution,
} from "@/components/license/license-table";
import { SbomSummary } from "@/components/license/sbom-summary";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

interface LicenseAuditPayload {
  summary: LicenseSummary;
  by_license: { license: string; count: number; gpl3_compatible: boolean }[];
  distributions: LicenseDistribution[];
}

async function fetchAudit(): Promise<LicenseAuditPayload> {
  const r = await fetch(`${API_BASE}/license_audit`, {
    headers: { Accept: "application/json" },
  });
  if (!r.ok) {
    let msg = `License audit unavailable (HTTP ${r.status})`;
    try {
      const body = await r.json();
      const detail = (body as { detail?: { error?: string } })?.detail;
      if (detail?.error) msg = detail.error;
    } catch {
      /* fall through to status-code message */
    }
    throw new Error(msg);
  }
  return (await r.json()) as LicenseAuditPayload;
}

export default function LicensesSettingsPage() {
  const [audit, setAudit] = React.useState<LicenseAuditPayload | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    fetchAudit()
      .then((data) => {
        if (cancelled) return;
        setAudit(data);
        setError(null);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-(--color-bg-page) px-6 py-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header
          className="surface-linear-card p-5"
          data-testid="licenses-page-header"
        >
          <nav
            aria-label="Breadcrumb"
            className="mb-2 flex items-center gap-1 text-[12px] text-(--color-text-tertiary)"
          >
            <Link
              href="/settings"
              className="hover:text-(--color-text-primary) hover:underline"
            >
              Settings
            </Link>
            <ChevronRight size={12} strokeWidth={1.75} />
            <span className="text-(--color-text-primary)">Licenses & SBOM</span>
          </nav>
          <h1 className="text-[20px] font-[510] tracking-[-0.3px] text-(--color-text-primary-strong)">
            Licenses & SBOM
          </h1>
          <p className="mt-1 text-[13px] text-(--color-text-tertiary-spec)">
            GPLv3 compatibility audit for every installed Python distribution,
            plus the CycloneDX SBOM the CI pipeline ships.
          </p>
        </header>

        {loading ? (
          <p
            className="surface-linear-card p-5 text-[13px] text-(--color-text-row-meta)"
            data-testid="licenses-loading"
          >
            Loading license audit…
          </p>
        ) : error ? (
          <p
            className="surface-linear-card p-5 text-[13px] text-(--color-status-red-spec)"
            data-testid="licenses-error"
          >
            {error}
          </p>
        ) : audit ? (
          <>
            <LicenseStats summary={audit.summary} />
            <LicenseTable distributions={audit.distributions} />
          </>
        ) : null}

        <SbomSummary />
      </div>
    </div>
  );
}
