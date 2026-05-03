"use client";

/**
 * Client island for /settings/run-presets.
 *
 * Owns: preset list fetch, form state for create/edit, confirm-delete,
 * inline error/success toast, and the parallel /domains + /executors
 * fetches needed to populate the dropdowns.
 *
 * Run-start integration is intentionally deferred — see the TODO at the
 * bottom of this file. Today the page is read/edit only; wiring a
 * preset_id into the run-start payload is tracked separately so this
 * change can land without touching the workspace flow.
 */

import * as React from "react";
import { Loader2, Pencil, Plus, Trash2, X, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:7878/api/v1";

const JOURNAL_OPTIONS = [
  "NONE",
  "AAS",
  "APS",
  "ICML",
  "JHEP",
  "NeurIPS",
  "PASJ",
] as const;

interface RunPresetConfig {
  idea_iters?: number;
  max_revision_iters?: number;
  journal?: string;
  domain?: string;
  executor?: string;
  [key: string]: unknown;
}

interface RunPreset {
  id: string;
  name: string;
  created_at: string;
  config: RunPresetConfig;
}

interface DomainProfile {
  name: string;
  journal_presets?: string[];
}

interface DomainsResponse {
  domains: DomainProfile[];
  default: string;
}

interface ExecutorInfo {
  name: string;
}

interface ExecutorsResponse {
  executors: ExecutorInfo[];
  default: string;
}

interface FormState {
  name: string;
  domain: string;
  journal: string;
  idea_iters: string;
  max_revision_iters: string;
  executor: string;
}

const EMPTY_FORM: FormState = {
  name: "",
  domain: "",
  journal: "NONE",
  idea_iters: "3",
  max_revision_iters: "2",
  executor: "",
};

function presetToForm(p: RunPreset): FormState {
  return {
    name: p.name,
    domain: typeof p.config.domain === "string" ? p.config.domain : "",
    journal:
      typeof p.config.journal === "string" ? p.config.journal : "NONE",
    idea_iters:
      typeof p.config.idea_iters === "number"
        ? String(p.config.idea_iters)
        : "3",
    max_revision_iters:
      typeof p.config.max_revision_iters === "number"
        ? String(p.config.max_revision_iters)
        : "2",
    executor: typeof p.config.executor === "string" ? p.config.executor : "",
  };
}

function formToConfig(f: FormState): RunPresetConfig {
  const ideaIters = Number.parseInt(f.idea_iters, 10);
  const revIters = Number.parseInt(f.max_revision_iters, 10);
  return {
    idea_iters: Number.isFinite(ideaIters) ? ideaIters : 3,
    max_revision_iters: Number.isFinite(revIters) ? revIters : 2,
    journal: f.journal,
    ...(f.domain ? { domain: f.domain } : {}),
    ...(f.executor ? { executor: f.executor } : {}),
  };
}

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
    let detail = `HTTP ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: { message?: string } };
      if (body?.detail?.message) detail = body.detail.message;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export function RunPresetsClient() {
  const [presets, setPresets] = React.useState<RunPreset[]>([]);
  const [domains, setDomains] = React.useState<DomainProfile[]>([]);
  const [executors, setExecutors] = React.useState<ExecutorInfo[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [showForm, setShowForm] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<FormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [toast, setToast] = React.useState<string | null>(null);
  const toastTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = React.useCallback(async () => {
    const list = await fetchJson<RunPreset[]>("/run-presets");
    setPresets(list);
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        const [list, domainsRes, executorsRes] = await Promise.all([
          fetchJson<RunPreset[]>("/run-presets"),
          fetchJson<DomainsResponse>("/domains").catch(
            () => ({ domains: [], default: "" }) satisfies DomainsResponse,
          ),
          fetchJson<ExecutorsResponse>("/executors").catch(
            () => ({ executors: [], default: "" }) satisfies ExecutorsResponse,
          ),
        ]);
        if (cancelled) return;
        setPresets(list);
        setDomains(domainsRes.domains);
        setExecutors(executorsRes.executors);
      } catch (err) {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  const showToast = React.useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2800);
  }, []);

  const openNewForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setShowForm(true);
  };

  const openEditForm = (p: RunPreset) => {
    setEditingId(p.id);
    setForm(presetToForm(p));
    setFormError(null);
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  };

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setFormError("Name is required.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const payload = { name: form.name.trim(), config: formToConfig(form) };
      if (editingId) {
        await fetchJson<RunPreset>(`/run-presets/${editingId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        showToast(`Updated ${payload.name}.`);
      } else {
        await fetchJson<RunPreset>("/run-presets", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        showToast(`Created ${payload.name}.`);
      }
      await refresh();
      closeForm();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSubmitting(false);
    }
  };

  const onDelete = async (p: RunPreset) => {
    const ok = window.confirm(
      `Delete preset "${p.name}"? This cannot be undone.`,
    );
    if (!ok) return;
    try {
      await fetchJson<void>(`/run-presets/${p.id}`, { method: "DELETE" });
      await refresh();
      showToast(`Deleted ${p.name}.`);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  if (loading) {
    return (
      <div
        className="surface-linear-card flex items-center gap-2 p-5 text-[13px] text-(--color-text-tertiary)"
        data-testid="run-presets-loading"
      >
        <Loader2 size={14} strokeWidth={1.75} className="animate-spin" />
        Loading run presets…
      </div>
    );
  }

  if (loadError) {
    return (
      <div
        className="surface-linear-card flex items-start gap-2 p-5 text-[13px] text-(--color-status-red)"
        data-testid="run-presets-error"
        style={{ borderColor: "rgba(235, 87, 87, 0.3)" }}
      >
        <AlertCircle size={14} strokeWidth={1.75} className="mt-0.5" />
        <span>Failed to load: {loadError}</span>
      </div>
    );
  }

  return (
    <>
      <section className="surface-linear-card p-5">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-[15px] font-[510] tracking-[-0.2px] text-(--color-text-primary-strong)">
              Saved presets
            </h2>
            <p className="mt-0.5 text-[12px] text-(--color-text-tertiary-spec)">
              {presets.length === 0
                ? "No presets yet. Create one to make run-start a one-click."
                : `${presets.length} preset${presets.length === 1 ? "" : "s"}.`}
            </p>
          </div>
          {!showForm ? (
            <Button
              variant="primary"
              size="md"
              onClick={openNewForm}
              data-testid="run-presets-new"
            >
              <Plus size={13} strokeWidth={1.75} />
              New preset
            </Button>
          ) : null}
        </div>

        {presets.length > 0 ? (
          <div className="overflow-hidden rounded-[8px] border border-(--color-border-card)">
            <table className="w-full text-[13px]">
              <thead className="bg-(--color-bg-pill-inactive) text-(--color-text-tertiary-spec)">
                <tr>
                  <th className="px-3 py-2 text-left font-[510]">Name</th>
                  <th className="px-3 py-2 text-left font-[510]">Domain</th>
                  <th className="px-3 py-2 text-left font-[510]">Journal</th>
                  <th className="px-3 py-2 text-left font-[510]">Iters</th>
                  <th className="px-3 py-2 text-left font-[510]">Executor</th>
                  <th className="px-3 py-2 text-right font-[510]">Actions</th>
                </tr>
              </thead>
              <tbody>
                {presets.map((p, idx) => (
                  <tr
                    key={p.id}
                    data-testid={`run-preset-row-${p.id}`}
                    className={cn(
                      idx > 0 ? "border-t border-(--color-border-card)" : "",
                      "bg-(--color-bg-card)",
                    )}
                  >
                    <td className="px-3 py-2 font-[510] text-(--color-text-primary)">
                      {p.name}
                    </td>
                    <td className="px-3 py-2 font-mono text-[12px] text-(--color-text-secondary)">
                      {String(p.config.domain ?? "—")}
                    </td>
                    <td className="px-3 py-2 font-mono text-[12px] text-(--color-text-secondary)">
                      {String(p.config.journal ?? "—")}
                    </td>
                    <td className="px-3 py-2 font-mono text-[12px] text-(--color-text-secondary)">
                      {String(p.config.idea_iters ?? "—")}/
                      {String(p.config.max_revision_iters ?? "—")}
                    </td>
                    <td className="px-3 py-2 font-mono text-[12px] text-(--color-text-secondary)">
                      {String(p.config.executor ?? "—")}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-1.5">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditForm(p)}
                          aria-label={`Edit ${p.name}`}
                          data-testid={`run-preset-edit-${p.id}`}
                        >
                          <Pencil size={12} strokeWidth={1.75} />
                          Edit
                        </Button>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => onDelete(p)}
                          aria-label={`Delete ${p.name}`}
                          data-testid={`run-preset-delete-${p.id}`}
                        >
                          <Trash2 size={12} strokeWidth={1.75} />
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {showForm ? (
        <section
          className="surface-linear-card p-5"
          data-testid="run-presets-form"
        >
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[15px] font-[510] tracking-[-0.2px] text-(--color-text-primary-strong)">
              {editingId ? "Edit preset" : "New preset"}
            </h2>
            <Button
              variant="subtle"
              size="sm"
              onClick={closeForm}
              aria-label="Close form"
              data-testid="run-presets-form-close"
            >
              <X size={13} strokeWidth={1.75} />
            </Button>
          </div>
          <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Name" htmlFor="rp-name" required>
              <input
                id="rp-name"
                type="text"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className={inputClass}
                data-testid="run-presets-input-name"
              />
            </Field>
            <Field label="Domain" htmlFor="rp-domain">
              <select
                id="rp-domain"
                value={form.domain}
                onChange={(e) => setForm({ ...form, domain: e.target.value })}
                className={inputClass}
                data-testid="run-presets-input-domain"
              >
                <option value="">— none —</option>
                {domains.map((d) => (
                  <option key={d.name} value={d.name}>
                    {d.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Journal" htmlFor="rp-journal">
              <select
                id="rp-journal"
                value={form.journal}
                onChange={(e) => setForm({ ...form, journal: e.target.value })}
                className={inputClass}
                data-testid="run-presets-input-journal"
              >
                {JOURNAL_OPTIONS.map((j) => (
                  <option key={j} value={j}>
                    {j}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Executor" htmlFor="rp-executor">
              <select
                id="rp-executor"
                value={form.executor}
                onChange={(e) => setForm({ ...form, executor: e.target.value })}
                className={inputClass}
                data-testid="run-presets-input-executor"
              >
                <option value="">— none —</option>
                {executors.map((x) => (
                  <option key={x.name} value={x.name}>
                    {x.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Idea iterations" htmlFor="rp-idea">
              <input
                id="rp-idea"
                type="number"
                min={1}
                max={20}
                value={form.idea_iters}
                onChange={(e) =>
                  setForm({ ...form, idea_iters: e.target.value })
                }
                className={inputClass}
                data-testid="run-presets-input-idea-iters"
              />
            </Field>
            <Field label="Max revision iters" htmlFor="rp-rev">
              <input
                id="rp-rev"
                type="number"
                min={0}
                max={20}
                value={form.max_revision_iters}
                onChange={(e) =>
                  setForm({ ...form, max_revision_iters: e.target.value })
                }
                className={inputClass}
                data-testid="run-presets-input-revision-iters"
              />
            </Field>

            {formError ? (
              <div
                className="sm:col-span-2 flex items-start gap-2 rounded-[6px] border border-(--color-status-red)/30 bg-(--color-status-red)/10 px-3 py-2 text-[12.5px] text-(--color-status-red)"
                data-testid="run-presets-form-error"
              >
                <AlertCircle size={13} strokeWidth={1.75} className="mt-0.5" />
                {formError}
              </div>
            ) : null}

            <div className="sm:col-span-2 flex justify-end gap-2">
              <Button variant="ghost" size="md" type="button" onClick={closeForm}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="md"
                type="submit"
                disabled={submitting}
                data-testid="run-presets-form-submit"
              >
                {submitting ? (
                  <>
                    <Loader2 size={13} strokeWidth={1.75} className="animate-spin" />
                    Saving…
                  </>
                ) : editingId ? (
                  "Save changes"
                ) : (
                  "Create preset"
                )}
              </Button>
            </div>
          </form>
        </section>
      ) : null}

      {/*
        TODO(run-start): wire `preset_id` into the workspace run-start
        payload so the operator can pick a saved preset and have its
        config merged over the form defaults. Tracked separately to keep
        this change scoped to the settings UI.
      */}

      {toast ? (
        <div
          role="status"
          data-testid="run-presets-toast"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-[8px] border border-(--color-border-card) bg-(--color-bg-card) px-3 py-2 text-[12.5px] text-(--color-text-primary) shadow-[var(--shadow-dialog)]"
        >
          {toast}
        </div>
      ) : null}
    </>
  );
}

const inputClass =
  "block w-full rounded-[6px] border border-(--color-border-solid) bg-(--color-bg-card) px-2.5 py-1.5 text-[13px] text-(--color-text-primary) outline-none transition-colors focus:border-(--color-brand-indigo) focus:ring-1 focus:ring-(--color-brand-indigo)";

function Field({
  label,
  htmlFor,
  required,
  children,
}: {
  label: string;
  htmlFor: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 block text-[12px] font-[510] text-(--color-text-secondary)"
      >
        {label}
        {required ? (
          <span className="ml-0.5 text-(--color-status-red)">*</span>
        ) : null}
      </label>
      {children}
    </div>
  );
}
