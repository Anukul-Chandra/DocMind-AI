import {
  ArrowRight,
  FileText,
  MessagesSquare,
  Sparkles,
  UploadCloud,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/app/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useCountUp } from "@/hooks/use-count-up";
import { useDocuments } from "@/hooks/use-documents";
import { cn } from "@/lib/utils";

function AnimatedNumber({ value }: { value: number }) {
  const count = useCountUp(value);
  return <>{count}</>;
}

interface OverviewCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  value: string | number;
  hint: string;
  to: string;
  action: string;
  delay?: number;
}

function OverviewCard({
  icon: Icon,
  title,
  description,
  value,
  hint,
  to,
  action,
  delay = 0,
}: OverviewCardProps) {
  return (
    <Card className="docmind-rise gap-5" style={{ animationDelay: `${delay}ms` }}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <span className="flex size-10 items-center justify-center rounded-lg bg-brand/10 text-brand ring-1 ring-brand-border/30 shadow-[0_0_0_1px_var(--color-brand-border)]">
            <Icon className="size-5" aria-hidden="true" />
          </span>
          <Button asChild size="icon" variant="ghost" aria-label={action}>
            <Link to={to}>
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </Button>
        </div>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1">
        <p className="text-3xl font-semibold tracking-tight tabular-nums">
          {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
        </p>
        <p className="text-sm text-muted-foreground">{hint}</p>
      </CardContent>
      <CardFooter>
        <Button asChild size="sm" variant="outline">
          <Link to={to}>{action}</Link>
        </Button>
      </CardFooter>
    </Card>
  );
}

interface QuickActionProps {
  icon: LucideIcon;
  title: string;
  description: string;
  to: string;
  delay?: number;
}

function QuickAction({
  icon: Icon,
  title,
  description,
  to,
  delay = 0,
}: QuickActionProps) {
  return (
    <Link
      to={to}
      style={{ animationDelay: `${delay}ms` }}
      className={cn(
        "docmind-rise group flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-sm",
        "transition-[transform,border-color,background-color,box-shadow] duration-200",
        "hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-md hover:shadow-brand/10",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
      )}
    >
      <span className="flex size-10 items-center justify-center rounded-lg bg-brand/10 text-brand ring-1 ring-brand-border/30 transition-colors group-hover:bg-brand/20 group-hover:ring-brand/30 group-hover:shadow-[0_0_8px_var(--color-brand)]">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <span className="space-y-1">
        <span className="block text-sm font-medium">{title}</span>
        <span className="block text-sm text-muted-foreground">
          {description}
        </span>
      </span>
    </Link>
  );
}

export function DashboardPage() {
  const { data: documents } = useDocuments();
  const documentCount = documents?.filter((document) => !document.deleted).length;

  return (
    <div className="docmind-page mx-auto w-full max-w-6xl space-y-8 p-6 lg:p-8">
      <div className="space-y-1">
        <p className="flex items-center gap-1.5 text-sm font-medium text-brand">
          <Sparkles className="size-4" aria-hidden="true" />
          Welcome back
        </p>
        <PageHeader
          title="Dashboard"
          description="Upload documents and ask questions about them with DocMind AI."
        />
      </div>

      <section className="grid gap-4 sm:grid-cols-2">
        <OverviewCard
          icon={FileText}
          title="Documents"
          description="Your indexed PDF library"
          value={documentCount ?? "—"}
          hint="Upload a PDF to build your knowledge base."
          to="/app/documents"
          action="Open documents"
        />
        <OverviewCard
          icon={MessagesSquare}
          title="Chat & RAG"
          description="Ask questions about your documents"
          value="—"
          hint="Start a conversation to get grounded answers."
          to="/app/chat"
          action="Open chat"
          delay={60}
        />
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          Quick actions
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <QuickAction
            icon={UploadCloud}
            title="Upload a document"
            description="Add a PDF and let DocMind index it for you."
            to="/app/documents"
          />
          <QuickAction
            icon={Sparkles}
            title="Ask a question"
            description="Get grounded answers from your documents."
            to="/app/chat"
            delay={60}
          />
          <QuickAction
            icon={FileText}
            title="Review documents"
            description="See what has been indexed so far."
            to="/app/documents"
            delay={120}
          />
        </div>
      </section>
    </div>
  );
}