import { FileSearch, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { NavLink } from "react-router-dom";

import { appNavItems } from "@/components/app/nav-items";
import { cn } from "@/lib/utils";

interface AppSidebarProps {
  className?: string;
  collapsed?: boolean;
  onNavigate?: () => void;
  onToggleCollapsed?: () => void;
}

export function AppSidebar({
  className,
  collapsed = false,
  onNavigate,
  onToggleCollapsed,
}: AppSidebarProps) {
  return (
    <div
      className={cn(
        "flex shrink-0 flex-col border-r border-r-brand-border/60 bg-card/40 transition-[width] duration-200 ease-out",
        collapsed ? "w-16" : "w-64",
        className,
      )}
    >
      <div
        className={cn(
          "flex h-14 shrink-0 items-center gap-2.5 border-b",
          collapsed ? "justify-center px-0" : "px-5",
        )}
      >
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-strong text-brand-foreground shadow-brand">
          <FileSearch className="size-4" aria-hidden="true" />
        </span>
        {!collapsed && <span className="font-semibold">DocMind AI</span>}
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {appNavItems.map((item) => (
          <NavLink
            key={item.href}
            to={item.href}
            end={item.href === "/app"}
            onClick={onNavigate}
            title={item.title}
            aria-label={item.title}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-3 rounded-md text-sm font-medium transition-[background-color,color,box-shadow] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                collapsed ? "justify-center px-2 py-2" : "px-3 py-2",
                isActive
                  ? "bg-brand-surface text-brand shadow-brand ring-1 ring-inset ring-brand-border"
                  : "text-muted-foreground hover:bg-brand/[0.06] hover:text-foreground",
              )
            }
          >
            {({ isActive }) => (
              <>
                <item.icon
                  className={cn(
                    "size-4 shrink-0 transition-colors",
                    isActive
                      ? "text-brand"
                      : "text-muted-foreground group-hover:text-brand/70",
                  )}
                  aria-hidden="true"
                />
                {!collapsed && item.title}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div
        className={cn(
          "border-t p-3",
          collapsed ? "flex justify-center" : "space-y-3",
        )}
      >
        {!collapsed && (
          <p className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
            <span
              className="size-1.5 shrink-0 rounded-full bg-brand"
              aria-hidden="true"
            />
            RAG-powered document analysis
          </p>
        )}
        {onToggleCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "flex items-center gap-2 rounded-md text-sm text-muted-foreground transition-colors hover:bg-brand/[0.06] hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              collapsed ? "size-9 justify-center" : "w-full px-3 py-2",
            )}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4 shrink-0" aria-hidden="true" />
            ) : (
              <>
                <PanelLeftClose className="size-4 shrink-0" aria-hidden="true" />
                <span>Collapse sidebar</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}