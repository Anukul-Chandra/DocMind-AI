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
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <div
        className={cn(
          "max-w-[85%] rounded-2xl border bg-card px-4 py-3 shadow-sm",
        )}
      >
        <p className="whitespace-pre-wrap text-sm leading-relaxed">
          {message.content}
        </p>
        {(message.provider || message.model) && (
          <p className="mt-2 text-xs text-muted-foreground">
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