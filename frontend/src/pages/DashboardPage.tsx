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
import { cn } from "@/lib/utils";

interface OverviewCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  value: string;
  hint: string;
  to: string;
  action: string;
}

function OverviewCard({
  icon: Icon,
  title,
  description,
  value,
  hint,
  to,
  action,
}: OverviewCardProps) {
  return (
    <Card className="gap-5">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
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
        <p className="text-3xl font-semibold tracking-tight">{value}</p>
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
}

function QuickAction({ icon: Icon, title, description, to }: QuickActionProps) {
  return (
    <Link
      to={to}
      className={cn(
        "group flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-sm transition-colors",
        "hover:border-primary/30 hover:bg-accent/40",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      )}
    >
      <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary/15">
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
  return (
    <div className="mx-auto w-full max-w-6xl space-y-8 p-6 lg:p-8">
      <div className="space-y-1">
        <p className="text-sm font-medium text-primary">Welcome back</p>
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
          value="—"
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
          />
          <QuickAction
            icon={FileText}
            title="Review documents"
            description="See what has been indexed so far."
            to="/app/documents"
          />
        </div>
      </section>
    </div>
  );
}
