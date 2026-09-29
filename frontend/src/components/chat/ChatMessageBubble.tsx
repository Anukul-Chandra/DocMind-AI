import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Pencil, RotateCcw, Sparkles, X } from "lucide-react";

import { ChatSources } from "@/components/chat/ChatSources";
import { ProgressiveText } from "@/components/chat/ProgressiveText";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";

interface ChatMessageBubbleProps {
  message: ChatMessage;
  /** Animate progressive reveal (only used for the newest assistant message). */
  animate?: boolean;
  onGrow?: () => void;
  /** Regenerate the assistant response for this user message. */
  onRegenerate?: () => void;
  /** Save an edited user message and regenerate the response. */
  onSaveEdit?: (newContent: string) => void;
  /** True while any chat request is in flight; disables regenerate/edit. */
  actionsDisabled?: boolean;
}

/** Left inset that aligns content with the sender name (avatar 24px + gap 10px). */
const CONTENT_INSET = "pl-[34px]";

export function ChatMessageBubble({
  message,
  animate = false,
  onGrow,
  onRegenerate,
  onSaveEdit,
  actionsDisabled = false,
}: ChatMessageBubbleProps) {
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
      <UserMessageView
        message={message}
        images={images}
        previewIndex={previewIndex}
        setPreviewIndex={setPreviewIndex}
        closePreview={closePreview}
        onRegenerate={onRegenerate}
        onSaveEdit={onSaveEdit}
        actionsDisabled={actionsDisabled}
      />
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

/* ------------------------------------------------------------------ */
/* User message view with hover action toolbar + inline editing.        */
/* ------------------------------------------------------------------ */

interface UserMessageViewProps {
  message: ChatMessage;
  images: string[] | null;
  previewIndex: number | null;
  setPreviewIndex: (index: number) => void;
  closePreview: () => void;
  onRegenerate?: () => void;
  onSaveEdit?: (newContent: string) => void;
  actionsDisabled?: boolean;
}

function UserMessageView({
  message,
  images,
  previewIndex,
  setPreviewIndex,
  closePreview,
  onRegenerate,
  onSaveEdit,
  actionsDisabled = false,
}: UserMessageViewProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const [copied, setCopied] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const copyTimer = useRef<number | null>(null);

  useEffect(() => {
    if (!isEditing) setDraft(message.content);
  }, [message.content, isEditing]);

  useEffect(() => {
    if (isEditing) textareaRef.current?.focus();
  }, [isEditing]);

  useEffect(() => {
    return () => {
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
    };
  }, []);

  function startEdit() {
    if (actionsDisabled) return;
    setDraft(message.content);
    setIsEditing(true);
  }

  function cancelEdit() {
    setDraft(message.content);
    setIsEditing(false);
  }

  function saveEdit() {
    const text = draft.trim();
    if (!text || actionsDisabled) return;
    setIsEditing(false);
    if (text !== message.content) {
      onSaveEdit?.(text);
    }
  }

  async function copyText() {
    try {
      await navigator.clipboard.writeText(message.content);
    } catch {
      // Fallback for non-secure contexts: select via a temp textarea.
      const el = document.createElement("textarea");
      el.value = message.content;
      el.style.position = "fixed";
      el.style.opacity = "0";
      document.body.appendChild(el);
      el.select();
      document.execCommand("copy");
      document.body.removeChild(el);
    }
    setCopied(true);
    if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
    copyTimer.current = window.setTimeout(() => setCopied(false), 1500);
  }

  const canAct = !actionsDisabled && !isEditing;

  const iconButtonClass =
    "flex size-7 items-center justify-center rounded-lg text-muted-foreground/60 transition-colors hover:bg-muted/60 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-40 dark:text-muted-foreground/60 dark:hover:bg-white/10 dark:hover:text-foreground";

  return (
    <>
      <div className="docmind-message group flex justify-end">
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
                  className="size-20 shrink-0 cursor-zoom-in overflow-hidden rounded-lg border border-border/40 shadow-sm transition-opacity hover:opacity-80 dark:border-white/10"
                >
                  <img src={url} alt="Attached image" className="size-full object-cover" />
                </button>
              ))}
            </div>
          )}
          {isEditing ? (
            <div className="w-full min-w-[240px] rounded-2xl rounded-br-md border border-border/60 bg-card p-2.5 shadow-sm dark:border-white/10 dark:bg-[#101C18]">
              <textarea
                ref={textareaRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") cancelEdit();
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    saveEdit();
                  }
                }}
                rows={3}
                aria-label="Edit your message"
                disabled={actionsDisabled}
                className="max-h-48 min-h-20 w-full resize-y rounded-xl bg-transparent px-2.5 py-2 text-sm leading-relaxed text-foreground outline-none placeholder:text-muted-foreground/60 focus-visible:ring-2 focus-visible:ring-ring/40"
              />
              <div className="mt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="inline-flex h-8 items-center rounded-lg border border-border/70 bg-background/40 px-3 text-xs font-medium text-muted-foreground transition-colors hover:border-brand/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={saveEdit}
                  disabled={!draft.trim() || actionsDisabled}
                  className="inline-flex h-8 items-center rounded-lg bg-brand px-3 text-xs font-medium text-brand-foreground transition-all hover:bg-brand-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Save &amp; Regenerate
                </button>
              </div>
            </div>
          ) : (
            <div className="whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-gradient-to-br from-brand to-brand-strong px-4 py-3 text-sm leading-relaxed text-brand-foreground shadow-[0_0_24px_-12px_var(--brand)]">
              {message.content}
            </div>
          )}

          {/* Hover action toolbar — always visible on touch, hover/focus on desktop */}
          {!isEditing && (
            <div
              role="toolbar"
              aria-label="Message actions"
              className={cn(
                "flex items-center gap-0.5 pr-1 transition-opacity duration-150",
                "opacity-100",
                "md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 md:focus-within:opacity-100",
              )}
            >
              <button
                type="button"
                onClick={() => canAct && onRegenerate?.()}
                disabled={!canAct || !onRegenerate}
                title="Regenerate response"
                aria-label="Regenerate response"
                className={iconButtonClass}
              >
                <RotateCcw className="size-3.5" aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={startEdit}
                disabled={!canAct || !onSaveEdit}
                title="Edit message"
                aria-label="Edit message"
                className={iconButtonClass}
              >
                <Pencil className="size-3.5" aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={() => void copyText()}
                title={copied ? "Copied" : "Copy message"}
                aria-label={copied ? "Copied" : "Copy message"}
                aria-live="polite"
                className={iconButtonClass}
              >
                {copied ? (
                  <Check className="size-3.5 text-brand" aria-hidden="true" />
                ) : (
                  <Copy className="size-3.5" aria-hidden="true" />
                )}
              </button>
              <span
                aria-live="polite"
                className={cn(
                  "docmind-label text-muted-foreground/60 transition-opacity",
                  copied ? "opacity-100" : "sr-only opacity-0",
                )}
              >
                Copied
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Full-size image preview modal */}
      {images && previewIndex !== null && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm dark:bg-black/80"
          role="dialog"
          aria-label="Image preview"
          onClick={closePreview}
        >
          <button
            type="button"
            onClick={closePreview}
            className="absolute right-4 top-4 flex size-10 items-center justify-center rounded-full bg-muted/30 text-foreground transition-colors hover:bg-muted/40 dark:bg-white/10 dark:text-white dark:hover:bg-white/20"
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
