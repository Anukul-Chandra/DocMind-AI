import { FileSearch, PanelLeftClose, PanelLeftOpen, Plus } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";

import { ConversationItem } from "@/components/chat/ConversationItem";
import { appNavItems } from "@/components/app/nav-items";
import { useConversations } from "@/hooks/use-conversations";
import type { ConversationMeta } from "@/types/conversations";
import { cn } from "@/lib/utils";

interface AppSidebarProps {
  className?: string;
  collapsed?: boolean;
  activeChatId?: string | null;
  onNavigate?: () => void;
  onToggleCollapsed?: () => void;
  onNewChat?: () => void;
  onSelectConversation?: (conversationId: string) => void;
}

export function AppSidebar({
  className,
  collapsed = false,
  activeChatId = null,
  onNavigate,
  onToggleCollapsed,
  onNewChat,
  onSelectConversation,
}: AppSidebarProps) {
  const location = useLocation();
  const isChatActive = location.pathname === "/app/chat";
  const { data: conversations = [], isLoading } = useConversations();

  return (
    <div
      className={cn(
        "flex shrink-0 flex-col transition-[width] duration-300 ease-out",
        "bg-background/70 border-r border-border/40 backdrop-blur-2xl",
        collapsed ? "w-16" : "w-68",
        className,
      )}
    >
      {/* Brand */}
      <div
        className={cn(
          "relative flex h-16 shrink-0 items-center gap-3 border-b border-border/40 px-4",
          collapsed && "justify-center",
        )}
      >
        <span
          className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-brand/25 via-transparent to-transparent"
          aria-hidden="true"
        />
        <span className="relative flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-brand-strong text-brand-foreground shadow-brand transition-shadow duration-300 hover:shadow-brand/45">
          <FileSearch className="size-4.5" aria-hidden="true" />
        </span>
        {!collapsed && (
          <span className="flex flex-col leading-tight">
            <span className="text-sm font-semibold tracking-tight text-foreground">DocMind AI</span>
            <span className="docmind-label text-[0.5625rem] text-muted-foreground">Document Intelligence</span>
          </span>
        )}
      </div>

      {/* Modules */}
      <nav
        className={cn(
          "flex flex-1 flex-col min-h-0 p-3",
          collapsed ? "items-stretch" : "",
        )}
        aria-label="Main navigation"
      >
        {!collapsed && (
          <p className="docmind-label mb-2 px-2 text-muted-foreground/60" aria-hidden="true">
            Modules
          </p>
        )}

        <div className="space-y-1">
          {appNavItems.map((item, index) => {
            return (
              <NavLink
                key={item.href}
                to={item.href}
                end={item.href === "/app"}
                onClick={onNavigate}
                title={item.title}
                aria-label={item.title}
                className={({ isActive }) =>
                  cn(
                    "docmind-nav-item group relative flex items-center gap-3 rounded-xl text-sm font-medium outline-none transition-colors duration-200",
                    "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                    collapsed ? "justify-center px-2 py-2.5" : "px-3 py-2.5",
                    isActive
                      ? "bg-brand-surface/90 text-brand ring-1 ring-inset ring-brand-border/40 shadow-[0_0_20px_-6px_var(--brand)]"
                      : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {/* Active module edge marker */}
                    <span
                      className={cn(
                        "absolute inset-y-[26%] left-0 w-0.5 rounded-full bg-brand shadow-[0_0_8px_var(--brand)] transition-opacity duration-300",
                        isActive ? "opacity-100" : "opacity-0",
                      )}
                      aria-hidden="true"
                    />
                    <span
                      className={cn(
                        "flex size-5 shrink-0 items-center justify-center transition-colors duration-200",
                        isActive
                          ? "text-brand drop-shadow-[0_0_6px_color-mix(in_oklab,var(--brand)_45%,transparent)]"
                          : "text-muted-foreground group-hover:text-brand/80",
                      )}
                      aria-hidden="true"
                    >
                      <item.icon className="size-4.5" />
                    </span>
                    {!collapsed && <span className="truncate">{item.title}</span>}
                    {!collapsed &&
                      (isActive ? (
                        <span
                          className="docmind-scan-pulse ml-auto size-1.5 shrink-0 rounded-full bg-brand shadow-[0_0_8px_var(--brand)]"
                          aria-hidden="true"
                        />
                      ) : (
                        <span
                          className="docmind-label ml-auto shrink-0 text-[0.5625rem] leading-none text-muted-foreground/45 transition-colors duration-200 group-hover:text-muted-foreground"
                          aria-hidden="true"
                        >
                          {String(index + 1).padStart(2, "0")}
                        </span>
                      ))}
                  </>
                )}
              </NavLink>
            );
          })}
        </div>

        {/* Chat history — visible directly under the Chat module while on the chat route */}
        {isChatActive && !collapsed && onNewChat && (
          <div className="mt-3 flex min-h-0 flex-1 flex-col gap-2">
            <button
              type="button"
              onClick={onNewChat}
              aria-label="New chat"
              className={cn(
                "group relative flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium outline-none transition-all duration-200",
                "border border-brand/30 bg-brand/8 text-brand",
                "hover:border-brand/50 hover:bg-brand/15 hover:shadow-[0_0_20px_-8px_var(--brand)]",
                "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              )}
            >
              <Plus
                className="size-4 shrink-0 transition-transform duration-200 group-hover:rotate-90"
                aria-hidden="true"
              />
              <span className="truncate">New chat</span>
            </button>

            <div
              className="docmind-label flex shrink-0 items-center gap-2 px-2 text-muted-foreground/45"
              aria-hidden="true"
            >
              <span className="h-px flex-1 bg-border/40" />
              <span>History</span>
              <span className="h-px flex-1 bg-border/40" />
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-0.5">
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
                        isActive={conversation.conversation_id === activeChatId}
                        onSelect={(id) => onSelectConversation?.(id)}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {/* Collapsed chat new-chat shortcut */}
        {isChatActive && collapsed && onNewChat && (
          <button
            type="button"
            onClick={onNewChat}
            aria-label="New chat"
            title="New chat"
            className={cn(
              "mx-auto mt-3 flex size-10 shrink-0 items-center justify-center rounded-xl text-brand outline-none transition-all duration-200",
              "border border-brand/30 bg-brand/8 hover:bg-brand/15 hover:border-brand/50",
              "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background",
            )}
          >
            <Plus className="size-4" aria-hidden="true" />
          </button>
        )}
      </nav>

      {/* Footer */}
      <div
        className={cn(
          "border-t border-border/40 p-3 transition-all duration-300",
          collapsed ? "flex justify-center" : "space-y-2",
        )}
      >
        {!collapsed && (
          <div className="docmind-panel relative rounded-xl p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="docmind-label relative flex items-center gap-2 text-brand">
                <span
                  className="docmind-scan-pulse size-1.5 shrink-0 rounded-full bg-brand shadow-[0_0_8px_var(--brand)]"
                  aria-hidden="true"
                />
                <span>RAG Core Online</span>
              </p>
              <span className="docmind-label text-muted-foreground/50" aria-hidden="true">
                OK
              </span>
            </div>
          </div>
        )}
        {onToggleCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "group relative flex items-center gap-2 rounded-xl text-sm font-medium outline-none transition-all duration-200",
              "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              collapsed
                ? "mx-auto flex size-10 items-center justify-center text-muted-foreground hover:bg-brand/10 hover:text-brand"
                : "w-full px-3 py-2 text-muted-foreground hover:bg-brand/8 hover:text-brand",
            )}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4.5 shrink-0" aria-hidden="true" />
            ) : (
              <>
                <PanelLeftClose
                  className="size-4.5 shrink-0 transition-transform duration-300 group-hover:-translate-x-0.5"
                  aria-hidden="true"
                />
                <span className="truncate">Collapse</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
