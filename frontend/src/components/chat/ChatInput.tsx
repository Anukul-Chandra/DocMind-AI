import { useState, type KeyboardEvent } from "react";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div>
      <div className="flex items-end gap-2 rounded-xl border bg-card p-2 shadow-sm">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Ask a question about your documents…"
          aria-label="Your question"
          disabled={disabled}
          autoFocus
          className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60"
        />
        <Button
          type="button"
          size="icon"
          onClick={submit}
          disabled={disabled || !value.trim()}
          aria-label="Send question"
        >
          <Send className="size-4" aria-hidden="true" />
        </Button>
      </div>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        Enter to send · Shift+Enter for a new line
      </p>
    </div>
  );
}