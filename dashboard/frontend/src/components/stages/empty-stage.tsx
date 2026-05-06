import * as React from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

export function EmptyStage({
  title,
  description,
  icon: Icon = Sparkles,
  onGenerate,
}: {
  title: string;
  description: string;
  icon?: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  onGenerate?: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col lg:flex-row">
      <main className="flex-1 flex flex-col items-center justify-center gap-3 px-5 py-10 sm:px-6">
        <div className="size-12 rounded-full bg-(--color-ghost-bg) hairline-r hairline-l hairline-t hairline-b flex items-center justify-center">
          <Icon size={20} strokeWidth={1.5} className="text-(--color-text-tertiary)" />
        </div>
        <h2 className="font-h1 text-center">{title}</h2>
        <p className="text-[13.5px] text-(--color-text-tertiary) max-w-md text-center leading-[1.6]">
          {description}
        </p>
        <div className="mt-4 flex max-w-full flex-wrap justify-center gap-2">
          <Button variant="primary" size="md" onClick={onGenerate}>
            <Sparkles size={13} strokeWidth={1.5} />
            Generate
          </Button>
          <Button variant="ghost" size="md">
            Upload
          </Button>
        </div>
      </main>
      <aside className="w-full border-t border-(--color-border-standard) bg-(--color-bg-marketing) p-4 lg:w-[320px] lg:border-l lg:border-t-0">
        <h3 className="font-label">This stage is empty</h3>
        <p className="text-[12px] text-(--color-text-tertiary) mt-2 leading-[1.6]">
          Run a generation to populate this stage, or upload a markdown file via{" "}
          <code className="font-mono text-[11.5px] text-(--color-text-secondary) px-1 py-0.5 rounded bg-(--color-ghost-bg)">
            Plato.set_*()
          </code>{" "}
          equivalent in the UI.
        </p>
      </aside>
    </div>
  );
}
