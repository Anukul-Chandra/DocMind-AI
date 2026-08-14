import { LogOut } from "lucide-react";
import { Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";

export function ProtectedShell() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between border-b px-6">
        <span className="text-sm font-semibold">DocMind AI</span>
        <Button variant="ghost" size="sm" onClick={handleLogout}>
          <LogOut className="size-4" aria-hidden="true" />
          Logout
        </Button>
      </header>
      <main className="flex flex-1">
        <Outlet />
      </main>
    </div>
  );
}
