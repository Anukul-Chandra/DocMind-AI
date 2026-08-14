import { FileText } from "lucide-react";

import type { Document } from "@/api/documents";
import { DeleteDocumentDialog } from "@/components/documents/DeleteDocumentDialog";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
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
    <Card className="gap-3 py-4">
      <CardHeader className="flex-row items-center gap-3 px-4">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted">
          <FileText
            className="size-5 text-muted-foreground"
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
          </span>
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 font-medium",
              document.deleted
                ? "bg-muted text-muted-foreground"
                : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
            )}
          >
            {document.deleted ? "Deleted" : "Indexed"}
          </span>
        </div>
      </CardContent>
      <CardFooter className="justify-end px-4">
        {!document.deleted && <DeleteDocumentDialog document={document} />}
      </CardFooter>
    </Card>
  );
}