import { useState, type FormEvent } from "react";
import { Pencil } from "lucide-react";

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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRenameConversation } from "@/hooks/use-conversations";

export function RenameConversationDialog({
  conversationId,
  title,
}: {
  conversationId: string;
  title: string;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(title);
  const [error, setError] = useState<string | null>(null);
  const renameMutation = useRenameConversation();

  const canSubmit = value.trim().length > 0 && !renameMutation.isPending;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setError(null);
    renameMutation
      .mutateAsync({ conversationId, title: value.trim() })
      .then(() => setOpen(false))
      .catch((err) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "Failed to rename the conversation.",
        );
      });
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setValue(title);
          setError(null);
        }
      }}
    >
      <AlertDialogTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          role="menuitem"
          className="w-full justify-start gap-2 px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <Pencil className="size-3.5" aria-hidden="true" />
          Rename
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <form onSubmit={handleSubmit}>
          <AlertDialogHeader>
            <AlertDialogTitle>Rename conversation</AlertDialogTitle>
            <AlertDialogDescription>
              Give this conversation a name you will recognise later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Input
            autoFocus
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Conversation title"
            className="mt-4"
            aria-label="Conversation title"
          />
          {error && (
            <div
              className="mt-3 flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              role="alert"
            >
              {error}
            </div>
          )}
          <AlertDialogFooter className="mt-4">
            <AlertDialogCancel type="button" disabled={renameMutation.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              type="submit"
              disabled={!canSubmit}
            >
              {renameMutation.isPending ? "Saving…" : "Save"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  );
}
