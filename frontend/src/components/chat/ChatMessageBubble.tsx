import { useCallback, useEffect, useState } from "react";
import { Sparkles, X } from "lucide-react";

import { ChatSources } from "@/components/chat/ChatSources";
import { ProgressiveText } from "@/components/chat/ProgressiveText";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";

interface ChatMessageBubbleProps {
  message: ChatMessage;
  /** Animate progressive reveal (only used for the newest assistant message). */
  animate?: boolean;
  onGrow?: () => void;
}

/** Left inset that aligns content with the sender name (avatar 24px + gap 10px). */
const CONTENT_INSET = "pl-[34px]";

export function ChatMessageBubble({ message, animate = false, onGrow }: ChatMessageBubbleProps) {
  // Sources appear only after the answer finishes revealing; static
  // (non-animated) messages show them immediately.
  const [sourcesVisible, setSourcesVisible] = useState(!animate);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);

  const closePreview = useCallback(() => setPreviewIndex(null), []);

  useEffect(() => {
    if (previewIndex === null) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") closePreview();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [previewIndex, closePreview]);

  const images = message.images && message.images.length > 0 ? message.images : null;

  if (message.role === "user") {
    return (
      <>
        <div className="docmind-message flex justify-end">
          <div className="flex max-w-[85%] flex-col items-end gap-1.5 sm:max-w-[75%]">
            <span className="docmind-label pr-1 text-muted-foreground/45" aria-hidden="true">
              Operator
            </span>
            {images && (
              <div className="flex gap-1.5">
                {images.map((url, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setPreviewIndex(i)}
                    className="size-20 shrink-0 cursor-zoom-in overflow-hidden rounded-lg border border-white/10 shadow-sm transition-opacity hover:opacity-80"
                  >
                    <img
                      src={url}
                      alt="Attached image"
                      className="size-full object-cover"
                    />
                  </button>
                ))}
              </div>
            )}
            <div className="whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-gradient-to-br from-brand to-brand-strong px-4 py-3 text-sm leading-relaxed text-brand-foreground shadow-[0_0_24px_-12px_var(--brand)]">
              {message.content}
            </div>
          </div>
        </div>

        {/* Full-size image preview modal */}
        {images && previewIndex !== null && (
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm"
            role="dialog"
            aria-label="Image preview"
            onClick={closePreview}
          >
            <button
              type="button"
              onClick={closePreview}
              className="absolute right-4 top-4 flex size-10 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20"
              aria-label="Close preview"
            >
              <X className="size-5" />
            </button>
            <img
              src={images[previewIndex]}
              alt="Full-size preview"
              className="max-h-[90vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        )}
      </>
    );
  }

  const modelMeta = [message.provider, message.model].filter(Boolean).join(" / ");
  const hasSources = Boolean(message.sources && message.sources.length > 0);

  return (
    <div className="docmind-message flex w-full max-w-[85%] flex-col gap-2 sm:max-w-[75%]">
      {/* Sender row — identity + model telemetry */}
      <div className="flex items-center gap-2.5">
        <span className="relative flex size-6 shrink-0 items-center justify-center rounded-md bg-brand/12 text-brand ring-1 ring-inset ring-brand-border/30">
          <Sparkles className="size-3" aria-hidden="true" />
        </span>
        <span className="text-sm font-semibold tracking-tight text-foreground">DocMind</span>
        {modelMeta && (
          <span className="docmind-label ml-auto min-w-0 truncate pl-3 text-muted-foreground/50" title={modelMeta}>
            {modelMeta}
          </span>
        )}
      </div>

      {/* Conversational body — open layout, no enclosing card */}
      <div className={CONTENT_INSET}>
        <ProgressiveText
          content={message.content}
          active={animate}
          onGrow={onGrow}
          onComplete={() => setSourcesVisible(true)}
        />
      </div>

      {/* Sources appear only after the answer finishes revealing, and only
          when the backend used retrieval for this answer */}
      {hasSources && sourcesVisible && (
        <div className={cn(CONTENT_INSET, "docmind-rise border-t border-border/40 pt-1")}>
          <ChatSources sources={message.sources!} />
        </div>
      )}
    </div>
  );
}
