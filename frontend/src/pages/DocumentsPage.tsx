import { AlertCircle, FileText } from "lucide-react";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/app/PageHeader";
import { DocumentCard } from "@/components/documents/DocumentCard";
import { UploadCard } from "@/components/documents/UploadCard";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useDocuments } from "@/hooks/use-documents";

function SkeletonCard() {
  return (
    <Card className="gap-3 py-4">
      <div className="flex items-center gap-3 px-4">
        <span className="size-10 shrink-0 animate-pulse rounded-lg bg-muted" />
        <div className="flex-1 space-y-2">
          <div className="h-3 w-3/4 animate-pulse rounded bg-muted" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
        </div>
      </div>
      <div className="h-3 w-1/3 animate-pulse rounded bg-muted px-4" />
    </Card>
  );
}

export function DocumentsPage() {
  const {
    data: documents,
    isLoading,
    isError,
    error,
    refetch,
  } = useDocuments();

  return (
    <div className="mx-auto w-full max-w-6xl space-y-8 p-6 lg:p-8">
      <PageHeader
        title="Documents"
        description="Upload PDFs and DocMind will index them for question answering."
      />

      <UploadCard />

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">
            Your documents
          </h2>
          <span className="text-xs text-muted-foreground">
            {documents?.length ?? 0}
          </span>
        </div>

        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <SkeletonCard key={index} />
            ))}
          </div>
        ) : isError ? (
          <Card className="flex flex-col items-center gap-3 py-10 text-center">
            <AlertCircle
              className="size-8 text-destructive"
              aria-hidden="true"
            />
            <p className="max-w-md text-sm text-muted-foreground">
              {error instanceof ApiError
                ? error.message
                : "Could not load documents."}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refetch()}
            >
              Try again
            </Button>
          </Card>
        ) : documents && documents.length === 0 ? (
          <Card className="flex flex-col items-center gap-3 py-10 text-center">
            <FileText className="size-8 text-muted-foreground" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">
              No documents yet. Upload your first PDF above.
            </p>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {documents?.map((document) => (
              <DocumentCard key={document.document_id} document={document} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}