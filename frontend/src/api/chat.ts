import { apiClient } from "@/api/client";

/** A document chunk the backend used while answering (RAG path only). */
export interface ChatSourceChunk {
  filename: string;
  chunk_id: number;
}

export interface ChatResponse {
  provider: string;
  model: string;
  answer: string;
  /** Backend routing decision: "general" | "document" | "metadata". */
  category?: string;
  /** Chunks that contributed to the answer; empty unless retrieval was used. */
  sources?: ChatSourceChunk[];
}

export async function chatUser(question: string): Promise<ChatResponse> {
  const response = await apiClient.post<ChatResponse>("/chat/", { question });
  return response.data;
}