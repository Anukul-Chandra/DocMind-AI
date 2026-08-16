import { Check, FileText, Loader2 } from "lucide-react";

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
      className="overflow-hidden rounded-xl border bg-card/40"
      role="status"
      aria-label={`Processing ${fileName}`}
    >
      <div className="flex items-center gap-2 border-b px-5 py-3 text-sm">
        <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span className="truncate font-medium">{fileName}</span>
      </div>
      <div className="grid gap-5 p-5 sm:grid-cols-[auto_1fr] sm:items-center sm:gap-6 sm:p-6">
        <div className="relative mx-auto w-44 shrink-0 sm:mx-0">
          <div className="relative overflow-hidden rounded-md border bg-white p-5 shadow-sm">
            <span
              className="absolute top-1.5 left-1.5 size-3 rounded-tl border-t-2 border-l-2 border-brand"
              aria-hidden="true"
            />
            <span
              className="absolute top-1.5 right-1.5 size-3 rounded-tr border-t-2 border-r-2 border-brand"
              aria-hidden="true"
            />
            <span
              className="absolute bottom-1.5 left-1.5 size-3 rounded-bl border-b-2 border-l-2 border-brand"
              aria-hidden="true"
            />
            <span
              className="absolute right-1.5 bottom-1.5 size-3 rounded-br border-r-2 border-b-2 border-brand"
              aria-hidden="true"
            />
            <div className="space-y-2" aria-hidden="true">
              <div className="h-2 w-3/4 rounded bg-slate-200" />
              <div className="h-2 w-full rounded bg-slate-100" />
              <div className="h-2 w-5/6 rounded bg-slate-100" />
              <div className="h-2 w-full rounded bg-slate-100" />
              <div className="h-2 w-2/3 rounded bg-slate-100" />
            </div>
            <div className="docmind-scan absolute inset-x-0 top-0 flex h-8 -translate-y-1/2 items-center justify-center">
              <div className="h-0.5 w-full rounded-full bg-gradient-to-r from-transparent via-brand to-transparent" />
              <div className="absolute h-8 w-3/4 rounded-full bg-brand/20 blur-md" />
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
                    "flex size-5 shrink-0 items-center justify-center rounded-full border",
                    done && "border-brand bg-brand/10 text-brand",
                    active && "border-brand/40 bg-brand/10 text-brand",
                    !done && !active && "border-border text-muted-foreground",
                  )}
                >
                  {done ? (
                    <Check className="size-3" aria-hidden="true" />
                  ) : active ? (
                    <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                  ) : (
                    <span className="size-1 rounded-full bg-current" aria-hidden="true" />
                  )}
                </span>
                <span
                  className={cn(
                    done && "text-muted-foreground",
                    active && "font-medium",
                  )}
                >
                  {stage.label}
                </span>
                {active && (
                  <span className="ml-auto h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                    <span className="docmind-scan-pulse block h-full w-2/3 rounded-full bg-brand" />
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