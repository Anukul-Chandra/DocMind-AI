import { ChevronDown, LogOut, Menu, User } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { pageTitles } from "@/components/app/nav-items";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

export function AppHeader({ onMenuClick }: { onMenuClick: () => void }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const title = pageTitles[location.pathname] ?? "DocMind AI";

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="relative flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border/40 bg-background/60 px-4 backdrop-blur-2xl lg:px-6">
      {/* Emerald accent hairline */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/35 to-transparent"
        aria-hidden="true"
      />

      {/* Locator */}
      <div className="flex min-w-0 items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="hover:bg-brand/10 hover:text-brand lg:hidden"
          onClick={onMenuClick}
          aria-label="Open navigation"
        >
          <Menu className="size-5" aria-hidden="true" />
        </Button>
        <div className="flex min-w-0 items-baseline gap-2.5">
          <span
            className="docmind-label hidden shrink-0 text-muted-foreground/55 md:inline"
            aria-hidden="true"
          >
            DOCMIND
          </span>
          <span
            className="hidden select-none text-muted-foreground/35 md:inline"
            aria-hidden="true"
          >
            /
          </span>
          <h1 className="truncate text-base font-semibold tracking-tight text-foreground">
            {title}
          </h1>
        </div>
      </div>

      {/* Command cluster */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 rounded-xl border border-border/50 bg-card/50 p-1 shadow-[inset_0_1px_0_oklch(1_0_0/4%)] backdrop-blur-md">
          <ThemeToggle />

          <span className="h-5 w-px bg-border/60" aria-hidden="true" />

          <button
            type="button"
            className={cn(
              "group flex items-center gap-2 rounded-lg py-1 pl-1.5 pr-2 outline-none transition-all duration-200",
              "hover:bg-brand/8 focus-visible:ring-2 focus-visible:ring-brand",
            )}
            aria-expanded="false"
            aria-haspopup="menu"
            aria-label="Account"
          >
            <span className="relative flex size-7 items-center justify-center rounded-lg bg-brand/12 text-brand ring-1 ring-inset ring-brand/25 transition-all duration-200 group-hover:bg-brand/18 group-hover:shadow-[0_0_12px_-2px_var(--brand)]">
              <User className="size-3.5" aria-hidden="true" />
              <span
                className="docmind-scan-pulse absolute -bottom-0.5 -right-0.5 size-2 rounded-full bg-brand shadow-[0_0_6px_var(--brand)] ring-2 ring-card"
                aria-hidden="true"
              />
            </span>
            <span className="hidden text-sm font-medium text-foreground sm:inline">Account</span>
            <ChevronDown
              className="hidden size-3.5 text-muted-foreground transition-all duration-200 group-hover:translate-y-px group-hover:text-brand sm:inline"
              aria-hidden="true"
            />
          </button>

          <span className="h-5 w-px bg-border/60" aria-hidden="true" />

          <Button
            variant="ghost"
            size="icon"
            className="size-9 rounded-lg text-muted-foreground hover:bg-brand/10 hover:text-brand"
            onClick={handleLogout}
            aria-label="Sign out"
          >
            <LogOut className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </header>
  );
}
