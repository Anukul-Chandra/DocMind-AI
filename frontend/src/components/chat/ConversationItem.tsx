import { MessageSquare } from "lucide-react";

import { DeleteConversationDialog } from "@/components/chat/DeleteConversationDialog";
import { RenameConversationDialog } from "@/components/chat/RenameConversationDialog";
import type { ConversationMeta } from "@/types/conversations";
import { cn } from "@/lib/utils";

export function ConversationItem({
  conversation,
  isActive,
  onSelect,
}: {
  conversation: ConversationMeta;
  isActive: boolean;
  onSelect: (conversationId: string) => void;
}) {
  const title = conversation.title?.trim() || "New chat";

  return (
    <div
      data-active={isActive || undefined}
      className={cn(
        "group relative flex w-full items-center gap-2 rounded-lg border border-transparent px-2 py-1.5 text-left transition-colors duration-150",
        isActive
          ? "bg-brand/10 text-foreground"
          : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
      )}
    >
      <button
        type="button"
        onClick={() => onSelect(conversation.conversation_id)}
        className="flex min-w-0 flex-1 items-center gap-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
        aria-current={isActive ? "page" : undefined}
        aria-label={`Open chat: ${title}`}
      >
        <MessageSquare
          className={cn(
            "size-3.5 shrink-0",
            isActive ? "text-brand" : "text-muted-foreground/60",
          )}
          aria-hidden="true"
        />
        <span className="truncate text-xs">{title}</span>
      </button>

      {isActive && (
        <div
          className="flex shrink-0 items-center gap-0.5"
          onClick={(event) => event.stopPropagation()}
        >
          <RenameConversationDialog
            conversationId={conversation.conversation_id}
            title={title}
          />
          <DeleteConversationDialog
            conversationId={conversation.conversation_id}
            title={title}
          />
        </div>
      )}
    </div>
  );
}
