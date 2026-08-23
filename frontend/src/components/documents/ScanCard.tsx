import { Check, FileText, Loader2, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export interface UploadStage {
  key: string;
  label: string;
}

interface ScanCardProps {
  fileName: string;
  stages: readonly UploadStage[];
  activeStage: number;
}

export function ScanCard({ fileName, stages, activeStage }: ScanCardProps) {
  return (
    <div
      className="overflow-hidden rounded-xl border border-brand-border/30 bg-card/40 shadow-brand/5"
      role="status"
      aria-label={`Processing ${fileName}`}
    >
      <div className="flex items-center gap-2 border-b border-brand-border/20 px-5 py-3 text-sm">
        <FileText className="size-4 shrink-0 text-brand/70" aria-hidden="true" />
        <span className="truncate font-medium text-foreground">{fileName}</span>
        <span className="ml-auto flex items-center gap-1 text-xs text-brand/70">
          <Sparkles className="size-3 docmind-scan-pulse" aria-hidden="true" />
          AI analyzing
        </span>
      </div>
      <div className="grid gap-5 p-5 sm:grid-cols-[auto_1fr] sm:items-center sm:gap-6 sm:p-6">
        <div className="relative mx-auto w-44 shrink-0 sm:mx-0">
          <div className="relative overflow-hidden rounded-lg border border-brand-border/30 bg-gradient-to-br from-brand/2 via-card to-brand/2 p-5 shadow-brand/10">
            <span
              className="absolute top-2 left-2 size-4 rounded-tl border-t-2 border-l-2 border-brand/50"
              aria-hidden="true"
            />
            <span
              className="absolute top-2 right-2 size-4 rounded-tr border-t-2 border-r-2 border-brand/50"
              aria-hidden="true"
            />
            <span
              className="absolute bottom-2 left-2 size-4 rounded-bl border-b-2 border-l-2 border-brand/50"
              aria-hidden="true"
            />
            <span
              className="absolute bottom-2 right-2 size-4 rounded-br border-r-2 border-b-2 border-brand/50"
              aria-hidden="true"
            />
            <div className="space-y-2" aria-hidden="true">
              <div className="h-2 w-3/4 rounded bg-brand/10" />
              <div className="h-2 w-full rounded bg-brand/5" />
              <div className="h-2 w-5/6 rounded bg-brand/5" />
              <div className="h-2 w-full rounded bg-brand/5" />
              <div className="h-2 w-2/3 rounded bg-brand/5" />
            </div>
            <div className="docmind-scan absolute inset-x-0 top-0 flex h-8 -translate-y-1/2 items-center justify-center">
              <div className="h-0.5 w-full rounded-full bg-gradient-to-r from-transparent via-brand/60 to-transparent" />
              <div className="absolute h-10 w-3/4 rounded-full bg-brand/15 blur-md" />
              <div className="absolute h-1.5 w-1.5 rounded-full bg-brand/80 blur-sm animate-pulse" />
            </div>
          </div>
        </div>

        <ol className="space-y-2.5" aria-label="Document processing steps">
          {stages.map((stage, index) => {
            const done = index < activeStage;
            const active = index === activeStage;
            return (
              <li
                key={stage.key}
                className={cn(
                  "flex items-center gap-3 text-sm",
                  !done && !active && "opacity-60",
                )}
              >
                <span
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-full border transition-all duration-200",
                    done && "border-brand bg-brand/10 text-brand shadow-[0_0_0_1px_var(--color-brand-border)]",
                    active && "border-brand bg-brand/15 text-brand shadow-brand/20 ring-1 ring-brand/20",
                    !done && !active && "border-border text-muted-foreground",
                  )}
                >
                  {done ? (
                    <Check className="size-3" aria-hidden="true" />
                  ) : active ? (
                    <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                  ) : (
                    <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                  )}
                </span>
                <span
                  className={cn(
                    done && "text-muted-foreground",
                    active && "font-medium text-foreground",
                  )}
                >
                  {stage.label}
                </span>
                {active && (
                  <span className="ml-auto h-1.5 w-20 overflow-hidden rounded-full bg-brand/10">
                    <span className="docmind-scan-pulse block h-full w-1/2 rounded-full bg-brand" />
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}