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
    <Card className={cn("gap-2 py-10", className)}>
      <CardContent className="flex flex-col items-center gap-3 px-6 text-center">
        <span className="flex size-11 items-center justify-center rounded-full bg-destructive/10">
          <AlertCircle
            className="size-5 text-destructive"
            aria-hidden="true"
          />
        </span>
        <p className="max-w-md text-sm text-muted-foreground">{message}</p>
        {action && <div className="mt-1">{action}</div>}
      </CardContent>
    </Card>
  );
}
