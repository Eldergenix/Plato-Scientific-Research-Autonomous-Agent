"use client";

/**
 * Client island for /settings/executors.
 *
 * Owns: executor-list fetch, user-preference fetch, default-toggle
 * mutation, in-flight pending state, and the toast that surfaces
 * success / failure of a "Set as default" click. The page.tsx wrapper
 * is a Server Component so it can export `metadata` and emit a static
 * header without paying the JS-bundle cost for static chrome.
 *
 * Data-fetching stays on the client because the existing Playwright
 * tests stub the backend with `page.route()`, which only intercepts
 * browser-side requests. Moving the fetch into the RSC would make the
 * mocks a no-op and break every settings test.
 */

import * as React from "react";
import {
  ExecutorSelector,
  type ExecutorInfo,
} from "@/components/executors/executor-selector";
import { ExecutorCard } from "@/components/executors/executor-card";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

interface ExecutorListResponse {
  executors: ExecutorInfo[];
  default: string;
}

interface ExecutorPreferenceResponse {
  default_executor: string | null;
}

type FetchState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; executors: ExecutorInfo[]; defaultName: string };

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export function ExecutorsClient() {
  const [state, setState] = React.useState<FetchState>({ kind: "loading" });
  const [selected, setSelected] = React.useState<string>("");
  const [pending, setPending] = React.useState(false);
  const [savedMsg, setSavedMsg] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [list, prefs] = await Promise.all([
          fetchJson<ExecutorListResponse>("/executors"),
          fetchJson<ExecutorPreferenceResponse>(
            "/user/executor_preferences",
          ).catch(() => ({ default_executor: null })),
        ]);
        if (cancelled) return;
        const fallback = list.default || list.executors[0]?.name || "";
        const initialDefault = prefs.default_executor ?? fallback;
        setState({
          kind: "ready",
          executors: list.executors,
          defaultName: initialDefault,
        });
        setSelected(initialDefault);
      } catch (err) {
        if (cancelled) return;
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Failed to load",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setAsDefault = async (name: string) => {
    setPending(true);
    setSavedMsg(null);
    try {
      await fetchJson<ExecutorPreferenceResponse>(
        "/user/executor_preferences",
        {
          method: "PUT",
          body: JSON.stringify({ default_executor: name }),
        },
      );
      setState((prev) =>
        prev.kind === "ready" ? { ...prev, defaultName: name } : prev,
      );
      setSavedMsg(`Default executor set to ${name}.`);
    } catch (err) {
      setSavedMsg(
        err instanceof Error ? err.message : "Failed to update preference.",
      );
    } finally {
      setPending(false);
    }
  };

  const selectedExec =
    state.kind === "ready"
      ? state.executors.find((e) => e.name === selected)
      : undefined;
  const defaultName = state.kind === "ready" ? state.defaultName : "";

  if (state.kind === "loading") {
    return (
      <div
        className="surface-linear-card p-5 text-[13px] text-(--color-text-tertiary)"
        data-testid="executors-loading"
      >
        Loading executors…
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div
        className="surface-linear-card p-5 text-[13px] text-(--color-status-red)"
        data-testid="executors-error"
      >
        {state.message}
      </div>
    );
  }

  return (
    <>
      <section className="surface-linear-card p-5">
        <SectionTitle
          title="Active selection"
          subtitle="Choose an executor to inspect, then set it as your default."
        />
        <div className="mt-3 flex flex-col gap-2">
          <ExecutorSelector
            value={selected}
            onChange={setSelected}
            executors={state.executors}
          />
        </div>
      </section>

      {selectedExec ? (
        <ExecutorCard
          executor={selectedExec}
          isDefault={selectedExec.name === defaultName}
          pending={pending}
          onSetDefault={() => setAsDefault(selectedExec.name)}
        />
      ) : null}

      {savedMsg ? (
        <div
          className="text-[12px] text-(--color-text-tertiary)"
          data-testid="executors-saved-msg"
        >
          {savedMsg}
        </div>
      ) : null}
    </>
  );
}

function SectionTitle({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <div>
      <h2 className="text-[15px] font-[510] tracking-[-0.2px] text-(--color-text-primary-strong)">
        {title}
      </h2>
      {subtitle ? (
        <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}
