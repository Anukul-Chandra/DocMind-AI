import { useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";

import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.focus();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  function handleChange(value: string) {
    setValue(value);
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
    }
  }

  const hasValue = value.trim().length > 0;

  return (
    <div className="w-full">
      <div
        className={cn(
          "relative flex items-end gap-2 rounded-2xl border border-border/60 bg-card/50 p-2 shadow-elevation-1 backdrop-blur-xl transition-all duration-200",
          "focus-within:border-brand/45 focus-within:shadow-[0_0_32px_-14px_var(--brand)] focus-within:ring-2 focus-within:ring-brand/15",
          hasValue && !disabled && "border-brand/30",
        )}
      >
        {/* Focus accent hairline */}
        <span
          className="pointer-events-none absolute inset-x-4 top-0 h-px bg-gradient-to-r from-transparent via-brand/50 to-transparent opacity-0 transition-opacity duration-300 focus-within:opacity-100"
          aria-hidden="true"
        />
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => handleChange(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Query the knowledge index…"
          aria-label="Your question"
          disabled={disabled}
          autoFocus
          className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-muted-foreground/70 disabled:cursor-not-allowed disabled:opacity-60"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !hasValue}
          aria-label="Send question"
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-xl transition-all duration-200",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background",
            hasValue && !disabled
              ? "bg-brand text-brand-foreground shadow-brand hover:shadow-brand/50 hover:brightness-105 active:brightness-95"
              : "bg-muted text-muted-foreground/60",
          )}
        >
          <ArrowUp className="size-4.5" aria-hidden="true" />
        </button>
      </div>
      <p className="docmind-label mt-2 text-center text-muted-foreground/55">
        Enter to transmit · Shift+Enter for a new line
      </p>
    </div>
  );
}
