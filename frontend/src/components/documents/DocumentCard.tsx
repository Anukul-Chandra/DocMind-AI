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
    <Card className="group gap-3 py-4 transition-[transform,border-color,box-shadow] duration-200 hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-md hover:shadow-brand/10">
      <CardHeader className="flex-row items-center gap-3 px-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand ring-1 ring-brand-border/30 transition-colors group-hover:bg-brand/20 group-hover:ring-brand/30 group-hover:shadow-[0_0_8px_var(--color-brand)]">
          <FileText
            className="size-5"
            aria-hidden="true"
          />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium" title={document.filename}>
            {document.filename}
          </p>
          <p className="text-xs text-muted-foreground">
            Uploaded {formatUploadDate(document.uploaded_at)}
          </p>
        </div>
      </CardHeader>
      <CardContent className="px-4">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">
            {document.chunk_count} chunks
            {document.deleted && (
              <span className="ml-2 text-destructive">· Deleted</span>
            )}
          </span>
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 font-medium",
              document.deleted
                ? "bg-muted text-muted-foreground"
                : document.classification === "unknown"
                ? "bg-brand/10 text-brand"
                : "bg-brand/10 text-brand ring-1 ring-brand-border/30",
            )}
          >
            {documentTypeLabel(document.classification)}
          </span>
        </div>
      </CardContent>
      <CardFooter className="justify-end px-4">
        {!document.deleted && <DeleteDocumentDialog document={document} />}
      </CardFooter>
    </Card>
  );
}