import { cn } from "@/lib/utils";
import type { StageStatus } from "@/lib/types";

type StatusIconProps = {
  status: StageStatus;
  size?: number;
  className?: string;
};

type StatusVisual = {
  color: string;
  dashed: boolean;
  fillRatio: number;
  variant: "circle" | "x";
};

const VISUALS: Record<StageStatus, StatusVisual> = {
  running: { color: "#F0BF00", dashed: true, fillRatio: 0.75, variant: "circle" },
  pending: { color: "#F0BF00", dashed: true, fillRatio: 0.33, variant: "circle" },
  done: { color: "#27A644", dashed: false, fillRatio: 1, variant: "circle" },
  empty: { color: "#919193", dashed: true, fillRatio: 0, variant: "circle" },
  stale: { color: "#919193", dashed: true, fillRatio: 0.33, variant: "circle" },
  failed: { color: "#EB5757", dashed: false, fillRatio: 0, variant: "x" },
};

export function StatusIcon({ status, size = 14, className }: StatusIconProps) {
  const visual = VISUALS[status];

  if (visual.variant === "x") {
    return (
      <svg
        role="img"
        aria-label={`status: ${status}`}
        width={size}
        height={size}
        viewBox="0 0 14 14"
        fill="none"
        className={cn("flex-none", className)}
      >
        <circle
          cx={7}
          cy={7}
          r={5.5}
          stroke={visual.color}
          strokeWidth={1.5}
          fill="none"
        />
        <path
          d="M4.6 4.6 L9.4 9.4 M9.4 4.6 L4.6 9.4"
          stroke={visual.color}
          strokeWidth={1.5}
          strokeLinecap="round"
        />
      </svg>
    );
  }

  const radius = 5.5;
  const circumference = 2 * Math.PI * radius;
  const arcLength = circumference * visual.fillRatio;
  const dashArray = visual.dashed ? "2.4 2.4" : undefined;
  const ringStrokeArray = visual.dashed
    ? dashArray
    : `${circumference} ${circumference}`;

  return (
    <svg
      role="img"
      aria-label={`status: ${status}`}
      width={size}
      height={size}
      viewBox="0 0 14 14"
      fill="none"
      className={cn("flex-none", className)}
    >
      <circle
        cx={7}
        cy={7}
        r={radius}
        stroke={visual.color}
        strokeWidth={1.5}
        strokeDasharray={ringStrokeArray}
        fill="none"
      />
      {visual.fillRatio > 0 && visual.fillRatio < 1 ? (
        <circle
          cx={7}
          cy={7}
          r={radius / 2}
          stroke={visual.color}
          strokeWidth={radius}
          strokeDasharray={`${arcLength / 2} ${circumference}`}
          fill="none"
          transform="rotate(-90 7 7)"
        />
      ) : null}
      {visual.fillRatio === 1 ? (
        <circle cx={7} cy={7} r={3.25} fill={visual.color} />
      ) : null}
    </svg>
  );
}
