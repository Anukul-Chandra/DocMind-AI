import { useCallback, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { CheckCircle2, CloudUpload, FileWarning } from "lucide-react";

import { ApiError } from "@/api/client";
import type { UploadResult } from "@/api/documents";
import { ScanCard } from "@/components/documents/ScanCard";
import { useUploadDocument } from "@/hooks/use-documents";
import { cn } from "@/lib/utils";

export const MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024;
export const MAX_UPLOAD_SIZE_LABEL = "50 MiB";

export function UploadCard() {
  const upload = useUploadDocument();
  const [error, setError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<UploadResult | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setUploaded(null);
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        setError("Only PDF files are supported.");
        return;
      }
      if (file.size > MAX_UPLOAD_SIZE_BYTES) {
        setError(`File exceeds the ${MAX_UPLOAD_SIZE_LABEL} upload limit.`);
        return;
      }
      try {
        const result = await upload.mutateAsync(file);
        setUploaded(result);
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "Upload failed. Please try again.",
        );
      }
    },
    [upload],
  );

  const onDrop = useCallback(
    (accepted: File[], rejected: FileRejection[]) => {
      setError(null);
      setUploaded(null);
      if (rejected.length > 0) {
        const codes = rejected[0].errors.map((reason) => reason.code);
        if (codes.includes("file-too-large")) {
          setError(`File exceeds the ${MAX_UPLOAD_SIZE_LABEL} upload limit.`);
        } else if (codes.includes("file-invalid-type")) {
          setError("Only PDF files are supported.");
        } else {
          setError("This file cannot be uploaded.");
        }
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
      disabled: upload.isPending,
    });

  if (upload.isPending) {
    return <ScanCard label="Uploading and indexing your document…" />;
  }

  return (
    <div className="space-y-3">
      {uploaded && (
        <div
          className="flex items-center gap-2 rounded-md border bg-emerald-500/10 px-3 py-2 text-sm text-emerald-600"
          role="status"
        >
          <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
          <span className="truncate">
            {uploaded.filename} indexed successfully ({uploaded.chunks} chunks).
          </span>
        </div>
      )}
      {error && (
        <div
          className="flex items-center gap-2 rounded-md border bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
        >
          <FileWarning className="size-4 shrink-0" aria-hidden="true" />
          {error}
        </div>
      )}
      <div
        {...getRootProps()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed bg-card/40 px-6 py-10 text-center transition-colors",
          isDragActive && "border-primary bg-primary/5",
          isDragReject && "border-destructive",
          upload.isPending && "pointer-events-none opacity-60",
        )}
      >
        <input {...getInputProps()} />
        <span className="flex size-12 items-center justify-center rounded-full bg-muted">
          <CloudUpload
            className="size-6 text-muted-foreground"
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