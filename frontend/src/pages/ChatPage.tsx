import { useEffect, useRef, useState } from "react";
import { AlertCircle, MessagesSquare } from "lucide-react";

import { ApiError } from "@/api/client";
import { chatUser } from "@/api/chat";
import { retrieveChunks, type RetrieveChunk } from "@/api/retrieve";
import { ChatInput } from "@/components/chat/ChatInput";
import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import { TypingIndicator } from "@/components/chat/TypingIndicator";
import type { ChatMessage, SourceFile } from "@/types/chat";

const EXAMPLE_QUESTIONS = [
  "What is the main topic of my documents?",
  "Summarize the key findings.",
  "Explain the most important details.",
];

function toSources(chunks: RetrieveChunk[]): SourceFile[] {
  const byFilename = new Map<string, number[]>();
  for (const chunk of chunks) {
    const ids = byFilename.get(chunk.filename) ?? [];
    if (!ids.includes(chunk.chunk_id)) {
      ids.push(chunk.chunk_id);
    }
    byFilename.set(chunk.filename, ids);
  }
  return [...byFilename.entries()].map(([filename, chunkIds]) => ({
    filename,
    chunkIds,
  }));
}

function EmptyState({ onExample }: { onExample: (text: string) => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 p-8 text-center">
      <span className="flex size-14 items-center justify-center rounded-full bg-brand/10">
        <MessagesSquare className="size-7 text-brand" aria-hidden="true" />
      </span>
      <div className="space-y-1">
        <p className="font-medium">Ask DocMind about your documents</p>
        <p className="text-sm text-muted-foreground">
          Questions are answered using your indexed documents.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {EXAMPLE_QUESTIONS.map((question, index) => (
          <button
            key={question}
            type="button"
            onClick={() => onExample(question)}
            style={{ animationDelay: `${150 + index * 60}ms` }}
            className="docmind-rise rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-[transform,border-color,background-color,color] hover:-translate-y-0.5 hover:border-brand/30 hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  async function handleSend(question: string) {
    const text = question.trim();
    if (!text || isLoading) return;
    setError(null);
    setMessages((previous) => [
      ...previous,
      { id: crypto.randomUUID(), role: "user", content: text },
    ]);
    setIsLoading(true);
    try {
      const [chatResult, retrieveResult] = await Promise.allSettled([
        chatUser(text),
        retrieveChunks(text),
      ]);
      if (chatResult.status === "rejected") {
        const reason = chatResult.reason;
        setError(
          reason instanceof ApiError
            ? reason.message
            : "Failed to get an answer. Please try again.",
        );
        return;
      }
      const { answer, provider, model } = chatResult.value;
      const sources =
        retrieveResult.status === "fulfilled" && retrieveResult.value.length > 0
          ? toSources(retrieveResult.value)
          : undefined;
      setMessages((previous) => [
        ...previous,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: answer,
          provider,
          model,
          sources,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="docmind-page flex h-full min-h-0 flex-col">
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {messages.length === 0 ? (
          <EmptyState onExample={(question) => void handleSend(question)} />
        ) : (
          <div className="mx-auto mt-auto flex w-full max-w-3xl flex-col gap-4 p-4 pb-2 sm:p-6 sm:pb-2 lg:p-8 lg:pb-2">
            {messages.map((message) => (
              <ChatMessageBubble key={message.id} message={message} />
            ))}
            {isLoading && (
              <div className="flex items-start">
                <TypingIndicator />
              </div>
            )}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div className="shrink-0 border-t bg-background p-4 lg:px-8">
        <div className="mx-auto w-full max-w-3xl space-y-2">
          {error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0">{error}</span>
            </div>
          )}
          <ChatInput
            onSend={(text) => void handleSend(text)}
            disabled={isLoading}
          />
        </div>
      </div>
    </div>
  );
}