import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Outlet } from "react-router-dom";

import { AppHeader } from "@/components/app/AppHeader";
import { AppSidebar } from "@/components/app/AppSidebar";
import { Button } from "@/components/ui/button";

export function ProtectedShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

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

  return (
    <div className="flex h-screen overflow-hidden">
      <AppSidebar className="hidden lg:flex" />
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-50 flex lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
        >
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          <AppSidebar
            className="relative z-10 h-full"
            onNavigate={() => setSidebarOpen(false)}
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
          <Outlet />
        </main>
      </div>
    </div>
  );
}
