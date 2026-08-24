import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Database,
  FileText,
  MessagesSquare,
  Sparkles,
  TrendingUp,
  UploadCloud,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Document } from "@/api/documents";
import { formatUploadDate } from "@/components/documents/DocumentCard";
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
import { documentTypeLabel } from "@/lib/document-types";
import { cn } from "@/lib/utils";

function AnimatedNumber({ value }: { value: number }) {
  const count = useCountUp(value);
  return <>{count}</>;
}

function SectionHeader({
  title,
  kicker,
  action,
}: {
  title: string;
  kicker: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-4">
      <div className="flex min-w-0 items-center gap-3">
        <span
          className="size-1.5 shrink-0 rounded-full bg-brand shadow-[0_0_6px_var(--brand)]"
          aria-hidden="true"
        />
        <h2 className="truncate text-base font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        <span className="docmind-label hidden shrink-0 text-muted-foreground/50 sm:inline" aria-hidden="true">
          {kicker}
        </span>
      </div>
      <span
        className="hidden h-px flex-1 bg-gradient-to-r from-border/60 to-transparent md:block"
        aria-hidden="true"
      />
      {action}
    </div>
  );
}

interface StatMonitorProps {
  icon: LucideIcon;
  title: string;
  description: string;
  value: string | number;
  trend?: string;
  status?: "live" | "idle";
  meterPercent?: number;
  delay?: number;
}

function StatMonitor({
  icon: Icon,
  title,
  description,
  value,
  trend,
  status = "idle",
  meterPercent,
  delay = 0,
}: StatMonitorProps) {
  return (
    <div
      className="docmind-rise docmind-panel group relative overflow-hidden rounded-2xl p-4 transition-shadow duration-300 hover:shadow-elevation-2"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div
        className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/30 to-transparent opacity-60 transition-opacity duration-300 group-hover:opacity-100"
        aria-hidden="true"
      />
      <div className="relative flex items-center justify-between gap-2">
        <span className="docmind-label flex min-w-0 items-center gap-2 text-muted-foreground">
          <Icon className="size-3.5 shrink-0 text-brand" aria-hidden="true" />
          <span className="truncate">{title}</span>
        </span>
        <span
          className={cn(
            "size-1.5 shrink-0 rounded-full",
            status === "live"
              ? "docmind-scan-pulse bg-brand shadow-[0_0_6px_var(--brand)]"
              : "bg-muted-foreground/40",
          )}
          aria-label={status === "live" ? "Live metric" : "No data"}
          role="img"
        />
      </div>
      <p className="mt-3 text-3xl font-semibold tabular-nums tracking-tight text-foreground">
        {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
      </p>
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <span className="truncate text-xs text-muted-foreground">{description}</span>
        {trend && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-brand/10 px-1.5 py-0.5 text-xs font-medium text-brand ring-1 ring-inset ring-brand-border/30">
            <TrendingUp className="size-3" aria-hidden="true" />
            {trend}
          </span>
        )}
      </div>
      {typeof meterPercent === "number" && (
        <div
          className="mt-2.5 h-1 overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={meterPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Storage capacity"
        >
          <div
            className="h-full rounded-full bg-brand/80 shadow-[0_0_6px_var(--brand)] transition-[width] duration-700 ease-out"
            style={{ width: `${meterPercent}%` }}
          />
        </div>
      )}
    </div>
  );
}

interface ModuleActionProps {
  icon: LucideIcon;
  code: string;
  title: string;
  description: string;
  to: string;
  variant?: "primary" | "secondary";
  delay?: number;
}

