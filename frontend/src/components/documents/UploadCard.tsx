import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useDropzone, type FileRejection } from "react-dropzone";
import {
  Check,
  CloudUpload,
  FileWarning,
  Sparkles,
} from "lucide-react";

import { ApiError } from "@/api/client";
import type { Document, UploadResult } from "@/api/documents";
import {
  ScanCard,
  type UploadStage,
} from "@/components/documents/ScanCard";
import { documentsKey, useUploadDocument } from "@/hooks/use-documents";
import { documentTypeLabel } from "@/lib/document-types";
import { cn } from "@/lib/utils";

export const MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024;
export const MAX_UPLOAD_SIZE_LABEL = "50 MiB";

const PROCESSING_STAGES: readonly UploadStage[] = [
  { key: "upload", label: "Uploading document" },
  { key: "scan", label: "Scanning & extracting" },
  { key: "classify", label: "Classifying content" },
  { key: "index", label: "Indexing & embedding" },
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
  const [activeStage, setActiveStage] = useState(0);

  useEffect(() => {
    if (status !== "processing") return;
    if (activeStage >= PROCESSING_STAGES.length - 1) return;
    const timer = setTimeout(() => setActiveStage((stage) => stage + 1), 900);
    return () => clearTimeout(timer);
  }, [status, activeStage]);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setResult(null);
      setClassification(null);
      setFileName(file.name);
      setActiveStage(0);
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
        const uploaded = await upload.mutateAsync(file);
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
        stages={PROCESSING_STAGES}
        activeStage={activeStage}
      />
    );
  }

  return (
    <div className="space-y-3">
      {result && (
        <div
          className="docmind-rise flex items-start gap-3 rounded-xl border border-brand-border/30 bg-brand/3 shadow-brand/10"
          role="status"
        >
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand ring-1 ring-brand-border/30">
            <Check className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Document indexed successfully</p>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              {result.filename}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center rounded-full border border-brand-border/30 bg-brand/5 px-2 py-0.5 text-muted-foreground">
                {result.chunks} {result.chunks === 1 ? "chunk" : "chunks"}
              </span>
              <span className="inline-flex items-center rounded-full border border-brand-border/30 bg-brand/5 px-2 py-0.5 text-muted-foreground">
                {result.embeddings} embeddings
              </span>
              {classification && classification !== "unknown" && (
                <span className="inline-flex items-center gap-1 rounded-full bg-brand/10 px-2 py-0.5 font-medium text-brand ring-1 ring-brand-border/30">
                  <Sparkles className="size-3" aria-hidden="true" />
                  {documentTypeLabel(classification)}
                </span>
              )}
            </div>
          </div>
        </div>
      )}
      {error && (
        <div
          className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
        >
          <FileWarning className="size-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0">{error}</span>
        </div>
      )}
      <div
        {...getRootProps()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed bg-card/40 px-6 py-10 text-center transition-all duration-200",
          "hover:border-brand/50 hover:bg-brand/[0.03]",
          "focus-visible:outline-none focus-visible:border-brand focus-visible:ring-brand/50 focus-visible:ring-[3px]",
          isDragActive && "border-brand bg-brand/5 shadow-brand/10 ring-1 ring-brand/20",
          isDragReject && "border-destructive bg-destructive/5",
        )}
      >
        <input {...getInputProps()} />
        <span
          className={cn(
            "flex size-12 items-center justify-center rounded-full bg-brand/5 transition-all duration-200",
            isDragActive && "bg-brand/15 ring-2 ring-brand/30",
          )}
        >
          <CloudUpload
            className={cn(
              "size-6 text-brand/60 transition-all duration-200",
              isDragActive && "text-brand scale-110",
            )}
            aria-hidden="true"
          />
        </span>
        <p className="text-sm font-medium">
          {isDragActive ? "Drop the PDF here" : "Drag & drop your PDF here"}
        </p>
        <p className="text-sm text-muted-foreground">
          or click to browse · PDF only, up to {MAX_UPLOAD_SIZE_LABEL}
        </p>
      </div>
    </div>
  );
}