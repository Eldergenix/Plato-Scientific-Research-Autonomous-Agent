import type { Metadata } from "next";
import { headers } from "next/headers";
import { Inter, JetBrains_Mono } from "next/font/google";
import { AuthProvider } from "@/components/auth/auth-context";
import { ErrorBoundary } from "@/components/shell/error-boundary";
import { ThemeProvider } from "@/components/shell/theme-provider";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans-loaded",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono-loaded",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Plato — Scientific Research Dashboard",
  description:
    "Multi-agent research workspace for Plato — orchestrate ideas, methods, results, and papers.",
};

// Inline pre-hydration script that mirrors ThemeProvider's resolution logic.
// Static literal (no user input) — safe injection. Keep in sync with
// src/components/shell/theme-provider.tsx so the class matches what React
// would set, avoiding a flash of un-themed content.
const themeBootstrap = `(function(){try{var t=localStorage.getItem("plato:theme")||"dark";var d=t==="system"?(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):t;document.documentElement.className=d;}catch(e){document.documentElement.className="dark";}})();`;

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // CSP nonce set by middleware.ts. Required so the inline themeBootstrap
  // <script> below can run without `'unsafe-inline'` in script-src.
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  // suppressHydrationWarning on <html> is required because the inline
  // themeBootstrap script writes documentElement.className before React
  // reconciles. Without it, React logs a hydration mismatch.
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}>
        {/* WCAG 2.4.1 bypass-block: keyboard users can skip the
            sidebar with one Tab. Hidden until focused. */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[9999] focus:rounded-[6px] focus:bg-(--color-bg-card) focus:px-3 focus:py-1.5 focus:text-[13px] focus:text-(--color-text-primary)"
        >
          Skip to main content
        </a>
        <ThemeProvider>
          <AuthProvider>
            <ErrorBoundary>{children}</ErrorBoundary>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
