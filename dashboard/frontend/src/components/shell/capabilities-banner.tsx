"use client";

import * as React from "react";
import { Sparkles } from "lucide-react";

export interface CapabilitiesBannerProps {
  isDemo: boolean;
  notes: string[];
  onLearnMore?: () => void;
}

export function CapabilitiesBanner(props: CapabilitiesBannerProps) {
  const { isDemo, notes, onLearnMore } = props;
  if (!isDemo) return null;

  const firstNote = notes[0];

  return (
    <div
      className="sticky top-0 z-40 flex h-8 items-center justify-between px-4"
      style={{
        background:
          "linear-gradient(90deg, rgba(94,106,210,0.12) 0%, rgba(94,106,210,0.04) 100%)",
        borderBottom: "1px solid var(--color-border-card)",
      }}
    >
      <div className="flex min-w-0 items-center gap-2">
        <Sparkles
          className="shrink-0"
          size={14}
          style={{ color: "var(--color-brand-hover)" }}
        />
        <span className="text-[13px] font-medium text-white">Demo mode active.</span>
        {firstNote && (
          <span className="truncate text-[13px] text-(--color-text-tertiary-spec)">
            {firstNote}
          </span>
        )}
      </div>
      <a
        href="#"
        onClick={(e) => {
          if (onLearnMore) {
            e.preventDefault();
            onLearnMore();
          }
        }}
        className="shrink-0 text-[13px] font-medium transition-colors"
        style={{ color: "#5e6ad2" }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "#7170ff")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "#5e6ad2")}
      >
        Run locally for full features →
      </a>
    </div>
  );
}
