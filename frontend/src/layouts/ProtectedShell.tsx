import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import { Outlet } from "react-router-dom";

import { AppHeader } from "@/components/app/AppHeader";
import { AppSidebar } from "@/components/app/AppSidebar";
import { Button } from "@/components/ui/button";
import { useCreateConversation } from "@/hooks/use-conversations";

export interface ChatShellContext {
  activeChatId: string | null;
  setActiveChatId: (conversationId: string | null) => void;
  onNewChat: () => void;
}

export function ProtectedShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const createMutation = useCreateConversation();

  const handleNewChat = useCallback(async () => {
    const created = await createMutation.mutateAsync();
    setActiveChatId(created.conversation_id);
  }, [createMutation]);

  const handleSelectConversation = useCallback((conversationId: string) => {
    setActiveChatId(conversationId);
  }, []);

  useEffect(() => {
    if (!sidebarOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSidebarOpen(false);
      }
    }
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [sidebarOpen]);

  const shellContext: ChatShellContext = {
    activeChatId,
    setActiveChatId,
    onNewChat: () => void handleNewChat(),
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <AppSidebar
        className="hidden lg:flex"
        collapsed={sidebarCollapsed}
        activeChatId={activeChatId}
        onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
        onNewChat={() => void handleNewChat()}
        onSelectConversation={handleSelectConversation}
      />
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-50 flex lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
        >
          <div
            className="docmind-drawer-overlay absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          <AppSidebar
            className="docmind-drawer relative z-10 h-full shadow-elevation-3"
            activeChatId={activeChatId}
            onNavigate={() => setSidebarOpen(false)}
            onNewChat={() => {
              void handleNewChat();
              setSidebarOpen(false);
            }}
            onSelectConversation={(conversationId) => {
              handleSelectConversation(conversationId);
              setSidebarOpen(false);
            }}
          />
          <Button
            variant="ghost"
            size="icon"
            className="absolute right-3 top-3 z-20 text-foreground hover:bg-accent hover:text-foreground lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation"
          >
            <X className="size-5" aria-hidden="true" />
          </Button>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader onMenuClick={() => setSidebarOpen(true)} />
        <main className="flex-1 overflow-y-auto">
          <Outlet context={shellContext} />
        </main>
      </div>
    </div>
  );
}
