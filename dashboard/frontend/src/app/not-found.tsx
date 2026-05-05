import Link from "next/link";
import { FileQuestion } from "lucide-react";

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
        The page you&apos;re looking for doesn&apos;t exist or has moved.
      </div>
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 rounded-md border border-(--color-border-default) px-3 py-1.5 text-[12.5px] text-(--color-text-primary) hover:bg-(--color-ghost-bg-hover)"
      >
        Go home
      </Link>
    </div>
  );
}
