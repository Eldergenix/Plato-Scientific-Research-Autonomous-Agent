import { auth } from "@clerk/nextjs/server";
import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { isClerkAuthEnabled } from "@/lib/auth-mode";
import { LandingScene } from "./scene";

const TENANT_COOKIE = "plato_user";

export const metadata: Metadata = {
  title: "Plato",
  description: "Enter the Plato research workspace.",
};

export default async function LandingPage() {
  if (await isAuthenticated()) {
    redirect("/");
  }

  return <LandingScene />;
}

async function isAuthenticated(): Promise<boolean> {
  if (isClerkAuthEnabled()) {
    const session = await auth();
    return Boolean(session.userId);
  }

  const cookieStore = await cookies();
  return cookieStore.has(TENANT_COOKIE);
}
