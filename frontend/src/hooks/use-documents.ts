import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteDocument,
  listDocuments,
  uploadDocument,
} from "@/api/documents";

export const documentsKey = ["documents"] as const;

export function useDocuments() {
  return useQuery({
    queryKey: documentsKey,
    queryFn: listDocuments,
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      onUploadProgress,
    }: {
      file: File;
      onUploadProgress?: (percent: number) => void;
    }) => uploadDocument(file, onUploadProgress),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentsKey });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: documentsKey });
    },
  });
}
