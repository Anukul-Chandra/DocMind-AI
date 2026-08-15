import { useState } from "react";
import { FileText, Search, SearchX } from "lucide-react";

import { ApiError } from "@/api/client";
import { PageHeader } from "@/components/app/PageHeader";
import { DocumentCard } from "@/components/documents/DocumentCard";
import { UploadCard } from "@/components/documents/UploadCard";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Input } from "@/components/ui/input";
import { useDocuments } from "@/hooks/use-documents";
import {
  filterDocuments,
  hasActiveFilters,
  NO_TYPE_FILTER,
  type DocumentTypeFilter,
} from "@/lib/document-filter";
import { DOCUMENT_TYPES, documentTypeLabel } from "@/lib/document-types";
import { cn } from "@/lib/utils";

function DocumentSkeleton() {
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
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] =
    useState<DocumentTypeFilter>(NO_TYPE_FILTER);

  const filters = { query, type: typeFilter };
  const filtered = filterDocuments(documents ?? [], filters);
  const hasFiltering = hasActiveFilters(filters);
  const hasDocuments = (documents?.length ?? 0) > 0;

  return (
    <div className="mx-auto w-full max-w-6xl space-y-8 p-6 lg:p-8">
      <PageHeader
        title="Documents"
        description="Upload PDFs and DocMind will index them for question answering."
      />

      <UploadCard />

      <section className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-medium text-muted-foreground">
              Your documents
            </h2>
            <span className="text-xs text-muted-foreground">
              {hasFiltering && hasDocuments
                ? `${filtered.length} of ${documents?.length ?? 0}`
                : documents?.length ?? 0}
            </span>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by filename…"
                aria-label="Search documents by filename"
                className="h-9 w-full pl-9 sm:w-64"
              />
            </div>
            <select
              value={typeFilter}
              onChange={(event) =>
                setTypeFilter(event.target.value as DocumentTypeFilter)
              }
              aria-label="Filter documents by type"
              className={cn(
                "border-input flex h-9 w-full min-w-0 rounded-md border bg-transparent px-3 py-1 text-base shadow-xs outline-none transition-[color,box-shadow] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
                "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                "sm:w-44",
              )}
            >
              <option value={NO_TYPE_FILTER}>All types</option>
              {DOCUMENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {documentTypeLabel(type)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((index) => (
              <DocumentSkeleton key={index} />
            ))}
          </div>
        ) : isError ? (
          <ErrorState
            message={
              error instanceof ApiError
                ? error.message
                : "Could not load documents."
            }
            action={
              <Button variant="outline" size="sm" onClick={() => void refetch()}>
                Try again
              </Button>
            }
          />
        ) : !hasDocuments ? (
          <EmptyState
            icon={FileText}
            title="No documents yet"
            description="Upload your first PDF above and DocMind will index it for question answering."
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={SearchX}
            title="No matching documents"
            description="No documents match your search or filter. Try a different filename or type."
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setQuery("");
                  setTypeFilter(NO_TYPE_FILTER);
                }}
              >
                Clear filters
              </Button>
            }
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((document) => (
              <DocumentCard key={document.document_id} document={document} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}