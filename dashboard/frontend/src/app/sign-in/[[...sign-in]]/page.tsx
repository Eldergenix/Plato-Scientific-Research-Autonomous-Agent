import { SignIn } from "@clerk/nextjs";
import { redirect } from "next/navigation";
import { isClerkAuthEnabled } from "@/lib/auth-mode";

export default function SignInPage() {
  if (!isClerkAuthEnabled()) {
    redirect("/login");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-(--color-bg-page) p-6">
      <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />
    </main>
  );
}
