"use client";

/**
 * Client island for /settings/licenses.
 *
 * Holds every piece of state and side-effect from the original
 * single-file page so the page.tsx wrapper can stay an RSC and export
 * its own ``metadata`` for the browser tab + share buttons.
 *
 * The data-fetching stays on the client (mocked by Playwright via
 * ``page.route``) — moving it server-side would break the existing
 * e2e mocks because Playwright can't intercept Next.js's RSC fetch.
 */

import * as React from "react";
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

export function LicensesClient() {
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

  if (loading) {
    return (
      <p
        className="surface-linear-card p-5 text-[13px] text-(--color-text-row-meta)"
        data-testid="licenses-loading"
      >
        Loading license audit…
      </p>
    );
  }

  if (error) {
    return (
      <p
        className="surface-linear-card p-5 text-[13px] text-(--color-status-red-spec)"
        data-testid="licenses-error"
      >
        {error}
      </p>
    );
  }

  return (
    <>
      {audit ? (
        <>
          <LicenseStats summary={audit.summary} />
          <LicenseTable distributions={audit.distributions} />
        </>
      ) : null}
      <SbomSummary />
    </>
  );
}
