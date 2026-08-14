import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <Card className={cn("gap-2 py-10", className)}>
      <CardContent className="flex flex-col items-center gap-3 px-6 text-center">
        {Icon && (
          <span className="flex size-11 items-center justify-center rounded-full bg-muted">
            <Icon
              className="size-5 text-muted-foreground"
              aria-hidden="true"
            />
          </span>
        )}
        <p className="text-sm font-medium">{title}</p>
        {description && (
          <p className="max-w-md text-sm text-muted-foreground">{description}</p>
        )}
        {action && <div className="mt-1">{action}</div>}
      </CardContent>
    </Card>
  );
}
