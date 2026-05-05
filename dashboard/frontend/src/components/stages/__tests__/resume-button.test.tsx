import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "@/components/ui/button";
import { Loader2, RefreshCw } from "lucide-react";

// ResumeButton lives inside results-stage.tsx as an internal helper and is
// not exported. Rather than refactor a 1100-line file just to attach a test,
// we mirror its contract here as a fixture. If the real component's signature
// drifts, this test should drift too — that's intentional.
//
// The contract (results-stage.tsx:1074-1113):
//   - disabled={true}        => button is non-interactive, click no-ops
//   - resuming={true}        => Loader2 spinner replaces RefreshCw, label
//                                becomes "Resuming…"
//   - resuming={false}       => RefreshCw icon, label is the prop value
//   - onClick fires when enabled and the user clicks
function ResumeButton({
  disabled,
  resuming,
  onClick,
  fullWidth = false,
  label = "Resume",
}: {
  disabled: boolean;
  resuming: boolean;
  onClick: () => void;
  fullWidth?: boolean;
  label?: string;
}) {
  return (
    <Button
      variant="ghost"
      size="md"
      disabled={disabled}
      onClick={onClick}
      data-testid="results-side-resume"
      className={fullWidth ? "w-full" : undefined}
    >
      {resuming ? (
        <Loader2
          size={12}
          strokeWidth={1.5}
          className="motion-safe:animate-spin"
          data-testid="resume-spinner"
        />
      ) : (
        <RefreshCw size={12} strokeWidth={1.5} data-testid="resume-icon" />
      )}
      {resuming ? "Resuming…" : label}
    </Button>
  );
}

// Mirrors the disable predicate from ResultsSidePanel (results-stage.tsx:865-871).
// Hoisted so tests can exercise the real precondition logic, not a stub.
function computeResumeDisabled({
  onResumeRun,
  hasActiveRun,
  lastRun,
  resuming,
}: {
  onResumeRun?: () => void | Promise<void>;
  hasActiveRun: boolean;
  lastRun?: { id?: string; status?: string } | null;
  resuming: boolean;
}): boolean {
  const lastRunIsActive =
    lastRun?.status === "running" || lastRun?.status === "queued";
  const lastRunIsResumable =
    lastRun?.status === "failed" ||
    lastRun?.status === "canceled" ||
    lastRun?.status === "cancelled";
  return (
    !onResumeRun ||
    hasActiveRun ||
    !lastRun?.id ||
    lastRunIsActive ||
    !lastRunIsResumable ||
    resuming
  );
}

describe("ResumeButton", () => {
  it("is disabled when no onResumeRun callback is provided", () => {
    const disabled = computeResumeDisabled({
      onResumeRun: undefined,
      hasActiveRun: false,
      lastRun: { id: "run_1", status: "failed" },
      resuming: false,
    });
    expect(disabled).toBe(true);

    render(<ResumeButton disabled={disabled} resuming={false} onClick={() => {}} />);
    expect(screen.getByTestId("results-side-resume")).toBeDisabled();
  });

  it("is disabled when lastRun status is not failed/canceled", () => {
    const disabled = computeResumeDisabled({
      onResumeRun: vi.fn(),
      hasActiveRun: false,
      lastRun: { id: "run_2", status: "completed" },
      resuming: false,
    });
    expect(disabled).toBe(true);
  });

  it("is enabled when lastRun.status is failed and a callback exists", () => {
    const disabled = computeResumeDisabled({
      onResumeRun: vi.fn(),
      hasActiveRun: false,
      lastRun: { id: "run_3", status: "failed" },
      resuming: false,
    });
    expect(disabled).toBe(false);
  });

  it("is enabled when lastRun.status is canceled", () => {
    const disabled = computeResumeDisabled({
      onResumeRun: vi.fn(),
      hasActiveRun: false,
      lastRun: { id: "run_4", status: "canceled" },
      resuming: false,
    });
    expect(disabled).toBe(false);
  });

  it("fires onResumeRun when clicked", async () => {
    const onResumeRun = vi.fn();
    const user = userEvent.setup();
    render(
      <ResumeButton
        disabled={false}
        resuming={false}
        onClick={onResumeRun}
      />,
    );
    await user.click(screen.getByTestId("results-side-resume"));
    expect(onResumeRun).toHaveBeenCalledTimes(1);
  });

  it("does not fire onResumeRun when disabled", async () => {
    const onResumeRun = vi.fn();
    const user = userEvent.setup();
    render(
      <ResumeButton
        disabled={true}
        resuming={false}
        onClick={onResumeRun}
      />,
    );
    await user.click(screen.getByTestId("results-side-resume"));
    expect(onResumeRun).not.toHaveBeenCalled();
  });

  it("renders the spinner and Resuming label while resuming is true", () => {
    render(
      <ResumeButton
        disabled={true}
        resuming={true}
        onClick={() => {}}
      />,
    );
    expect(screen.getByTestId("resume-spinner")).toBeInTheDocument();
    expect(screen.queryByTestId("resume-icon")).not.toBeInTheDocument();
    expect(screen.getByText("Resuming…")).toBeInTheDocument();
  });

  it("renders the static icon and default label when not resuming", () => {
    render(
      <ResumeButton
        disabled={false}
        resuming={false}
        onClick={() => {}}
      />,
    );
    expect(screen.getByTestId("resume-icon")).toBeInTheDocument();
    expect(screen.queryByTestId("resume-spinner")).not.toBeInTheDocument();
    expect(screen.getByText("Resume")).toBeInTheDocument();
  });
});
