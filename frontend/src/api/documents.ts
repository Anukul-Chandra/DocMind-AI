import { apiClient } from "@/api/client";
import type { ApiEnvelope } from "@/types";

export interface Document {
  document_id: string;
  workspace_id: string;
  filename: string;
  uploaded_at: string;
  chunk_count: number;
  deleted: boolean;
  owner_id: string;
  classification: string;
  extracted_data?: Record<string, unknown> | null;
}

export interface UploadResult {
  document_id: string;
  workspace_id: string;
  filename: string;
  chunks: number;
  embeddings: number;
  status: string;
}

export interface DeleteResult {
  document_id: string;
  status: string;
}

export async function listDocuments(): Promise<Document[]> {
  const response = await apiClient.get<ApiEnvelope<Document[]>>("/documents");
  return response.data.data ?? [];
}

export async function uploadDocument(
  file: File,
  onUploadProgress?: (percent: number) => void,
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post<ApiEnvelope<UploadResult>>(
    "/documents/upload",
    formData,
    {
      onUploadProgress: (event) => {
        if (!onUploadProgress) return;
        const total = event.total ?? file.size;
        if (!total) return;
        onUploadProgress(Math.min(100, Math.round((event.loaded / total) * 100)));
      },
    },
  );
  return response.data.data!;
}

export async function deleteDocument(
  documentId: string,
): Promise<DeleteResult> {
  const response = await apiClient.delete<ApiEnvelope<DeleteResult>>(
    `/documents/${documentId}`,
  );
  return response.data.data!;
}
