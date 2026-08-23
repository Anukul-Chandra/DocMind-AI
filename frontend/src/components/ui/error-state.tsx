import type { ReactNode } from "react";
import { AlertCircle } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  message: string;
  action?: ReactNode;
  className?: string;
}

export function ErrorState({ message, action, className }: ErrorStateProps) {
  return (
    <Card variant="glass" className={cn("gap-3 py-10 px-8 border-destructive/20", className)}>
      <CardContent className="flex flex-col items-center gap-4 px-6 text-center">
        <span className="flex size-14 items-center justify-center rounded-2xl bg-destructive/10 text-destructive ring-1 ring-destructive/20">
          <AlertCircle className="size-7" aria-hidden="true" />
        </span>
        <div className="space-y-1">
          <p className="text-lg font-semibold text-foreground">Something went wrong</p>
          <p className="max-w-md text-base text-muted-foreground">{message}</p>
        </div>
        {action && <div className="mt-2">{action}</div>}
      </CardContent>
    </Card>
  );
}