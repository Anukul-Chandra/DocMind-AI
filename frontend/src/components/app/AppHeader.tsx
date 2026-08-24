import { LogOut, Menu, User } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { pageTitles } from "@/components/app/nav-items";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

interface AppHeaderProps {
  onMenuClick: () => void;
}

export function AppHeader({ onMenuClick }: AppHeaderProps) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const title = pageTitles[location.pathname] ?? "DocMind AI";

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <header className="relative flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border/40 bg-background/60 backdrop-blur-2xl px-4 lg:px-6">
      {/* Subtle brand accent line */}
      <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-transparent via-brand/30 to-transparent pointer-events-none" aria-hidden="true" />

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
        <h1 className="truncate text-base font-semibold text-foreground">{title}</h1>
      </div>

      <div className="flex items-center gap-2">
        {/* Theme Toggle - Premium */}
        <ThemeToggle />

        {/* Account Button - Premium */}
        <div className="relative group">
          <button
            type="button"
            className={cn(
              "flex items-center gap-2 rounded-xl border border-border/50 bg-card/60 px-3 py-1.5 pr-4 transition-all duration-200",
              "hover:border-brand/30 hover:bg-card/80 hover:shadow-elevation-1",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
            )}
            aria-expanded="false"
            aria-haspopup="menu"
          >
            <span className="relative flex size-8 items-center justify-center rounded-xl bg-brand/10 text-brand ring-1 ring-brand-border/30 shadow-[0_0_0_1px_var(--color-brand-border)] transition-all duration-200 group-hover:bg-brand/15 group-hover:ring-brand/40 group-hover:shadow-brand/20">
              <User className="size-4" aria-hidden="true" />
              <span className="absolute bottom-0 right-0 size-2 rounded-full bg-green ring-2 ring-background" aria-hidden="true" />
            </span>
            <span className="hidden text-sm font-medium text-foreground sm:inline">Account</span>
            <span className="hidden sm:inline text-muted-foreground">▼</span>
          </button>
        </div>

        {/* Logout Button - Premium */}
        <Button
          variant="ghost"
          size="icon"
          onClick={handleLogout}
          aria-label="Sign out"
          className="hover:bg-brand/10 hover:text-brand text-muted-foreground transition-all duration-200"
        >
          <LogOut className="size-5" aria-hidden="true" />
        </Button>
      </div>
    </header>
  );
}