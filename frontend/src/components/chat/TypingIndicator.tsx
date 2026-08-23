import { Sparkles } from "lucide-react";

export function TypingIndicator() {
  return (
    <div
      className="flex items-center gap-2 rounded-2xl rounded-tl-md border border-brand-border/30 bg-card/80 px-4 py-3 shadow-sm shadow-brand/5 ring-1 ring-brand-border/20"
      role="status"
      aria-live="polite"
      aria-label="DocMind is thinking"
    >
      <span className="flex size-5 items-center justify-center rounded-full bg-brand/10 text-brand ring-1 ring-brand-border/30">
        <Sparkles className="size-3" aria-hidden="true" />
      </span>
      <div className="flex items-center gap-1" aria-hidden="true">
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="size-2 animate-bounce rounded-full bg-brand/70"
            style={{ animationDelay: `${index * 0.15}s` }}
          />
        ))}
      </div>
      <span className="text-xs text-brand/70 font-medium ml-1">Thinking…</span>
    </div>
  );
}