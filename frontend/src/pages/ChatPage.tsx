import { MessagesSquare } from "lucide-react";

import { PageHeader } from "@/components/app/PageHeader";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function ChatPage() {
  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 p-6 lg:p-8">
      <PageHeader
        title="Chat"
        description="Ask questions and get grounded answers from your documents."
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ask DocMind</CardTitle>
          <CardDescription>
            Your conversations will appear here.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center justify-center gap-3 py-12 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-muted">
            <MessagesSquare className="size-6 text-muted-foreground" aria-hidden="true" />
          </span>
          <p className="text-sm text-muted-foreground">
            Chat with your documents is coming in a later phase.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