function ModuleAction({
  icon: Icon,
  code,
  title,
  description,
  to,
  variant = "secondary",
  delay = 0,
}: ModuleActionProps) {
  const isPrimary = variant === "primary";
  return (
    <Link
      to={to}
      style={{ animationDelay: `${delay}ms` }}
      className={cn(
        "docmind-rise docmind-nav-item group relative flex flex-col gap-4 rounded-2xl p-5 outline-none transition-all duration-300 hover:-translate-y-0.5",
        "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        isPrimary
          ? "border border-brand-border/40 bg-gradient-to-br from-brand-surface/80 via-card to-card shadow-[0_0_28px_-10px_var(--brand)] hover:border-brand/50 hover:shadow-elevation-2"
          : "docmind-panel hover:border-brand/35 hover:shadow-elevation-2",
      )}
    >
      <div className="relative z-10 flex items-start justify-between">
        <span
          className={cn(
            "flex size-12 items-center justify-center rounded-xl transition-all duration-300",
            isPrimary
              ? "bg-brand text-brand-foreground shadow-brand group-hover:shadow-brand/45"
              : "bg-brand/10 text-brand ring-1 ring-inset ring-brand-border/30 group-hover:bg-brand/15 group-hover:shadow-[0_0_14px_-4px_var(--brand)]",
          )}
        >
          <Icon className="size-5" aria-hidden="true" />
        </span>
        <span
          className="docmind-label pt-1 text-muted-foreground/40 transition-colors duration-300 group-hover:text-muted-foreground"
          aria-hidden="true"
        >
          {code}
        </span>
      </div>
      <div className="relative z-10 space-y-1">
        <span className="block font-medium text-foreground">{title}</span>
        <span className="block text-sm leading-relaxed text-muted-foreground">{description}</span>
      </div>
      <ArrowRight
        className="relative z-10 size-4 self-start text-muted-foreground/50 transition-all duration-300 group-hover:translate-x-1 group-hover:text-brand"
        aria-hidden="true"
      />
    </Link>
  );
}

