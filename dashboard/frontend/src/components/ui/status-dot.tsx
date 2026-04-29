import { cn } from "@/lib/utils";
import type { StageStatus } from "@/lib/types";

const STATUS_CLASSES: Record<StageStatus, string> = {
  empty: "bg-(--color-text-quaternary)",
  pending: "bg-(--color-text-tertiary)",
  running: "bg-(--color-brand-interactive) animate-pulse-dot",
  done: "bg-(--color-status-emerald)",
  stale: "bg-(--color-status-amber)",
  failed: "bg-(--color-status-red)",
};

export function StatusDot({
  status,
  size = 8,
  className,
}: {
  status: StageStatus;
  size?: 6 | 8 | 10;
  className?: string;
}) {
  return (
    <span
      role="img"
      aria-label={`status: ${status}`}
      className={cn("inline-block rounded-full", STATUS_CLASSES[status], className)}
      style={{ width: size, height: size }}
    />
  );
}
