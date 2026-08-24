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
      <nav className="flex-1 overflow-y-auto p-3" aria-label="Main navigation">
        {!collapsed && (
          <p className="docmind-label mb-2 px-2 text-muted-foreground/60" aria-hidden="true">
            Modules
          </p>
        )}
        <div className="space-y-1">
          {appNavItems.map((item, index) => (
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
          ))}
        </div>
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
