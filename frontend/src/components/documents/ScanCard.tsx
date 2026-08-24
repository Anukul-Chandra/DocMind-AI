import { Check, FileText, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

export interface PipelineStage {
  key: string;
  label: string;
}

/**
 * Real-state pipeline visualization.
 *
 * The backend processes a document in one atomic request, so individual
 * sub-stages (scanning, parsing, chunking, embedding, indexing) cannot be
 * observed separately. This panel therefore only claims what is actually
 * known:
 *  - "transmitting": bytes are still uploading — the upload node shows the
 *    real percentage from axios onUploadProgress.
 *  - "processing": the request is on the server — downstream nodes pulse as
 *    an active corridor without claiming individual completion.
 * Completion of every stage is only shown once the server has responded.
 */
interface ScanCardProps {
  fileName: string;
  stages: readonly PipelineStage[];
  phase: "transmitting" | "processing";
  uploadPercent: number;
}

export function ScanCard({ fileName, stages, phase, uploadPercent }: ScanCardProps) {
  const uploadDone = phase === "processing";

  return (
    <div
      className="docmind-panel relative overflow-hidden rounded-2xl"
      role="status"
      aria-live="polite"
      aria-label={`Processing ${fileName}`}
    >
      {/* Energy hairline */}
      <div
        className="docmind-scan-pulse absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/70 to-transparent"
        aria-hidden="true"
      />

      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border/40 px-5 py-3.5">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand ring-1 ring-inset ring-brand-border/30">
          <FileText className="size-4" aria-hidden="true" />
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground" title={fileName}>
          {fileName}
        </span>
        <span className="docmind-label shrink-0 text-brand">
          {phase === "transmitting" ? `Uplink ${uploadPercent}%` : "Pipeline Active"}
        </span>
      </div>

      <div className="grid gap-6 p-5 sm:grid-cols-[minmax(0,11rem)_1fr] sm:items-start sm:p-6">
        {/* Optical scan preview */}
        <div className="relative mx-auto w-full max-w-44 shrink-0 sm:mx-0">
          <div className="relative overflow-hidden rounded-xl border border-border/50 bg-gradient-to-br from-brand/4 via-card to-brand/4 p-5 shadow-elevation-1">
            <span className="absolute top-2 left-2 size-4 rounded-tl-md border-t border-l border-brand/45" aria-hidden="true" />
            <span className="absolute top-2 right-2 size-4 rounded-tr-md border-t border-r border-brand/45" aria-hidden="true" />
            <span className="absolute bottom-2 left-2 size-4 rounded-bl-md border-b border-l border-brand/45" aria-hidden="true" />
            <span className="absolute bottom-2 right-2 size-4 rounded-br-md border-b border-r border-brand/45" aria-hidden="true" />
            <div className="space-y-2" aria-hidden="true">
              <div className="h-2 w-3/4 rounded bg-brand/12" />
              <div className="h-2 w-full rounded bg-brand/6" />
              <div className="h-2 w-5/6 rounded bg-brand/6" />
              <div className="h-2 w-full rounded bg-brand/6" />
              <div className="h-2 w-2/3 rounded bg-brand/6" />
            </div>
            <div className="docmind-scan absolute inset-x-0 top-0 flex h-8 -translate-y-1/2 items-center justify-center">
              <div className="h-0.5 w-full rounded-full bg-gradient-to-r from-transparent via-brand/60 to-transparent" />
              <div className="absolute h-10 w-3/4 rounded-full bg-brand/15 blur-md" />
              <div className="docmind-scan-pulse absolute size-1.5 rounded-full bg-brand/90 blur-[2px]" />
            </div>
          </div>
          <p className="docmind-label mt-3 text-center text-muted-foreground/50" aria-hidden="true">
            Optical Scan
          </p>
        </div>

        {/* Pipeline rail */}
        <ol className="min-w-0" aria-label="Document processing pipeline">
          {stages.map((stage, index) => {
            const isFirst = index === 0;
            const isLast = index === stages.length - 1;
            const done = isFirst && uploadDone;
            const active = isFirst && !uploadDone;
            const flowing = !isFirst && uploadDone;

            return (
              <li key={stage.key} className="relative flex gap-3.5 pb-5 last:pb-0">
                {/* Connector */}
                {!isLast && (
                  <span
                    className={cn(
                      "absolute top-7 bottom-0 left-[13px] w-px overflow-hidden bg-border/50",
                      done && "bg-brand/40",
                    )}
                    aria-hidden="true"
                  >
                    {(phase === "processing" || (phase === "transmitting" && index === 0)) && (
                      <span className="docmind-energy-y absolute inset-x-0 top-0 h-5 bg-gradient-to-b from-transparent via-brand to-transparent" />
                    )}
                  </span>
                )}

                {/* Node */}
                <span
                  className={cn(
                    "relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border transition-all duration-300",
                    done &&
                      "border-brand bg-brand text-brand-foreground shadow-[0_0_12px_-2px_var(--brand)]",
                    active && "border-brand bg-brand/10 text-brand ring-4 ring-brand/15",
                    flowing && "border-brand/50 bg-card text-brand",
                    !done && !active && !flowing && "border-border bg-card text-muted-foreground/50",
                  )}
                >
                  {done ? (
                    <Check className="size-3.5" aria-hidden="true" />
                  ) : active ? (
                    <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <span
                      className={cn(
                        "rounded-full bg-current",
                        flowing ? "docmind-scan-pulse size-1.5" : "size-1",
                      )}
                      aria-hidden="true"
                    />
                  )}
                </span>

                {/* Label + status */}
                <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-0.5 pt-1">
                  <span
                    className={cn(
                      "text-sm transition-colors duration-300",
                      (done || active) && "font-medium text-foreground",
                      flowing && "text-foreground/85",
                      !done && !active && !flowing && "text-muted-foreground/60",
                    )}
                  >
                    {stage.label}
                  </span>
                  <span className="docmind-label ml-auto shrink-0 text-muted-foreground/55">
                    {active
                      ? `${uploadPercent}%`
                      : done
                        ? "Complete"
                        : flowing
                          ? ""
                          : "Queued"}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>

        {/* Aggregate status — the only claim we can honestly make mid-flight */}
        <p className="docmind-label col-span-full flex items-center gap-2 border-t border-border/40 pt-3 text-muted-foreground/60 sm:-mt-1">
          <span className="docmind-scan-pulse size-1.5 rounded-full bg-brand" aria-hidden="true" />
          {phase === "transmitting"
            ? "Streaming document to server…"
            : "Server executing pipeline — scanning, parsing, chunking, embedding, indexing"}
        </p>
      </div>
    </div>
  );
}
