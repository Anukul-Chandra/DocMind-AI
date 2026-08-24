import { Fragment, useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useDropzone, type FileRejection } from "react-dropzone";
import { Check, CloudUpload, FileWarning } from "lucide-react";

import { ApiError } from "@/api/client";
import type { Document, UploadResult } from "@/api/documents";
import {
  ScanCard,
  type PipelineStage,
} from "@/components/documents/ScanCard";
import { documentsKey, useUploadDocument } from "@/hooks/use-documents";
import { documentTypeLabel } from "@/lib/document-types";
import { cn } from "@/lib/utils";

export const MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024;
export const MAX_UPLOAD_SIZE_LABEL = "50 MiB";

const PIPELINE_STAGES: readonly PipelineStage[] = [
  { key: "upload", label: "Upload" },
  { key: "scan", label: "Scanning" },
  { key: "parse", label: "Parsing" },
  { key: "chunk", label: "Chunking" },
  { key: "embed", label: "Embedding" },
  { key: "index", label: "Indexing" },
];

type UploadStatus = "idle" | "processing" | "ready" | "error";

export function UploadCard() {
  const upload = useUploadDocument();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [fileName, setFileName] = useState("");
  const [classification, setClassification] = useState<string | null>(null);
  const [uploadPercent, setUploadPercent] = useState(0);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setResult(null);
      setClassification(null);
      setFileName(file.name);
      setUploadPercent(0);
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        setError("Only PDF files are supported.");
        setStatus("error");
        return;
      }
      if (file.size > MAX_UPLOAD_SIZE_BYTES) {
        setError(`File exceeds the ${MAX_UPLOAD_SIZE_LABEL} upload limit.`);
        setStatus("error");
        return;
      }
      setStatus("processing");
      try {
        const uploaded = await upload.mutateAsync({
          file,
          onUploadProgress: setUploadPercent,
        });
        setResult(uploaded);
        await queryClient.invalidateQueries({ queryKey: documentsKey });
        const docs = queryClient.getQueryData<Document[]>(documentsKey);
        const doc = docs?.find(
          (candidate) => candidate.document_id === uploaded.document_id,
        );
        setClassification(doc?.classification ?? null);
        setStatus("ready");
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "Upload failed. Please try again.",
        );
        setStatus("error");
      }
    },
    [upload, queryClient],
  );

  const onDrop = useCallback(
    (accepted: File[], rejected: FileRejection[]) => {
      setError(null);
      setResult(null);
      if (rejected.length > 0) {
        const codes = rejected[0].errors.map((reason) => reason.code);
        if (codes.includes("file-too-large")) {
          setError(`File exceeds the ${MAX_UPLOAD_SIZE_LABEL} upload limit.`);
        } else if (codes.includes("file-invalid-type")) {
          setError("Only PDF files are supported.");
        } else {
          setError("This file cannot be uploaded.");
        }
        setStatus("error");
        return;
      }
      const file = accepted[0];
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  const { getRootProps, getInputProps, isDragActive, isDragReject } =
    useDropzone({
      onDrop,
      accept: { "application/pdf": [".pdf"] },
      maxSize: MAX_UPLOAD_SIZE_BYTES,
      multiple: false,
    });

  if (status === "processing") {
    return (
      <ScanCard
        fileName={fileName}
        stages={PIPELINE_STAGES}
        phase={uploadPercent >= 100 ? "processing" : "transmitting"}
        uploadPercent={uploadPercent}
      />
    );
  }

  return (
    <div className="space-y-3">
      {result && (
        <div
          className="docmind-rise relative overflow-hidden rounded-2xl border border-brand-border/40 bg-card/60 p-5 shadow-[0_0_36px_-14px_var(--brand)] backdrop-blur-md"
          role="status"
        >
          <div
            className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/70 to-transparent"
            aria-hidden="true"
          />
          <div className="flex items-start gap-4">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand text-brand-foreground shadow-brand">
              <Check className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-foreground">
                  Indexing complete
                </p>
                <span className="docmind-label rounded-md bg-brand/10 px-1.5 py-0.5 text-brand ring-1 ring-inset ring-brand-border/30">
                  Indexed
                </span>
              </div>
              <p className="mt-0.5 truncate text-xs text-muted-foreground">
                {result.filename}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="docmind-label inline-flex items-center rounded-md border border-border/50 bg-card/60 px-2 py-1 tabular-nums text-muted-foreground">
                  {result.chunks} {result.chunks === 1 ? "chunk" : "chunks"}
                </span>
                <span className="docmind-label inline-flex items-center rounded-md border border-border/50 bg-card/60 px-2 py-1 tabular-nums text-muted-foreground">
                  {result.embeddings} embeddings
                </span>
                {classification && classification !== "unknown" && (
                  <span className="inline-flex items-center gap-1.5 rounded-md bg-brand/10 px-2 py-1 text-xs font-medium text-brand ring-1 ring-inset ring-brand-border/30">
                    <Check className="size-3" aria-hidden="true" />
                    {documentTypeLabel(classification)}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Full-pipeline recap — every stage genuinely executed by now */}
          <div
            className="mt-4 flex items-center gap-1.5 border-t border-border/40 pt-3"
            aria-hidden="true"
          >
            {PIPELINE_STAGES.map((stage, index) => (
              <Fragment key={stage.key}>
                {index > 0 && <span className="h-px flex-1 bg-brand-border/40" />}
                <span
                  className="size-1.5 shrink-0 rounded-full bg-brand shadow-[0_0_5px_var(--brand)]"
                  title={stage.label}
                />
              </Fragment>
            ))}
            <span className="docmind-label ml-3 hidden text-muted-foreground/50 sm:inline">
              Full pipeline executed
            </span>
          </div>
        </div>
      )}

      {error && (
        <div
          className="flex items-center gap-2.5 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive backdrop-blur-sm"
          role="alert"
        >
          <FileWarning className="size-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0">{error}</span>
        </div>
      )}

      {/* Ingest module */}
      <div
        {...getRootProps()}
        className={cn(
          "group relative flex cursor-pointer flex-col items-center justify-center gap-2 overflow-hidden rounded-2xl border border-dashed border-border/80 bg-card/30 px-6 py-12 text-center transition-all duration-300",
          "hover:border-brand/50 hover:bg-brand/[0.03] hover:shadow-[0_0_44px_-18px_var(--brand)]",
          "focus-visible:outline-none focus-visible:border-brand focus-visible:ring-brand/50 focus-visible:ring-[3px]",
          isDragActive &&
            "scale-[1.005] border-brand bg-brand/8 shadow-[0_0_56px_-20px_var(--brand)]",
          isDragReject && "border-destructive bg-destructive/5",
        )}
      >
        <input {...getInputProps()} />

        {/* Technical grid + corner brackets */}
        <div className="docmind-grid-fade absolute inset-0 opacity-70" aria-hidden="true" />
        <span
          className={cn(
            "absolute top-3 left-3 size-3.5 rounded-tl-md border-t border-l transition-colors duration-300",
            isDragActive ? "border-brand/70" : "border-brand/25",
          )}
          aria-hidden="true"
        />
        <span
          className={cn(
            "absolute top-3 right-3 size-3.5 rounded-tr-md border-t border-r transition-colors duration-300",
            isDragActive ? "border-brand/70" : "border-brand/25",
          )}
          aria-hidden="true"
        />
        <span
          className={cn(
            "absolute bottom-3 left-3 size-3.5 rounded-bl-md border-b border-l transition-colors duration-300",
            isDragActive ? "border-brand/70" : "border-brand/25",
          )}
          aria-hidden="true"
        />
        <span
          className={cn(
            "absolute right-3 bottom-3 size-3.5 rounded-br-md border-r border-b transition-colors duration-300",
            isDragActive ? "border-brand/70" : "border-brand/25",
          )}
          aria-hidden="true"
        />

        <span
          className={cn(
            "relative flex size-14 items-center justify-center rounded-2xl bg-brand/8 ring-1 ring-inset ring-brand-border/25 transition-all duration-300",
            isDragActive &&
              "scale-105 bg-brand/15 shadow-[0_0_24px_-6px_var(--brand)] ring-brand/40",
          )}
        >
          <CloudUpload
            className={cn(
              "size-7 text-brand/60 transition-all duration-300",
              isDragActive && "scale-110 text-brand",
            )}
            aria-hidden="true"
          />
        </span>

        <p className="relative mt-1 text-base font-medium text-foreground">
          {isDragReject
            ? "Unsupported file"
            : isDragActive
              ? "Release to ingest"
              : "Drop PDF to ingest"}
        </p>
        <p className="relative text-sm text-muted-foreground">
          or click to browse · parsed, chunked & embedded automatically
        </p>

        <div
          className="docmind-label relative mt-2 flex items-center gap-2.5 text-muted-foreground/50"
          aria-hidden="true"
        >
          <span>PDF</span>
          <span className="h-3 w-px bg-border/60" />
          <span>Max {MAX_UPLOAD_SIZE_LABEL}</span>
          <span className="h-3 w-px bg-border/60" />
          <span>Auto-Classify</span>
        </div>
      </div>
    </div>
  );
}
