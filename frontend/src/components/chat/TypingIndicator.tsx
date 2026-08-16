import { Sparkles } from "lucide-react";

export function TypingIndicator() {
  return (
    <div
      className="flex items-center gap-2 rounded-2xl rounded-tl-md border bg-card px-4 py-3 shadow-sm"
      role="status"
      aria-live="polite"
      aria-label="DocMind is thinking"
    >
      <Sparkles className="size-3.5 text-brand" aria-hidden="true" />
      <div className="flex items-center gap-1.5" aria-hidden="true">
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="size-2 animate-bounce rounded-full bg-brand/60"
            style={{ animationDelay: `${index * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}