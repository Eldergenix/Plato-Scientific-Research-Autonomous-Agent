"use client";

import * as React from "react";
import { ChevronDown, ChevronUp, Pause, Play, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LogLine } from "@/lib/types";

const SOURCE_FILTERS = ["all", "idea", "method", "literature", "results", "paper"] as const;
type SourceFilter = (typeof SOURCE_FILTERS)[number];

const AGENT_COLORS: Record<string, string> = {
  idea_maker: "text-(--color-brand-hover)",
  idea_hater: "text-(--color-status-amber)",
  engineer: "text-(--color-status-emerald)",
  researcher: "text-(--color-brand-lavender)",
  planner: "text-(--color-text-secondary)",
  reviewer: "text-(--color-status-amber)",
  formatter: "text-(--color-text-tertiary)",
};

export function AgentLogStream({
  lines,
  height,
  onChangeHeight,
  paused,
  onTogglePause,
}: {
  lines: LogLine[];
  height: 0 | 30 | 60;
  onChangeHeight: (h: 0 | 30 | 60) => void;
  paused: boolean;
  onTogglePause: () => void;
}) {
  const [filter, setFilter] = React.useState<SourceFilter>("all");
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const filtered = React.useMemo(
    () => (filter === "all" ? lines : lines.filter((l) => l.source === filter)),
    [filter, lines],
  );

  React.useEffect(() => {
    if (paused || height === 0) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [filtered.length, paused, height]);

  const collapsed = height === 0;
  const heightClass =
    height === 0 ? "h-9" : height === 30 ? "h-[200px]" : "h-[420px]";

  return (
    <div
      className={cn(
        "hairline-t bg-(--color-bg-panel) flex flex-col transition-[height] duration-150",
        heightClass,
      )}
      role="region"
      aria-label="Agent log stream"
    >
      <div className="h-9 flex items-center px-3 gap-2 hairline-b bg-(--color-bg-marketing)">
        <button
          type="button"
          aria-label={collapsed ? "Open log" : "Collapse log"}
          onClick={() => onChangeHeight(collapsed ? 30 : 0)}
          className="size-6 inline-flex items-center justify-center rounded-[4px] text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)"
        >
          {collapsed ? <ChevronUp size={13} strokeWidth={1.5} /> : <ChevronDown size={13} strokeWidth={1.5} />}
        </button>
        <span className="text-[12px] font-medium text-(--color-text-primary)">
          Agent log
        </span>
        <span className="font-mono text-[11px] text-(--color-text-quaternary) tabular-nums">
          {filtered.length} lines
        </span>

        {!collapsed && (
          <>
            <div className="ml-3 flex items-center gap-1">
              {SOURCE_FILTERS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setFilter(s)}
                  className={cn(
                    "h-6 px-2 rounded-[4px] text-[11px] capitalize transition-colors",
                    filter === s
                      ? "bg-(--color-ghost-bg-hover) text-(--color-text-primary)"
                      : "text-(--color-text-tertiary) hover:bg-(--color-ghost-bg)",
                  )}
                >
                  {s}
                </button>
              ))}
            </div>

            <div className="ml-auto flex items-center gap-1">
              <button
                type="button"
                onClick={onTogglePause}
                aria-label={paused ? "Resume tail" : "Pause tail"}
                className="h-6 px-2 rounded-[4px] text-[11px] text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary) inline-flex items-center gap-1"
              >
                {paused ? <Play size={11} strokeWidth={1.5} /> : <Pause size={11} strokeWidth={1.5} />}
                {paused ? "Resume" : "Pause"}
              </button>
              <button
                type="button"
                onClick={() => onChangeHeight(height === 60 ? 30 : 60)}
                aria-label={height === 60 ? "Shrink log panel" : "Expand log panel"}
                className="size-6 inline-flex items-center justify-center rounded-[4px] text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)"
              >
                {height === 60 ? <ChevronDown size={11} strokeWidth={1.5} /> : <ChevronUp size={11} strokeWidth={1.5} />}
              </button>
              <button
                type="button"
                aria-label="Close log"
                onClick={() => onChangeHeight(0)}
                className="size-6 inline-flex items-center justify-center rounded-[4px] text-(--color-text-tertiary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)"
              >
                <X size={11} strokeWidth={1.5} />
              </button>
            </div>
          </>
        )}
      </div>

      {!collapsed && (
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto font-mono text-[12px] leading-[1.55] px-3 py-2"
        >
          {filtered.length === 0 ? (
            <p className="text-(--color-text-quaternary) text-[12px]">
              No log lines yet. Start a run to see agent reasoning here.
            </p>
          ) : (
            filtered.map((line, i) => <LogRow key={i} line={line} />)
          )}
        </div>
      )}
    </div>
  );
}

function LogRow({ line }: { line: LogLine }) {
  const ts = line.ts.slice(11, 19);
  return (
    <div
      className={cn(
        "flex items-start gap-2 py-0.5 hover:bg-(--color-ghost-bg)",
        line.level === "error" && "text-(--color-status-red)",
        line.level === "warn" && "text-(--color-status-amber)",
        line.level === "tool" && "opacity-75",
      )}
    >
      <span className="text-(--color-text-quaternary) tabular-nums shrink-0">{ts}</span>
      {line.agent && (
        <span className={cn("font-medium shrink-0", AGENT_COLORS[line.agent] ?? "text-(--color-text-secondary)")}>
          {line.agent}
        </span>
      )}
      <span className="text-(--color-text-secondary) flex-1 whitespace-pre-wrap break-words">
        {line.text}
      </span>
      {line.tokens && (
        <span className="text-(--color-text-quaternary) tabular-nums shrink-0">
          {line.tokens}t
        </span>
      )}
    </div>
  );
}
