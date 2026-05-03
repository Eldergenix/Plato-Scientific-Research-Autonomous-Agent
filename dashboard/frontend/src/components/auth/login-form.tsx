"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuth } from "./auth-context";

export interface LoginFormProps {
  /** Where to send the user after a successful login. Defaults to "/". */
  redirectTo?: string;
}

export function LoginForm({ redirectTo = "/" }: LoginFormProps) {
  const router = useRouter();
  const { login } = useAuth();
  const [value, setValue] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const trimmed = value.trim();
  const canSubmit = trimmed.length > 0 && !submitting;

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await login(trimmed);
      router.push(redirectTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="login-form"
      className="flex flex-col gap-4"
    >
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="login-user-id"
          className="block text-[12px] font-medium text-(--color-text-secondary-spec)"
        >
          User ID
        </label>
        <input
          id="login-user-id"
          data-testid="login-user-id"
          autoFocus
          autoComplete="off"
          spellCheck={false}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={submitting}
          placeholder="alice"
          className={cn(
            "h-9 rounded-[6px] border border-[#262628] bg-[#141415] px-2.5",
            "text-[13px] text-(--color-text-primary) placeholder:text-(--color-text-quaternary-spec)",
            "transition-colors hover:border-[#34343a]",
            "focus-visible:border-(--color-brand-indigo) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--color-brand-indigo)",
            "disabled:opacity-50",
          )}
        />
      </div>

      {error ? (
        <div
          role="alert"
          aria-live="polite"
          aria-atomic="true"
          data-testid="login-error"
          className="rounded-[6px] border border-(--color-status-red)/30 bg-(--color-status-red)/10 px-2.5 py-1.5 text-[12px] text-(--color-status-red)"
        >
          {error}
        </div>
      ) : null}

      <Button
        type="submit"
        variant="primary"
        size="md"
        disabled={!canSubmit}
        data-testid="login-submit"
      >
        <LogIn size={13} strokeWidth={1.75} />
        {submitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
