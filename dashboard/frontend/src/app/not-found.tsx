import Link from "next/link";
import { FileQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";

// Default Next.js renders a plain "404 — Not found" string with no shell.
// This component matches the RouteError visual so a 404 inside a child
// segment doesn't break the user out of the app's navigation.
export default function NotFound() {
  return (
    <div
      role="alert"
      data-testid="route-not-found"
      className="flex min-h-[40vh] flex-col items-center justify-center gap-3 px-6 py-8 text-(--color-text-primary)"
    >
      <FileQuestion
        size={28}
        strokeWidth={1.5}
        className="text-(--color-text-tertiary-spec)"
      />
      <div className="text-[14px] font-medium">Page not found</div>
      <div className="max-w-md text-center text-[12.5px] text-(--color-text-tertiary-spec)">
        The page you tried to open doesn’t exist, or it has been moved.
      </div>
      <Button asChild variant="primary" size="sm">
        <Link href="/">Back to workspace</Link>
      </Button>
    </div>
  );
}
