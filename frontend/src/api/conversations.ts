import { apiClient } from "@/api/client";
import type { ApiEnvelope } from "@/types";
import type {
  ConversationMessage,
  ConversationMeta,
} from "@/types/conversations";

export async function listConversations(): Promise<ConversationMeta[]> {
  const response = await apiClient.get<ApiEnvelope<ConversationMeta[]>>(
    "/conversations",
  );
  return response.data.data ?? [];
}

export async function createConversation(): Promise<ConversationMeta> {
  const response = await apiClient.post<ApiEnvelope<ConversationMeta>>(
    "/conversations",
  );
  return response.data.data!;
}

export async function getConversation(
  conversationId: string,
): Promise<ConversationMeta> {
  const response = await apiClient.get<ApiEnvelope<ConversationMeta>>(
    `/conversations/${conversationId}`,
  );
  return response.data.data!;
}

export async function getConversationMessages(
  conversationId: string,
): Promise<ConversationMessage[]> {
  const response = await apiClient.get<
    ApiEnvelope<ConversationMessage[]>
  >(`/conversations/${conversationId}/messages`);
  return response.data.data ?? [];
}

export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<ConversationMeta> {
  const response = await apiClient.patch<ApiEnvelope<ConversationMeta>>(
    `/conversations/${conversationId}`,
    { title },
  );
  return response.data.data!;
}

export async function deleteConversation(
  conversationId: string,
): Promise<void> {
  await apiClient.delete(`/conversations/${conversationId}`);
}
