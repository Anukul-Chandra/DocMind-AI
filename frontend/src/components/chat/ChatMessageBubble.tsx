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
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-brand px-4 py-3 text-sm text-brand-foreground shadow-brand/20 sm:max-w-[75%]">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="docmind-message flex flex-col items-start gap-2">
      <div className="flex max-w-[85%] flex-col gap-1.5 sm:max-w-[75%]">
        <div className="flex items-center gap-2 text-xs">
          <span className="flex size-6 items-center justify-center rounded-full bg-brand/10 text-brand ring-1 ring-brand-border/30 shadow-brand/10">
            <Sparkles className="size-3" aria-hidden="true" />
          </span>
          <span className="font-medium text-foreground">DocMind</span>
        </div>
        <div
          className={cn(
            "relative whitespace-pre-wrap break-words rounded-2xl rounded-tl-md bg-card px-5 py-3.5 text-sm leading-relaxed shadow-elevation-1 transition-all duration-200",
            "border border-border/50 hover:shadow-elevation-2 hover:border-brand/20",
          )}
        >
          <div className="prose prose-sm max-w-none text-foreground">
            {message.content}
          </div>
        </div>
        {(message.provider || message.model) && (
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-brand/30" aria-hidden="true" />
            {[message.provider, message.model].filter(Boolean).join(" · ")}
          </p>
        )}
      </div>
      {message.sources && message.sources.length > 0 && (
        <ChatSources sources={message.sources} />
      )}
    </div>
  );
}