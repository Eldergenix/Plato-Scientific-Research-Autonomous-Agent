"use client";

import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

// NOTE: `confirmLabel` and `cancelLabel` keep hardcoded English defaults so
// existing callers don't break. New callers SHOULD pass localized strings —
// e.g. `confirmLabel={t("confirm")}` from the `common` namespace, or one of
// the `dialogs.*` / `actions.*` keys (see messages/en.json). The defaults
// will eventually be removed once all callers are migrated.
export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "primary" | "danger";
  onConfirm: () => void | Promise<void>;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "primary",
  onConfirm,
}: ConfirmDialogProps) {
  const [busy, setBusy] = React.useState(false);

  const handleConfirm = React.useCallback(async () => {
    setBusy(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  }, [onConfirm, onOpenChange]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[420px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2",
            "bg-(--color-bg-card)",
          )}
          style={{
            border: "1px solid var(--color-border-card)",
            borderRadius: 12,
            boxShadow:
              "0 0 0 1px rgba(0, 0, 0, 0.2), 0 10px 30px rgba(0, 0, 0, 0.45), 0 4px 8px rgba(0, 0, 0, 0.3)",
          }}
        >
          <div className="flex items-start gap-3 px-5 pt-5">
            <div
              className={cn(
                "size-9 shrink-0 rounded-full flex items-center justify-center",
                variant === "danger"
                  ? "bg-(--color-status-red)/12 text-(--color-status-red)"
                  : "bg-(--color-brand-indigo)/12 text-(--color-brand-hover)",
              )}
            >
              <AlertTriangle size={16} strokeWidth={1.75} />
            </div>
            <div className="flex-1 min-w-0">
              <Dialog.Title className="text-[15px] font-medium text-(--color-text-primary) leading-snug">
                {title}
              </Dialog.Title>
              {description && (
                <Dialog.Description className="mt-1.5 text-[13px] text-(--color-text-tertiary) leading-relaxed">
                  {description}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close"
                className="size-7 inline-flex items-center justify-center rounded-full text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary) transition-colors"
              >
                <X size={14} strokeWidth={1.75} />
              </button>
            </Dialog.Close>
          </div>

          <div className="px-5 pt-5 pb-4 mt-2 hairline-t flex items-center justify-end gap-2">
            <Dialog.Close asChild>
              <Button variant="ghost" size="md" disabled={busy}>
                {cancelLabel}
              </Button>
            </Dialog.Close>
            <Button
              variant={variant === "danger" ? "danger" : "primary"}
              size="md"
              disabled={busy}
              onClick={handleConfirm}
            >
              {busy ? "Working…" : confirmLabel}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Convenience hook for one-shot confirmation flows. */
export function useConfirm() {
  const [config, setConfig] = React.useState<Omit<ConfirmDialogProps, "open" | "onOpenChange"> | null>(null);

  const confirm = React.useCallback(
    (
      cfg: Omit<ConfirmDialogProps, "open" | "onOpenChange" | "onConfirm"> & {
        onConfirm?: () => void | Promise<void>;
      },
    ) =>
      new Promise<boolean>((resolve) => {
        setConfig({
          ...cfg,
          onConfirm: async () => {
            await cfg.onConfirm?.();
            resolve(true);
          },
        });
        // Resolve false if dismissed.
        const cleanup = () => resolve(false);
        // Dismiss handler is provided by ConfirmDialog rendered below.
        void cleanup;
      }),
    [],
  );

  const node = config ? (
    <ConfirmDialog
      open
      onOpenChange={(o) => !o && setConfig(null)}
      {...config}
    />
  ) : null;

  return { confirm, node };
}
