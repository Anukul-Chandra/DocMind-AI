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
  /** The conversation the exchange was recorded into, if any. */
  conversation_id?: string | null;
}

export interface ClassifyResponse {
  category: string;
}

export async function classifyChat(question: string): Promise<ClassifyResponse> {
  const formData = new FormData();
  formData.append("question", question);
  const response = await apiClient.post<ClassifyResponse>("/chat/classify", formData);
  return response.data;
}

export async function chatUser(
  question: string,
  attachments: File[] = [],
  conversationId?: string | null,
): Promise<ChatResponse> {
  const formData = new FormData();
  formData.append("question", question);
  if (conversationId) {
    formData.append("conversation_id", conversationId);
  }
  for (const file of attachments) {
    formData.append("attachments", file);
  }
  const response = await apiClient.post<ChatResponse>("/chat/", formData);
  return response.data;
}

/**
 * Regenerate the assistant response for one user message as a true branch.
 * The backend truncates the stored conversation to the messages preceding
 * `messageIndex`, generates against that truncated context, and replaces the
 * superseded branch. Pass `question` to edit, omit it for pure regenerate
 * (stored text and image attachments are reused server-side).
 */
export async function chatRegenerate(
  conversationId: string,
  messageIndex: number,
  question?: string | null,
): Promise<ChatResponse> {
  const formData = new FormData();
  formData.append("conversation_id", conversationId);
  formData.append("message_index", String(messageIndex));
  if (question !== undefined && question !== null) {
    formData.append("question", question);
  }
  const response = await apiClient.post<ChatResponse>("/chat/regenerate", formData);
  return response.data;
}
