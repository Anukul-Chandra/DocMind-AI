import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  kicker?: string;
  action?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, description, kicker, action, className }: PageHeaderProps) {
  return (
    <div className={cn("space-y-1.5 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3", className)}>
      <div>
        {kicker && (
          <p className="docmind-label mb-2 flex items-center gap-2 text-muted-foreground/60" aria-hidden="true">
            <span className="size-1 rounded-full bg-brand/70" aria-hidden="true" />
            {kicker}
          </p>
        )}
        <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description && (
          <p className="text-base text-muted-foreground mt-0.5 max-w-2xl">{description}</p>
        )}
      </div>
      {action && (
        <div className="flex-shrink-0 mt-2 sm:mt-0">{action}</div>
      )}
    </div>
  );
}