function RecentIndexPanel({ documents }: { documents: Document[] }) {
  const recent = [...documents]
    .filter((document) => !document.deleted)
    .sort((a, b) => new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime())
    .slice(0, 4);

  return (
    <Card className="gap-0 py-0 lg:col-span-3">
      <CardHeader className="flex-row items-center justify-between gap-3 border-b border-border/40 px-5 py-4">
        <div className="flex items-center gap-2.5">
          <Database className="size-4 text-brand" aria-hidden="true" />
          <CardTitle className="text-sm font-semibold">Knowledge Index</CardTitle>
          <span className="docmind-label hidden text-muted-foreground/50 sm:inline" aria-hidden="true">
            Live
          </span>
        </div>
        <span
          className="docmind-scan-pulse size-1.5 rounded-full bg-brand shadow-[0_0_6px_var(--brand)]"
          aria-hidden="true"
        />
      </CardHeader>
      <CardContent className="px-2.5 py-3">
        {recent.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
            <span className="flex size-11 items-center justify-center rounded-xl bg-brand/10 text-brand ring-1 ring-inset ring-brand-border/30">
              <FileText className="size-5" aria-hidden="true" />
            </span>
            <p className="text-sm text-muted-foreground">No documents indexed yet.</p>
            <Button asChild size="sm" variant="outline" className="hover:border-brand/40 hover:text-brand">
              <Link to="/app/documents">Upload your first document</Link>
            </Button>
          </div>
        ) : (
          <ul className="space-y-0.5">
            {recent.map((document) => (
              <li key={document.document_id}>
                <Link
                  to="/app/documents"
                  className="docmind-nav-item group/row flex items-center gap-3 rounded-xl px-2.5 py-2.5 transition-colors duration-200 hover:bg-accent/60"
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand ring-1 ring-inset ring-brand-border/25 transition-shadow duration-200 group-hover/row:shadow-[0_0_10px_-2px_var(--brand)]">
                    <FileText className="size-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-foreground" title={document.filename}>
                      {document.filename}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      Indexed {formatUploadDate(document.uploaded_at)} ·{" "}
                      <span className="tabular-nums">{document.chunk_count}</span> chunks
                    </span>
                  </span>
                  <span className="hidden shrink-0 items-center rounded-md bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand ring-1 ring-inset ring-brand-border/25 sm:inline-flex">
                    {documentTypeLabel(document.classification)}
                  </span>
                  <ArrowUpRight
                    className="size-4 shrink-0 text-muted-foreground/40 transition-all duration-200 group-hover/row:translate-x-0.5 group-hover/row:-translate-y-0.5 group-hover/row:text-brand"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const { data: documents } = useDocuments();
  const activeDocuments = documents?.filter((document) => !document.deleted) ?? [];
  const documentCount = activeDocuments.length;
  const chunkCount =
    documents?.reduce((sum, d) => sum + (d.chunk_count ?? 0), 0) ?? 0;

  return (
    <div className="docmind-page mx-auto w-full max-w-7xl space-y-8 p-6 lg:p-8">
      {/* Hero — system introduction */}
      <section
        className="docmind-corners relative overflow-hidden rounded-3xl border border-border/50 p-6 lg:p-10"
        aria-label="DocMind AI system overview"
      >
        {/* Atmosphere layers */}
        <div className="absolute inset-0 bg-gradient-to-br from-card via-card/85 to-card/55" aria-hidden="true" />
        <div className="docmind-grid-fade absolute inset-0" aria-hidden="true" />
        <div
          className="absolute inset-0 bg-[radial-gradient(ellipse_60%_70%_at_88%_-10%,color-mix(in_oklab,var(--brand)_9%,transparent),transparent_65%)]"
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/45 to-transparent"
          aria-hidden="true"
        />

        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-4">
            <span className="docmind-label inline-flex items-center gap-2 rounded-full border border-brand-border/35 bg-brand/8 px-3 py-1 text-brand">
              <span className="docmind-scan-pulse size-1.5 rounded-full bg-brand shadow-[0_0_6px_var(--brand)]" aria-hidden="true" />
              System Online
            </span>
            <div className="space-y-2.5">
              <h1 className="text-4xl font-semibold tracking-tight text-foreground lg:text-5xl">
                DocMind <span className="text-brand-gradient">AI</span>
              </h1>
              <p className="docmind-label text-muted-foreground/70" aria-hidden="true">
                Document Intelligence · Command Center
              </p>
              <p className="max-w-xl text-base leading-relaxed text-muted-foreground">
                Your document intelligence workspace is online. Index PDFs into searchable knowledge, query it in
                natural language, and get grounded answers with citations.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild size="lg" className="gap-2 shadow-brand hover:shadow-brand/45">
              <Link to="/app/documents">
                <UploadCloud className="size-4.5" aria-hidden="true" />
                Upload Document
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="gap-2 hover:border-brand/40 hover:bg-brand/5 hover:text-brand">
              <Link to="/app/chat">
                <MessagesSquare className="size-4.5" aria-hidden="true" />
                Start Chat
              </Link>
            </Button>
          </div>
        </div>

        {/* Telemetry ticker */}
        <div className="relative mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-border/40 pt-4">
          <span className="docmind-label flex items-center gap-2 text-muted-foreground/60">
            <Activity className="size-3.5 text-brand/70" aria-hidden="true" />
            Index Telemetry
          </span>
          <span className="docmind-label text-muted-foreground/60">
            DOCS <span className="ml-1.5 text-brand">{documentCount}</span>
          </span>
          <span className="docmind-label text-muted-foreground/60">
            CHUNKS <span className="ml-1.5 text-brand">{chunkCount}</span>
          </span>
          <span className="docmind-label text-muted-foreground/60">
            RAG CORE <span className="ml-1.5 text-brand">ONLINE</span>
          </span>
        </div>
      </section>

      {/* Statistics — system telemetry */}
      <section className="space-y-4" aria-label="System telemetry">
        <SectionHeader title="System telemetry" kicker="Monitoring" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatMonitor
            icon={FileText}
            title="Documents"
            description="Indexed PDFs in library"
            value={documentCount}
            trend="+12%"
            status="live"
            delay={0}
          />
          <StatMonitor
            icon={MessagesSquare}
            title="Conversations"
            description="Chat sessions this month"
            value="—"
            status="idle"
            delay={60}
          />
          <StatMonitor
            icon={Sparkles}
            title="Chunks Indexed"
            description="Searchable segments"
            value={chunkCount}
            trend="+8%"
            status="live"
            delay={120}
          />
          <StatMonitor
            icon={UploadCloud}
            title="Storage Used"
            description="Of 5 GB allowance"
            value="2.1 GB"
            status="live"
            meterPercent={42}
            delay={180}
          />
        </div>
      </section>

      {/* Quick actions — AI modules */}
      <section className="space-y-4" aria-label="Operations modules">
        <SectionHeader
          title="Operations"
          kicker="Modules"
          action={
            <Button asChild variant="ghost" size="sm" className="text-muted-foreground hover:text-brand">
              <Link to="/app/documents">View all</Link>
            </Button>
          }
        />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <ModuleAction
            icon={UploadCloud}
            code="M·01"
            title="Ingest Document"
            description="Add a PDF and let DocMind index it for you."
            to="/app/documents"
            variant="primary"
            delay={0}
          />
          <ModuleAction
            icon={Sparkles}
            code="M·02"
            title="Query Intelligence"
            description="Get grounded answers from your documents."
            to="/app/chat"
            delay={60}
          />
          <ModuleAction
            icon={FileText}
            code="M·03"
            title="Browse Library"
            description="See what has been indexed so far."
            to="/app/documents"
            delay={120}
          />
        </div>
      </section>

      {/* Knowledge index + insights */}
      <section className="space-y-4" aria-label="Knowledge index and AI insights">
        <SectionHeader title="Knowledge system" kicker="Live Feed" />
        <div className="grid gap-4 lg:grid-cols-5">
          <RecentIndexPanel documents={documents ?? []} />

          <div className="space-y-4 lg:col-span-2">
            <Card className="gap-4 border-brand-border/30 bg-brand-surface/40 transition-colors duration-300 hover:border-brand/35">
              <CardHeader className="pb-0">
                <div className="flex items-center gap-2 text-sm font-medium text-brand">
                  <Sparkles className="size-4" aria-hidden="true" />
                  <CardTitle className="text-sm">Smart suggestions</CardTitle>
                </div>
                <CardDescription className="sr-only">Suggested prompts for the assistant</CardDescription>
              </CardHeader>
              <CardContent className="space-y-1.5 px-4 pb-4">
                <Button asChild variant="ghost" className="w-full justify-start gap-3 rounded-xl p-2.5 hover:bg-brand/10 hover:text-foreground">
                  <Link to="/app/chat">
                    <span className="flex size-8 items-center justify-center rounded-lg bg-brand/10 text-brand">
                      <MessagesSquare className="size-4" aria-hidden="true" />
                    </span>
                    <span className="truncate text-sm font-medium">Summarize my latest uploads</span>
                  </Link>
                </Button>
                <Button asChild variant="ghost" className="w-full justify-start gap-3 rounded-xl p-2.5 hover:bg-brand/10 hover:text-foreground">
                  <Link to="/app/chat">
                    <span className="flex size-8 items-center justify-center rounded-lg bg-brand/10 text-brand">
                      <FileText className="size-4" aria-hidden="true" />
                    </span>
                    <span className="truncate text-sm font-medium">Extract key findings from all docs</span>
                  </Link>
                </Button>
              </CardContent>
            </Card>

            <Card className="gap-4">
              <CardHeader className="pb-0 px-5 pt-5">
                <CardTitle className="text-sm">Getting started</CardTitle>
                <CardDescription>Three steps to your first grounded answer</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2.5 px-5 pb-5 text-sm text-muted-foreground">
                {[
                  "Drag & drop a PDF to index it",
                  "Ask questions in natural language",
                  "Get cited, grounded answers",
                ].map((step, index) => (
                  <p key={step} className="flex items-center gap-3">
                    <span className="docmind-label flex size-6 shrink-0 items-center justify-center rounded-md bg-brand/10 text-brand ring-1 ring-inset ring-brand-border/25">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    {step}
                  </p>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    </div>
  );
}
