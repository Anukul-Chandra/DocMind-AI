import { useState } from "react";
import { Trash2 } from "lucide-react";

import { ApiError } from "@/api/client";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { useDeleteConversation } from "@/hooks/use-conversations";
import { cn } from "@/lib/utils";

export function DeleteConversationDialog({
  conversationId,
  title,
}: {
  conversationId: string;
  title: string;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deleteMutation = useDeleteConversation();

  async function handleConfirm() {
    setError(null);
    try {
      await deleteMutation.mutateAsync(conversationId);
      setOpen(false);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to delete the conversation.",
      );
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          role="menuitem"
          className="w-full justify-start gap-2 px-2 py-1.5 text-xs text-destructive hover:text-destructive"
        >
          <Trash2 className="size-3.5" aria-hidden="true" />
          Delete
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
          <AlertDialogDescription>
            “{title || "Untitled chat"}” and its messages will be permanently
            deleted. This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {error && (
          <div
            className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            role="alert"
          >
            {error}
          </div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleteMutation.isPending}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={(event) => {
              event.preventDefault();
              void handleConfirm();
            }}
            disabled={deleteMutation.isPending}
            className={cn(buttonVariants({ variant: "destructive" }))}
          >
            {deleteMutation.isPending ? "Deleting…" : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
