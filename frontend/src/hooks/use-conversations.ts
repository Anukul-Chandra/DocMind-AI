import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  createConversation,
  deleteConversation,
  getConversationMessages,
  listConversations,
  renameConversation,
} from "@/api/conversations";

export const conversationsKey = ["conversations"] as const;

export function conversationsMessagesKey(conversationId: string) {
  return ["conversations", conversationId, "messages"] as const;
}

export function useConversations() {
  return useQuery({
    queryKey: conversationsKey,
    queryFn: listConversations,
  });
}

export function useConversationMessages(conversationId: string | null) {
  return useQuery({
    queryKey: conversationsMessagesKey(conversationId ?? ""),
    queryFn: () => getConversationMessages(conversationId!),
    enabled: conversationId !== null,
  });
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createConversation,
    onSuccess: (conversation) => {
      void queryClient.invalidateQueries({ queryKey: conversationsKey });
      void queryClient.setQueryData(
        conversationsMessagesKey(conversation.conversation_id),
        [],
      );
    },
  });
}

export function useRenameConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      conversationId,
      title,
    }: {
      conversationId: string;
      title: string;
    }) => renameConversation(conversationId, title),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: conversationsKey });
    },
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: conversationsKey });
    },
  });
}
