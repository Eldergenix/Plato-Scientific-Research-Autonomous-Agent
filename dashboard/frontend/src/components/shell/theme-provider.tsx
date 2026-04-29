"use client";

import * as React from "react";

type Theme = "dark" | "light" | "system";
type ResolvedTheme = "dark" | "light";

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  setTheme: (t: Theme) => void;
}

const STORAGE_KEY = "plato:theme";

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

function readStored(): Theme {
  if (typeof window === "undefined") return "dark";
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "dark" || v === "light" || v === "system") return v;
  } catch {
    /* ignore */
  }
  return "dark";
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return true;
  }
}

function applyClass(resolved: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.className = resolved;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<Theme>(() => readStored());
  const [resolvedTheme, setResolvedTheme] = React.useState<ResolvedTheme>(() => {
    const t = readStored();
    if (t === "system") return systemPrefersDark() ? "dark" : "light";
    return t;
  });

  // Apply class + persist on theme change.
  React.useEffect(() => {
    const next: ResolvedTheme =
      theme === "system" ? (systemPrefersDark() ? "dark" : "light") : theme;
    setResolvedTheme(next);
    applyClass(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* storage may be unavailable */
    }
  }, [theme]);

  // When theme === "system", react to OS-level prefers-color-scheme changes.
  React.useEffect(() => {
    if (theme !== "system" || typeof window === "undefined") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      const next: ResolvedTheme = e.matches ? "dark" : "light";
      setResolvedTheme(next);
      applyClass(next);
    };
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [theme]);

  const setTheme = React.useCallback((t: Theme) => {
    setThemeState(t);
  }, []);

  const value = React.useMemo<ThemeContextValue>(
    () => ({ theme, resolvedTheme, setTheme }),
    [theme, resolvedTheme, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used inside a <ThemeProvider>");
  }
  return ctx;
}
