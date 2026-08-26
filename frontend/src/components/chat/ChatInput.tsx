import { useRef, useState, useEffect, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";

import { cn } from "@/lib/utils";

const MAX_TEXTAREA_HEIGHT = 180;

interface ChatInputAttachment {
  id: string;
  previewUrl: string;
  file: File;
}

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [attachments, setAttachments] = useState<ChatInputAttachment[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Revoke object URLs when component unmounts
  useEffect(() => {
    return () => {
      attachments.forEach((a) => URL.revokeObjectURL(a.previewUrl));
    };
  }, [attachments]);

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue("");
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.overflowY = "hidden";
      textarea.style.height = `${Math.min(
        textarea.scrollHeight,
        MAX_TEXTAREA_HEIGHT
      )}px`;
      textarea.focus();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
    // Shift+Enter: default browser behavior inserts a newline (\n) into the
    // textarea since preventDefault() is only called for Enter without shift.
  }

  function handleChange(value: string) {
    setValue(value);
    const textarea = textareaRef.current;
    if (!textarea) return;

    let height = textarea.scrollHeight;
    if (height > MAX_TEXTAREA_HEIGHT) {
      height = MAX_TEXTAREA_HEIGHT;
      textarea.style.overflowY = "auto";
    } else {
      textarea.style.overflowY = "hidden";
    }
    textarea.style.height = `${height}px`;
  }

  function handlePaste(
    event: React.ClipboardEvent<HTMLTextAreaElement>
  ) {
    const items = event.clipboardData?.items;
    if (!items) return;

    // Check for image types among clipboard items
    const imageItems = Array.from(items).filter(
      (item) => item.type && item.type.startsWith("image/")
    );

    if (imageItems.length > 0) {
      event.preventDefault(); // Prevent raw file path from entering textarea

      // Use the first image item
      const imageItem = imageItems[0];
      const file = imageItem.getAsFile();

      if (file) {
        const id = `attachment-${Date.now()}-${Math.random()
          .toString(36)
          .substring(2, 9)}`;
        const previewUrl = URL.createObjectURL(file);

        setAttachments((prev) => [...prev, { id, previewUrl, file }]);
      }
    }
    // If no image items, let default paste behavior handle normal text
  }

  const hasValue = value.trim().length > 0 || attachments.length > 0;

  function handleClickAway() {
    textareaRef.current?.focus();
  }

  function removeAttachment(id: string) {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }

  return (
    <div className="w-full" onClick={handleClickAway}>
      {/* Image attachment previews — above input */}
      {attachments.length > 0 && (
        <div className="flex gap-2 pb-2">
          {attachments.map((attachment) => (
            <div
              key={attachment.id}
              className="group relative shrink-0 size-[64px] sm:size-[72px] rounded-xl bg-card/80 border border-border/40 p-0.5 backdrop-blur-sm hover:border-brand/20 transition-colors"
            >
              <img
                src={attachment.previewUrl}
                alt="Attachment preview"
                className="size-full rounded-[0.6rem] object-cover"
              />
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  removeAttachment(attachment.id);
                }}
                aria-label="Remove attachment"
                className="absolute -right-1.5 -top-1.5 flex size-5 items-center justify-center rounded-full border border-border/60 bg-card text-muted-foreground/60 opacity-0 shadow-sm transition-all hover:border-destructive/40 hover:text-destructive group-hover:opacity-100"
              >
                <svg className="size-2.5 text-white" aria-hidden="true">
                  <use href="/icons/minus.svg#x" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        className={cn(
          "relative flex items-end rounded-2xl bg-[#050807] border-2 border-brand/20 p-2.5 shadow-sm transition-colors",
          "focus-within:border-brand/50 focus-within:shadow-[0_0_32px_-14px_var(--brand)] focus-within:ring-3 focus-within:ring-brand/25",
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
          onPaste={handlePaste}
          rows={1}
          placeholder="Query the knowledge index…"
          aria-label="Your question"
          disabled={disabled}
          className="flex-1 resize-none bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-muted-foreground/70 disabled:cursor-not-allowed disabled:opacity-60 min-h-[48px]"
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
              ? "bg-brand text-brand-foreground shadow-md hover:shadow-brand/30 hover:brightness-110 active:brightness-105"
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