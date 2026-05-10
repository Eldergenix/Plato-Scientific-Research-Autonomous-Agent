import { SignUp } from "@clerk/nextjs";
import { redirect } from "next/navigation";
import { isClerkAuthEnabled } from "@/lib/auth-mode";

export default function SignUpPage() {
  if (!isClerkAuthEnabled()) {
    redirect("/login");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-(--color-bg-page) p-6">
      <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" />
    </main>
  );
}
