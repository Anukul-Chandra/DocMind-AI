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

export interface ClassifyResponse {
  category: string;
}

export async function classifyChat(question: string): Promise<ClassifyResponse> {
  const formData = new FormData();
  formData.append("question", question);
  const response = await apiClient.post<ClassifyResponse>("/chat/classify", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function chatUser(question: string, attachments: File[] = []): Promise<ChatResponse> {
  const formData = new FormData();
  formData.append("question", question);
  for (const file of attachments) {
    formData.append("attachments", file);
  }
  const response = await apiClient.post<ChatResponse>("/chat/", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}