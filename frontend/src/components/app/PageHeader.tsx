import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, description, action, className }: PageHeaderProps) {
  return (
    <div className={cn("space-y-1.5 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3", className)}>
      <div>
        <h1 className="text-2xl lg:text-3xl font-semibold tracking-tight text-foreground">{title}</h1>
        {description && (
          <p className="text-base text-muted-foreground mt-0.5">{description}</p>
        )}
      </div>
      {action && (
        <div className="flex-shrink-0 mt-2 sm:mt-0">{action}</div>
      )}
    </div>
  );
}