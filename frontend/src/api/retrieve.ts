import { apiClient } from "@/api/client";
import type { ApiEnvelope } from "@/types";

export interface RetrieveChunk {
  id: number;
  workspace_id: string;
  filename: string;
  chunk_id: number;
  document_id: string;
  owner_id: string;
  text: string;
}

export async function retrieveChunks(query: string): Promise<RetrieveChunk[]> {
  const response = await apiClient.post<ApiEnvelope<{ results: RetrieveChunk[] }>>(
    "/retrieve",
    { query },
  );
  return response.data.data?.results ?? [];
}