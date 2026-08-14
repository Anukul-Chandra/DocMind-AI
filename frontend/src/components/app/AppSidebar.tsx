import { FileSearch } from "lucide-react";
import { NavLink } from "react-router-dom";

import { appNavItems } from "@/components/app/nav-items";
import { cn } from "@/lib/utils";

interface AppSidebarProps {
  className?: string;
  onNavigate?: () => void;
}

export function AppSidebar({ className, onNavigate }: AppSidebarProps) {
  return (
    <div
      className={cn(
        "flex w-64 shrink-0 flex-col border-r bg-card/40",
        className,
      )}
    >
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-6">
        <FileSearch className="size-5" aria-hidden="true" />
        <span className="font-semibold">DocMind AI</span>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {appNavItems.map((item) => (
          <NavLink
            key={item.href}
            to={item.href}
            end={item.href === "/app"}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )
            }
          >
            <item.icon className="size-4 shrink-0" aria-hidden="true" />
            {item.title}
          </NavLink>
        ))}
      </nav>
      <div className="border-t p-4 text-xs text-muted-foreground">
        RAG-powered document analysis
      </div>
    </div>
  );
}
