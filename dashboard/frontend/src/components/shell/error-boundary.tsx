"use client";

import * as React from "react";
import { AlertOctagon, ExternalLink, KeyRound, RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Optional custom fallback */
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
    this.reset = this.reset.bind(this);
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    if (typeof console !== "undefined") {
      console.error("[ErrorBoundary]", error, errorInfo);
    }
  }

  reset(): void {
    this.setState({ error: null });
  }

  render(): React.ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) {
      return this.props.fallback(error, this.reset);
    }

    return <DefaultFallback error={error} reset={this.reset} />;
  }
}

/* ------------------------------------------------------------------ fallback */

interface FallbackContent {
  heading: string;
  description: React.ReactNode;
  detail?: string;
  primaryAction?: {
    label: string;
    onClick: () => void;
    icon?: React.ReactNode;
  };
}

function classifyError(error: Error): FallbackContent {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return {
        heading: "Backend offline",
        description: (
          <>
            The Plato API is not reachable. Start it with{" "}
            <code className="font-mono text-(--color-text-secondary) px-1 py-0.5 rounded bg-(--color-ghost-bg)">
              plato dashboard
            </code>
            .
          </>
        ),
        detail: detailString(error.detail),
      };
    }
    if (error.status === 401) {
      return {
        heading: "Authentication required",
        description:
          "Your session is missing or has expired. Add an API key to continue.",
        detail: detailString(error.detail),
        primaryAction: {
          label: "Go to /keys",
          onClick: () => {
            window.location.href = "/keys";
          },
          icon: <KeyRound size={13} strokeWidth={1.75} />,
        },
      };
    }
    if (error.status === 402) {
      return {
        heading: "Demo budget exhausted",
        description:
          "The shared demo budget has been spent. Run Plato locally for full access.",
        detail: detailString(error.detail),
      };
    }
    return {
      heading: "Something went wrong",
      description: `API error ${error.status}`,
      detail: detailString(error.detail),
    };
  }
  return {
    heading: "Something went wrong",
    description: "An unexpected runtime error occurred.",
    detail: error.stack ?? error.message,
  };
}

function detailString(detail: unknown): string {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  try {
    return JSON.stringify(detail, null, 2);
  } catch {
    return String(detail);
  }
}

function DefaultFallback({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  const content = classifyError(error);

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-(--color-bg-page) text-(--color-text-primary) p-6">
      <div
        className="w-full max-w-md flex flex-col items-center text-center surface-linear-card p-6"
        role="alert"
        aria-live="assertive"
      >
        <AlertOctagon
          size={48}
          strokeWidth={1.5}
          color="#EB5757"
          aria-hidden="true"
        />
        <h1
          className="mt-4 text-(--color-text-primary)"
          style={{
            fontFamily: "var(--font-sans)",
            fontWeight: 510,
            fontSize: 24,
            letterSpacing: "-0.5px",
          }}
        >
          {content.heading}
        </h1>
        <p className="mt-2 text-[13px] text-(--color-text-tertiary)">
          {content.description}
        </p>

        {content.detail && (
          <pre
            className="mt-4 w-full overflow-auto text-left font-mono text-[12px] text-(--color-text-secondary) bg-(--color-bg-card) border border-(--color-border-card) rounded-[6px]"
            style={{ padding: 12, maxHeight: 160 }}
          >
            {content.detail}
          </pre>
        )}

        <div className="mt-5 flex items-center gap-2">
          {content.primaryAction ? (
            <Button
              variant="primary"
              size="md"
              onClick={content.primaryAction.onClick}
            >
              {content.primaryAction.icon}
              {content.primaryAction.label}
            </Button>
          ) : (
            <Button
              variant="primary"
              size="md"
              onClick={() => window.location.reload()}
            >
              <RefreshCw size={13} strokeWidth={1.75} />
              Reload page
            </Button>
          )}
          <Button variant="ghost" size="md" onClick={reset}>
            Reset
          </Button>
        </div>

        <p className="mt-5 text-[12px] text-(--color-text-quaternary)">
          If this keeps happening,{" "}
          <a
            href="https://github.com/plato-research/plato/issues/new"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-(--color-brand-interactive) hover:text-(--color-brand-hover) underline-offset-2 hover:underline"
          >
            open an issue
            <ExternalLink size={11} strokeWidth={1.75} />
          </a>
          .
        </p>
      </div>
    </div>
  );
}
