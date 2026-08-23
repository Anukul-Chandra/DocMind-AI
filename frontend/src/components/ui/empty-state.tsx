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
    <Card variant="glass" className={cn("gap-3 py-12 px-8", className)}>
      <CardContent className="flex flex-col items-center gap-4 px-6 text-center">
        {Icon && (
          <span className="flex size-14 items-center justify-center rounded-2xl bg-brand/10 text-brand ring-1 ring-brand-border/30 shadow-brand/10">
            <Icon className="size-7" aria-hidden="true" />
          </span>
        )}
        <div className="space-y-1">
          <p className="text-lg font-semibold text-foreground">{title}</p>
          {description && (
            <p className="max-w-md text-base text-muted-foreground">{description}</p>
          )}
        </div>
        {action && <div className="mt-2">{action}</div>}
      </CardContent>
    </Card>
  );
}