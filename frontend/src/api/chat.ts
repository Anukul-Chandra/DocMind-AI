import { apiClient } from "@/api/client";

export interface ChatResponse {
  provider: string;
  model: string;
  answer: string;
}

export async function chatUser(question: string): Promise<ChatResponse> {
  const response = await apiClient.post<ChatResponse>("/chat/", { question });
  return response.data;
}