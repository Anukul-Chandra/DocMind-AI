import { FileText } from "lucide-react";

import type { Document } from "@/api/documents";
import { DeleteDocumentDialog } from "@/components/documents/DeleteDocumentDialog";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import { documentTypeLabel } from "@/lib/document-types";
import { cn } from "@/lib/utils";

export function formatUploadDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function DocumentCard({ document }: { document: Document }) {
  return (
    <Card className="group relative gap-3 overflow-hidden py-4 transition-[transform,border-color,box-shadow] duration-200 hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-elevation-2">
      {/* Emerald accent hairline on hover */}
      <span
        className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/60 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        aria-hidden="true"
      />
      <CardHeader className="flex-row items-center gap-3 px-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand ring-1 ring-inset ring-brand-border/30 transition-all duration-300 group-hover:bg-brand/15 group-hover:shadow-[0_0_12px_-4px_var(--brand)]">
          <FileText className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium" title={document.filename}>
            {document.filename}
          </p>
          <p className="text-xs text-muted-foreground">
            Indexed {formatUploadDate(document.uploaded_at)}
          </p>
        </div>
        <span
          className={cn(
            "ml-auto size-1.5 shrink-0 rounded-full",
            document.deleted ? "bg-muted-foreground/40" : "docmind-scan-pulse bg-brand shadow-[0_0_5px_var(--brand)]",
          )}
          aria-label={document.deleted ? "Deleted" : "Indexed"}
          role="img"
        />
      </CardHeader>
      <CardContent className="px-4">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="docmind-label tabular-nums text-muted-foreground/70">
            {document.chunk_count} chunks
          </span>
          <span
            className={cn(
              "inline-flex items-center rounded-md px-2 py-0.5 font-medium ring-1 ring-inset",
              document.deleted
                ? "bg-muted text-muted-foreground ring-transparent"
                : "bg-brand/10 text-brand ring-brand-border/30",
            )}
          >
            {documentTypeLabel(document.classification)}
          </span>
        </div>
        {document.deleted && (
          <p className="mt-1.5 text-xs text-destructive">Removed from index</p>
        )}
      </CardContent>
      <CardFooter className="justify-end px-4">
        {!document.deleted && <DeleteDocumentDialog document={document} />}
      </CardFooter>
    </Card>
  );
}
