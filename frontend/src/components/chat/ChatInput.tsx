import { useRef, useState, type KeyboardEvent } from "react";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
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
          "relative flex items-end gap-2 rounded-2xl bg-card/60 border border-border/50 p-2 shadow-elevation-1 backdrop-blur-xl transition-all duration-200",
          "focus-within:border-brand/40 focus-within:ring-2 focus-within:ring-brand/20 focus-within:ring-offset-0 focus-within:shadow-brand/15",
          hasValue && "border-brand/30",
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => handleChange(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Ask a question about your documents…"
          aria-label="Your question"
          disabled={disabled}
          autoFocus
          className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
        />
        <div className="relative flex items-center justify-center">
          <Button
            type="button"
            size="icon"
            onClick={submit}
            disabled={disabled || !hasValue}
            aria-label="Send question"
            variant={hasValue ? "default" : "ghost"}
            className={cn(
              "transition-all duration-200",
              hasValue ? "shadow-brand hover:shadow-brand/30" : "text-muted-foreground hover:text-brand hover:bg-brand/10",
              disabled && "opacity-50",
            )}
          >
            <Send className="size-4.5" aria-hidden="true" />
          </Button>
        </div>
      </div>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        Enter to send · Shift+Enter for a new line
      </p>
    </div>
  );
}