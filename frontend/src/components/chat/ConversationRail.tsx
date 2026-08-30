import { MessageSquarePlus, PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { ConversationItem } from "@/components/chat/ConversationItem";
import { Button } from "@/components/ui/button";
import { useConversations } from "@/hooks/use-conversations";
import type { ConversationMeta } from "@/types/conversations";
import { cn } from "@/lib/utils";

export function ConversationRail({
  activeId,
  collapsed,
  onSelect,
  onToggleCollapsed,
  onNewChat,
}: {
  activeId: string | null;
  collapsed: boolean;
  onSelect: (conversationId: string) => void;
  onToggleCollapsed: () => void;
  onNewChat: () => void;
}) {
  const { data: conversations = [], isLoading } = useConversations();

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-white/[0.06] bg-[#0C110F] transition-[width] duration-200",
        collapsed ? "w-12" : "w-64",
      )}
    >
      <div className="flex items-center justify-between gap-2 px-3 pt-3 pb-2">
        {!collapsed && (
          <Button
            type="button"
            onClick={onNewChat}
            variant="outline"
            size="sm"
            className="h-8 flex-1 justify-start gap-2 border-brand/30 text-brand hover:bg-brand/10"
          >
            <MessageSquarePlus className="size-4" aria-hidden="true" />
            New chat
          </Button>
        )}
        <Button
          type="button"
          onClick={onToggleCollapsed}
          variant="ghost"
          size="icon"
          className="size-8 shrink-0 text-muted-foreground hover:text-foreground"
          aria-label={collapsed ? "Expand chat list" : "Collapse chat list"}
        >
          {collapsed ? (
            <PanelLeftOpen className="size-4" aria-hidden="true" />
          ) : (
            <PanelLeftClose className="size-4" aria-hidden="true" />
          )}
        </Button>
      </div>

      {collapsed ? (
        <div className="flex flex-col items-center gap-1 pt-1">
          <Button
            type="button"
            onClick={onNewChat}
            variant="ghost"
            size="icon"
            className="size-8 text-brand"
            aria-label="New chat"
          >
            <MessageSquarePlus className="size-4" aria-hidden="true" />
          </Button>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto overscroll-contain px-2 pb-3">
          {isLoading ? (
            <p className="px-2 py-2 text-xs text-muted-foreground/60">
              Loading conversations…
            </p>
          ) : conversations.length === 0 ? (
            <p className="px-2 py-2 text-xs text-muted-foreground/60">
              No conversations yet. Start a new chat.
            </p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {conversations.map((conversation: ConversationMeta) => (
                <li key={conversation.conversation_id}>
                  <ConversationItem
                    conversation={conversation}
                    isActive={conversation.conversation_id === activeId}
                    onSelect={onSelect}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </aside>
  );
}
