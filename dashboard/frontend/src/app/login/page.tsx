import type { Metadata } from "next";
import LoginClient from "./login-client";

export const metadata: Metadata = {
  title: "Sign in — Plato",
  description: "Sign in to your Plato workspace.",
};

export default function LoginPage() {
  return <LoginClient />;
}
