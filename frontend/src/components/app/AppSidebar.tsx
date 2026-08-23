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
        "flex shrink-0 flex-col transition-[width] duration-300 ease-out",
        "bg-card/60 border-r border-border/50 backdrop-blur-xl",
        collapsed ? "w-16" : "w-68",
        className,
      )}
    >
      {/* Logo / Brand */}
      <div
        className={cn(
          "flex h-16 shrink-0 items-center gap-3 border-b border-border/50 px-4",
          collapsed && "justify-center",
        )}
      >
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-brand-strong text-brand-foreground shadow-brand transition-all duration-300 hover:shadow-brand/30 hover:scale-[1.02]">
          <FileSearch className="size-4.5" aria-hidden="true" />
        </span>
        {!collapsed && (
          <span className="font-semibold text-foreground tracking-tight transition-opacity duration-200">
            DocMind AI
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3" aria-label="Main navigation">
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
                "group relative flex items-center gap-3 rounded-xl text-sm font-medium transition-all duration-200",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                collapsed ? "justify-center px-2 py-3" : "px-3 py-3",
                isActive
                  ? "bg-brand-surface text-brand shadow-brand/20 ring-1 ring-inset ring-brand-border/50"
                  : "text-muted-foreground hover:bg-brand/8 hover:text-foreground",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={cn(
                    "relative flex size-5 shrink-0 items-center justify-center transition-all duration-200",
                    isActive
                      ? "text-brand"
                      : "text-muted-foreground group-hover:text-brand/80",
                  )}
                  aria-hidden="true"
                >
                  <item.icon className="size-5" />
                  {isActive && !collapsed && (
                    <span className="absolute -right-3 top-1/2 -translate-y-1/2 size-1.5 rounded-full bg-brand animate-pulse" aria-hidden="true" />
                  )}
                </span>
                {!collapsed && <span className="truncate">{item.title}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div
        className={cn(
          "border-t border-border/50 p-3 transition-all duration-300",
          collapsed ? "flex justify-center" : "space-y-3",
        )}
      >
        {!collapsed && (
          <div className="relative rounded-xl p-3 bg-brand/5 border border-brand-border/30">
            <div className="absolute inset-0 bg-gradient-to-r from-brand/10 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 rounded-xl" aria-hidden="true" />
            <p className="relative flex items-center gap-2 text-xs font-medium text-brand">
              <span className="size-1.5 shrink-0 rounded-full bg-brand animate-pulse" aria-hidden="true" />
              <span>RAG-powered document analysis</span>
            </p>
          </div>
        )}
        {onToggleCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "group relative flex items-center gap-2 rounded-xl text-sm font-medium transition-all duration-200",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
              collapsed
                ? "size-10 justify-center mx-auto hover:bg-brand/10 text-muted-foreground"
                : "w-full px-3 py-2.5 hover:bg-brand/8 text-muted-foreground hover:text-brand",
            )}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4.5 shrink-0 text-current" aria-hidden="true" />
            ) : (
              <>
                <PanelLeftClose className="size-4.5 shrink-0 text-current group-hover:text-brand transition-colors" aria-hidden="true" />
                <span>Collapse sidebar</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}