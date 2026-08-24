import { Sparkles } from "lucide-react";

import { ChatSources } from "@/components/chat/ChatSources";
import { ProgressiveText } from "@/components/chat/ProgressiveText";
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
  if (message.role === "user") {
    return (
      <div className="docmind-message flex justify-end">
        <div className="flex max-w-[85%] flex-col items-end gap-1.5 sm:max-w-[75%]">
          <span className="docmind-label pr-1 text-muted-foreground/45" aria-hidden="true">
            Operator
          </span>
          <div className="whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-gradient-to-br from-brand to-brand-strong px-4 py-3 text-sm leading-relaxed text-brand-foreground shadow-[0_0_24px_-12px_var(--brand)]">
            {message.content}
          </div>
        </div>
      </div>
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
        <ProgressiveText content={message.content} active={animate} onGrow={onGrow} />
      </div>

      {/* Sources stay attached below the answer, visually separate from it */}
      <div className={CONTENT_INSET}>
        {hasSources ? (
          <div className="border-t border-border/40 pt-1">
            <ChatSources sources={message.sources!} />
          </div>
        ) : (
          <p className="docmind-label border-t border-border/40 pt-2.5 text-muted-foreground/40">
            No sources attached
          </p>
        )}
      </div>
    </div>
  );
}
