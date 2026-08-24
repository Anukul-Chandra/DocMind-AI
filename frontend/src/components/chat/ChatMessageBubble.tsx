import { Sparkles } from "lucide-react";

import { ChatSources } from "@/components/chat/ChatSources";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";

interface ChatMessageBubbleProps {
  message: ChatMessage;
}

export function ChatMessageBubble({ message }: ChatMessageBubbleProps) {
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

  return (
    <div className="docmind-message flex flex-col items-start gap-2">
      <div className="w-full max-w-[85%] sm:max-w-[75%]">
        {/* System response panel */}
        <div
          className={cn(
            "relative overflow-hidden rounded-2xl border border-border/60 bg-card/70 shadow-elevation-1 backdrop-blur-md",
            "transition-all duration-200 hover:border-brand/25 hover:shadow-elevation-2",
          )}
        >
          {/* Header — identity + model telemetry */}
          <div className="flex items-center gap-2.5 border-b border-border/40 px-4 py-2.5">
            <span className="relative flex size-6 shrink-0 items-center justify-center rounded-md bg-brand/12 text-brand ring-1 ring-inset ring-brand-border/30">
              <Sparkles className="size-3" aria-hidden="true" />
            </span>
            <span className="text-sm font-semibold tracking-tight text-foreground">DocMind</span>
            <span
              className="docmind-label hidden shrink-0 rounded bg-brand/8 px-1.5 py-0.5 text-brand/85 sm:inline"
              aria-hidden="true"
            >
              Response
            </span>
            {(message.provider || message.model) && (
              <span
                className="docmind-label ml-auto min-w-0 truncate pl-3 text-muted-foreground/50"
                title={[message.provider, message.model].filter(Boolean).join(" / ")}
              >
                {[message.provider, message.model].filter(Boolean).join(" / ")}
              </span>
            )}
          </div>

          {/* Body */}
          <div className="relative px-5 py-4">
            <span
              className="absolute inset-y-0 left-0 w-0.5 bg-gradient-to-b from-brand/55 via-brand/15 to-transparent"
              aria-hidden="true"
            />
            <div className="whitespace-pre-wrap break-words pl-2.5 text-sm leading-relaxed text-foreground">
              {message.content}
            </div>
          </div>

          {/* Sources footer — RAG transparency stays attached to the answer */}
          {message.sources && message.sources.length > 0 ? (
            <div className="border-t border-border/40 bg-background/30">
              <ChatSources sources={message.sources} />
            </div>
          ) : (
            <div className="border-t border-border/40 px-4 py-2">
              <p className="docmind-label text-muted-foreground/40">No sources attached</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
