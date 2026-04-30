"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { LogIn, LogOut, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "./auth-context";

/**
 * Avatar + dropdown for the signed-in user.
 *
 * - Signed in: shows a circle with the first letter of ``user_id`` and a
 *   menu with "Signed in as …", a Settings link, and Sign out.
 * - Signed out, auth optional: shows a "Sign in" link to /login.
 * - Signed out, auth required: redirects to /login on mount.
 */
export function UserMenu() {
  const router = useRouter();
  const { user_id, authRequired, loading, logout } = useAuth();

  React.useEffect(() => {
    if (loading) return;
    if (user_id === null && authRequired) {
      router.push("/login");
    }
  }, [user_id, authRequired, loading, router]);

  if (user_id === null) {
    if (authRequired) return null; // redirecting
    return (
      <a
        href="/login"
        data-testid="user-menu-signin"
        className={cn(
          "inline-flex h-7 items-center gap-1.5 rounded-[6px] px-2 text-[12px]",
          "text-(--color-text-secondary) hover:bg-(--color-ghost-bg-hover) hover:text-(--color-text-primary)",
          "transition-colors",
        )}
      >
        <LogIn size={12} strokeWidth={1.75} />
        Sign in
      </a>
    );
  }

  const initial = user_id.trim().charAt(0).toUpperCase() || "?";

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          data-testid="user-menu-trigger"
          aria-label={`User menu for ${user_id}`}
          className={cn(
            "inline-flex size-7 items-center justify-center rounded-full",
            "bg-(--color-brand-indigo)/15 text-[12px] font-medium text-(--color-brand-hover)",
            "transition-colors hover:bg-(--color-brand-indigo)/25",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-interactive)",
          )}
        >
          {initial}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          data-testid="user-menu-content"
          className={cn(
            "z-[60] min-w-[200px] overflow-hidden rounded-[8px]",
            "border border-(--color-border-card) bg-(--color-bg-card) shadow-[var(--shadow-dialog)]",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0",
          )}
        >
          <div
            data-testid="user-menu-header"
            className="border-b border-[#1D1D1F] px-3 py-2 text-[11.5px] text-(--color-text-tertiary-spec)"
          >
            Signed in as{" "}
            <span className="font-medium text-(--color-text-primary)">{user_id}</span>
          </div>
          <div className="p-1">
            <DropdownMenu.Item asChild>
              <a
                href="/settings"
                data-testid="user-menu-settings"
                className={cn(
                  "flex h-7 cursor-pointer items-center gap-2 rounded-[4px] px-2",
                  "text-[12.5px] text-(--color-text-secondary-spec)",
                  "data-[highlighted]:bg-(--color-ghost-bg-hover) data-[highlighted]:text-(--color-text-primary)",
                  "data-[highlighted]:outline-none",
                )}
              >
                <Settings size={12} strokeWidth={1.75} />
                Settings
              </a>
            </DropdownMenu.Item>
            <DropdownMenu.Item
              data-testid="user-menu-signout"
              onSelect={() => {
                void logout();
              }}
              className={cn(
                "flex h-7 cursor-pointer items-center gap-2 rounded-[4px] px-2",
                "text-[12.5px] text-(--color-text-secondary-spec)",
                "data-[highlighted]:bg-(--color-ghost-bg-hover) data-[highlighted]:text-(--color-text-primary)",
                "data-[highlighted]:outline-none",
              )}
            >
              <LogOut size={12} strokeWidth={1.75} />
              Sign out
            </DropdownMenu.Item>
          </div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
