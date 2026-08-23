import {
  ArrowRight,
  FileText,
  MessagesSquare,
  Sparkles,
  UploadCloud,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
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

interface StatCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  value: string | number;
  trend?: string;
  trendUp?: boolean;
  delay?: number;
}

function StatCard({
  icon: Icon,
  title,
  description,
  value,
  trend,
  trendUp = true,
  delay = 0,
}: StatCardProps) {
  return (
    <Card className={cn("docmind-rise relative overflow-hidden", "transition-all duration-300 hover:shadow-elevation-2", { "shadow-elevation-1": true })} style={{ animationDelay: `${delay}ms` }}>
      <div className="absolute inset-0 bg-gradient-to-br from-brand/5 via-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" aria-hidden="true" />
      <CardHeader className="relative z-10">
        <div className="flex items-start justify-between gap-3">
          <span className="flex size-11 items-center justify-center rounded-xl bg-brand/10 text-brand ring-1 ring-brand-border/30 shadow-[0_0_0_1px_var(--color-brand-border)] transition-all duration-300 group-hover:bg-brand/15 group-hover:ring-brand/40 group-hover:shadow-brand/20">
            <Icon className="size-5" aria-hidden="true" />
          </span>
          {trend && (
            <span className={cn(
              "flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full",
              trendUp ? "bg-green/10 text-green" : "bg-destructive/10 text-destructive"
            )}>
              <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
              {trend}
            </span>
          )}
        </div>
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <CardDescription className="text-xs">{description}</CardDescription>
      </CardHeader>
      <CardContent className="relative z-10 space-y-1">
        <p className="text-3xl font-semibold tracking-tight tabular-nums text-foreground">
          {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
        </p>
      </CardContent>
    </Card>
  );
}

interface QuickActionProps {
  icon: LucideIcon;
  title: string;
  description: string;
  to: string;
  variant?: "primary" | "secondary";
  delay?: number;
}

function QuickAction({
  icon: Icon,
  title,
  description,
  to,
  variant = "secondary",
  delay = 0,
}: QuickActionProps) {
  const isPrimary = variant === "primary";
  return (
    <Link
      to={to}
      style={{ animationDelay: `${delay}ms` }}
      className={cn(
        "docmind-rise group relative flex flex-col gap-4 rounded-2xl p-5 transition-all duration-300",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        isPrimary
          ? "bg-gradient-to-br from-brand/10 via-brand/5 to-transparent border border-brand-border/30 hover:border-brand/40 hover:shadow-brand/15 hover:shadow-elevation-2"
          : "bg-card border border-border hover:border-brand/30 hover:shadow-elevation-2 hover:bg-card/80"
      )}
    >
      <div className="relative z-10">
        <span className={cn(
          "flex size-11 items-center justify-center rounded-xl transition-all duration-300",
          isPrimary
            ? "bg-brand text-brand-foreground shadow-brand group-hover:shadow-brand/30 group-hover:scale-105"
            : "bg-brand/10 text-brand ring-1 ring-brand-border/30 group-hover:bg-brand/15 group-hover:ring-brand/40 group-hover:shadow-brand/20"
        )}>
          <Icon className="size-5" aria-hidden="true" />
        </span>
        <div className="absolute inset-0 bg-gradient-to-br from-brand/5 via-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100 rounded-2xl" aria-hidden="true" />
      </div>
      <div className="relative z-10 space-y-1">
        <span className="block text-base font-medium text-foreground">{title}</span>
        <span className="block text-sm text-muted-foreground">{description}</span>
      </div>
      <div className={cn(
        "relative z-10 flex items-center gap-1.5 text-sm font-medium transition-transform duration-300 group-hover:translate-x-1",
        isPrimary ? "text-brand-foreground/80" : "text-brand"
      )}>
        <ArrowRight className="size-4" aria-hidden="true" />
      </div>
    </Link>
  );
}

export function DashboardPage() {
  const { data: documents } = useDocuments();
  const documentCount = documents?.filter((document) => !document.deleted).length ?? 0;
  const chunkCount = documents?.reduce((sum, d) => sum + (d.chunk_count ?? 0), 0) ?? 0;

  return (
    <div className="docmind-page mx-auto w-full max-w-7xl space-y-8 p-6 lg:p-8 docmind-ambient">
      {/* Hero Section */}
      <section className="relative rounded-3xl bg-gradient-to-br from-card via-card/80 to-card/60 border border-border/50 p-6 lg:p-10 overflow-hidden docmind-ambient">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,var(--brand)_/15,transparent_60%)] pointer-events-none" aria-hidden="true" />
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="flex size-8 items-center justify-center rounded-lg bg-brand/10 text-brand ring-1 ring-brand-border/30">
                <Sparkles className="size-4" aria-hidden="true" />
              </span>
              <span className="text-sm font-medium text-brand">DocMind AI</span>
              <span className="text-xs text-muted-foreground">Workspace</span>
            </div>
            <h1 className="text-3xl lg:text-4xl font-semibold tracking-tight text-foreground">
              Welcome back
            </h1>
            <p className="text-base text-muted-foreground max-w-xl">
              Your intelligent document workspace is ready. Upload PDFs, ask questions, and let AI do the heavy lifting.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 mt-4 sm:mt-0">
            <Button asChild size="lg" className="gap-2 shadow-brand hover:shadow-brand/30">
              <Link to="/app/documents">Upload Document</Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="gap-2 border-border hover:border-brand/40 hover:bg-brand/5">
              <Link to="/app/chat">Start Chat</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Stats Grid */}
      <section aria-label="Workspace statistics">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            icon={FileText}
            title="Documents"
            description="Indexed PDFs in your library"
            value={documentCount}
            trend="+12%"
            delay={0}
          />
          <StatCard
            icon={MessagesSquare}
            title="Conversations"
            description="Chat sessions this month"
            value="—"
            delay={60}
          />
          <StatCard
            icon={Sparkles}
            title="Chunks Indexed"
            description="Searchable content segments"
            value={chunkCount}
            trend="+8%"
            delay={120}
          />
          <StatCard
            icon={UploadCloud}
            title="Storage Used"
            description="Of your 5GB allowance"
            value="2.1 GB"
            delay={180}
          />
        </div>
      </section>

      {/* Quick Actions */}
      <section className="space-y-4" aria-label="Quick actions">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Quick actions</h2>
          <Button asChild variant="ghost" size="sm" className="text-muted-foreground hover:text-brand">
            <Link to="/app/documents">View all</Link>
          </Button>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <QuickAction
            icon={UploadCloud}
            title="Upload a document"
            description="Add a PDF and let DocMind index it for you."
            to="/app/documents"
            variant="primary"
            delay={0}
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

      {/* Recent Activity / AI Insights */}
      <section className="space-y-4" aria-label="AI insights">
        <h2 className="text-lg font-semibold text-foreground">AI insights</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card className="bg-brand-surface/50 border-brand-border/30 hover:border-brand/30 transition-all duration-300">
            <CardHeader className="pb-2">
              <div className="flex items-center gap-2 text-sm font-medium text-brand">
                <Sparkles className="size-4" aria-hidden="true" />
                <span>Smart suggestions</span>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button asChild variant="ghost" className="w-full justify-start gap-3 p-3 rounded-xl hover:bg-brand/10 hover:text-foreground transition-all">
                <Link to="/app/chat">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-brand/10 text-brand">
                    <MessagesSquare className="size-4" aria-hidden="true" />
                  </span>
                  <span className="text-sm font-medium">"Summarize my latest uploads"</span>
                </Link>
              </Button>
              <Button asChild variant="ghost" className="w-full justify-start gap-3 p-3 rounded-xl hover:bg-brand/10 hover:text-foreground transition-all">
                <Link to="/app/chat">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-brand/10 text-brand">
                    <FileText className="size-4" aria-hidden="true" />
                  </span>
                  <span className="text-sm font-medium">"Extract key findings from all docs"</span>
                </Link>
              </Button>
            </CardContent>
          </Card>
          <Card className="hover:border-brand/30 transition-all duration-300">
            <CardHeader className="pb-2">
              <h3 className="text-sm font-medium text-foreground">Getting started</h3>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p className="flex items-center gap-2">
                <span className="flex size-5 items-center justify-center rounded bg-brand/10 text-brand">
                  <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                </span>
                Drag & drop a PDF to get started
              </p>
              <p className="flex items-center gap-2 ml-7">
                <span className="flex size-5 items-center justify-center rounded bg-brand/10 text-brand">
                  <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                </span>
                Ask questions in natural language
              </p>
              <p className="flex items-center gap-2 ml-7">
                <span className="flex size-5 items-center justify-center rounded bg-brand/10 text-brand">
                  <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
                </span>
                Get cited, grounded answers
              </p>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}