import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      className={cn(
        "relative overflow-hidden rounded-xl transition-all duration-300",
        "hover:bg-brand/10 hover:text-brand",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
      )}
    >
      <span className="relative flex size-9 items-center justify-center rounded-xl">
        <span className="absolute inset-0 bg-gradient-to-br from-brand/10 via-transparent to-transparent opacity-0 transition-opacity duration-300" aria-hidden="true" />
        <span key={theme} className="relative docmind-theme-icon flex items-center justify-center">
          {isDark ? (
            <Sun className="size-4.5" aria-hidden="true" />
          ) : (
            <Moon className="size-4.5" aria-hidden="true" />
          )}
        </span>
      </span>
    </Button>
  );
}