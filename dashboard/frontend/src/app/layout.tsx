import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
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

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className={`${inter.variable} ${jetbrainsMono.variable} antialiased`}>
        <ThemeProvider>
          <ErrorBoundary>{children}</ErrorBoundary>
        </ThemeProvider>
      </body>
    </html>
  );
}
