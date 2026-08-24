import { Sparkles } from "lucide-react";

const EQ_DELAYS = ["0ms", "160ms", "320ms", "480ms"];

export function TypingIndicator() {
  return (
    <div
      className="docmind-message flex w-full max-w-[85%] flex-col gap-2 sm:max-w-[75%]"
      role="status"
      aria-live="polite"
      aria-label="DocMind is analyzing your documents and composing an answer"
    >
      {/* Sender row */}
      <div className="flex items-center gap-2.5">
        <span className="relative flex size-6 shrink-0 items-center justify-center rounded-md bg-brand/12 text-brand ring-1 ring-inset ring-brand-border/30">
          <span className="docmind-scan-pulse absolute inset-0 rounded-md bg-brand/15" aria-hidden="true" />
          <Sparkles className="relative size-3" aria-hidden="true" />
        </span>
        <span className="text-sm font-semibold tracking-tight text-foreground">DocMind</span>
        <span className="docmind-label ml-auto shrink-0 text-brand">Processing</span>
      </div>

      {/* Body — activity bars + response skeleton, aligned with answer content */}
      <div className="space-y-4 pl-[34px]">
        <div className="flex items-center gap-3">
          <span className="flex h-4 items-end gap-1" aria-hidden="true">
            {EQ_DELAYS.map((delay) => (
              <span
                key={delay}
                className="docmind-eq-bar h-full w-1 rounded-full bg-brand shadow-[0_0_6px_var(--brand)]"
                style={{ animationDelay: delay }}
              />
            ))}
          </span>
          <span className="text-sm text-muted-foreground">
            Analyzing your indexed documents…
          </span>
        </div>
        <div className="space-y-2.5" aria-hidden="true">
          <div className="docmind-skeleton h-3 w-11/12 rounded-full" />
          <div className="docmind-skeleton h-3 w-2/3 rounded-full" />
        </div>
      </div>
    </div>
  );
}
