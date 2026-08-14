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
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground sm:max-w-[75%]">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <div className="flex max-w-[85%] flex-col gap-1 sm:max-w-[75%]">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Sparkles className="size-3.5" aria-hidden="true" />
          <span>DocMind</span>
        </div>
        <div
          className={cn(
            "whitespace-pre-wrap break-words rounded-2xl rounded-tl-md border bg-card px-4 py-3 text-sm leading-relaxed shadow-sm",
          )}
        >
          {message.content}
        </div>
        {(message.provider || message.model) && (
          <p className="text-xs text-muted-foreground">
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