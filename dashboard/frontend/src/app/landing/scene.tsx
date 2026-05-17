"use client";

import * as React from "react";
import Link from "next/link";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-context";

const SPLINE_VIEWER_SRC =
  "https://unpkg.com/@splinetool/viewer@1.12.94/build/spline-viewer.js";
const SPLINE_SCENE_URL =
  "https://prod.spline.design/L3ajUTEjDj55mxCT/scene.splinecode";

export function LandingScene() {
  const router = useRouter();
  const { loading, user_id } = useAuth();

  React.useEffect(() => {
    if (!loading && user_id) {
      router.replace("/");
    }
  }, [loading, router, user_id]);

  return (
    <main className="relative h-svh min-h-screen w-screen overflow-hidden bg-black">
      <Script src={SPLINE_VIEWER_SRC} type="module" strategy="afterInteractive" />
      <div className="absolute inset-0" aria-hidden="true" data-testid="landing-spline">
        {React.createElement("spline-viewer", {
          url: SPLINE_SCENE_URL,
          className: "block h-full w-full",
          style: { height: "100%", width: "100%" },
        })}
      </div>
      <div className="absolute left-1/2 top-3/4 z-10 w-[min(320px,calc(100vw-48px))] -translate-x-1/2 -translate-y-1/2">
        <Link
          href="/login?next=%2F"
          data-testid="landing-enter"
          className="flex h-12 w-full items-center justify-center rounded-full bg-white/20 px-6 text-[14px] font-medium text-black shadow-[0_10px_30px_rgba(0,0,0,0.22)] backdrop-blur-[18px] transition-transform duration-150 hover:scale-[1.015] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/80 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
        >
          enter
        </Link>
      </div>
    </main>
  );
}
