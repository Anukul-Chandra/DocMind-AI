import { LogOut, Menu, User } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { pageTitles } from "@/components/app/nav-items";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useAuth } from "@/hooks/use-auth";

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
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b px-4 lg:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onMenuClick}
          aria-label="Open navigation"
        >
          <Menu className="size-5" aria-hidden="true" />
        </Button>
        <h1 className="truncate text-sm font-semibold">{title}</h1>
      </div>
      <div className="flex items-center gap-1">
        <ThemeToggle />
        <div className="flex items-center gap-2 rounded-full border bg-card/60 py-1 pl-1 pr-3">
          <span className="flex size-7 items-center justify-center rounded-full bg-brand/10">
            <User className="size-4 text-brand" aria-hidden="true" />
          </span>
          <span className="hidden text-sm font-medium sm:inline">Account</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleLogout}
          aria-label="Sign out"
        >
          <LogOut className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </header>
  );
}
