import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, MessagesSquare } from "lucide-react";
import { useOutletContext } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { chatUser, classifyChat, type ChatSourceChunk } from "@/api/chat";
import type { ChatShellContext } from "@/layouts/ProtectedShell";
import { ChatInput } from "@/components/chat/ChatInput";
import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import { TypingIndicator, type IndicatorCategory } from "@/components/chat/TypingIndicator";
import {
  conversationsKey,
  conversationsMessagesKey,
  useConversationMessages,
  useCreateConversation,
} from "@/hooks/use-conversations";
import type { ChatMessage, SourceFile } from "@/types/chat";
import type { ConversationMessage } from "@/types/conversations";
import { cn } from "@/lib/utils";

const EXAMPLE_QUESTIONS = [
  "What is the main topic of my documents?",
  "Summarize the key findings.",
  "Explain the most important details.",
];

/** Group backend-reported chunks into per-file sources for display. */
function toSources(chunks: ChatSourceChunk[]): SourceFile[] {
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
    <div className="flex h-full flex-col items-center justify-center gap-6 p-8 text-center">
      <span className="relative flex size-14 items-center justify-center rounded-2xl bg-brand/10 text-brand ring-1 ring-inset ring-brand-border/30 shadow-[0_0_32px_-12px_var(--brand)]">
        <MessagesSquare className="size-7" aria-hidden="true" />
        <span
          className="docmind-scan-pulse absolute -right-1 -top-1 size-2.5 rounded-full bg-brand shadow-[0_0_8px_var(--brand)] ring-2 ring-background"
          aria-hidden="true"
        />
      </span>
      <div className="space-y-1.5">
        <p className="font-semibold tracking-tight text-foreground">Query the knowledge index</p>
        <p className="text-sm text-muted-foreground">
          Answers are grounded in your indexed documents, with sources attached.
        </p>
      </div>
      <div className="flex w-full max-w-md flex-col gap-2 sm:flex-row sm:justify-center">
        {EXAMPLE_QUESTIONS.map((question, index) => (
          <button
            key={question}
            type="button"
            onClick={() => onExample(question)}
            style={{ animationDelay: `${150 + index * 60}ms` }}
            className={cn(
              "docmind-nav-item docmind-rise group flex flex-1 items-center gap-2.5 rounded-xl border border-border/60 bg-card/50 px-3.5 py-2.5 text-left transition-all duration-200",
              "hover:-translate-y-0.5 hover:border-brand/35 hover:bg-brand/5 hover:shadow-elevation-2",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            )}
          >
            <span className="docmind-label shrink-0 text-brand/70 tabular-nums" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="truncate text-xs text-muted-foreground transition-colors duration-200 group-hover:text-foreground">
              {question}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function readFileAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function toChatMessage(message: ConversationMessage, id: string): ChatMessage {
  return { id, role: message.role, content: message.content };
}

export function ChatPage() {
  const queryClient = useQueryClient();
  const { activeChatId: activeId, setActiveChatId } =
    useOutletContext<ChatShellContext>();
  const [isLoading, setIsLoading] = useState(false);
  const [loadingCategory, setLoadingCategory] = useState<IndicatorCategory>("general");
  const [loadingHasImages, setLoadingHasImages] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const createMutation = useCreateConversation();
  const { data: storedMessages = [], isFetching } = useConversationMessages(activeId);

  const messages: ChatMessage[] = storedMessages.map((message, index) =>
    toChatMessage(
      message,
      `${activeId ?? "draft"}-${index}-${message.role}`,
    ),
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [storedMessages, isLoading]);

  // Keep the viewport pinned to the newest content while a response reveals.
  const scrollToLatest = useCallback(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, []);

  function appendMessages(
    conversationId: string | null,
    updater: (previous: ConversationMessage[] | undefined) => ConversationMessage[],
  ) {
    if (!conversationId) return;
    queryClient.setQueryData<ConversationMessage[]>(
      conversationsMessagesKey(conversationId),
      updater,
    );
  }

  async function ensureConversation(): Promise<string | null> {
    if (activeId) return activeId;
    try {
      const created = await createMutation.mutateAsync();
      setActiveChatId(created.conversation_id);
      return created.conversation_id;
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not start a new conversation.",
      );
      return null;
    }
  }

  async function handleSend(question: string, attachments: File[] = []) {
    const text = question.trim();
    if (!text || isLoading) return;
    setError(null);

    setIsLoading(true);
    setLoadingCategory("general");

    const conversationId = await ensureConversation();
    if (!conversationId) {
      setIsLoading(false);
      return;
    }

    // Create data URLs so image attachments survive browser refresh
    const imageUrls = await Promise.all(attachments.map(readFileAsDataURL));
    appendMessages(conversationId, (previous) => [
      ...(previous ?? []),
      {
        role: "user",
        content: text,
        ...(imageUrls.length > 0 ? { images: imageUrls } : {}),
      },
    ]);

    const hasImages = attachments.length > 0;
    setLoadingHasImages(hasImages);

    try {
      const classifyResult = await classifyChat(text);
      if (classifyResult.category === "document" || classifyResult.category === "metadata") {
        setLoadingCategory(classifyResult.category);
      }
    } catch {
      // If classify fails, fall back to general
    }

    try {
      const { answer, provider, model, sources } = await chatUser(
        text,
        attachments,
        conversationId,
      );
      appendMessages(conversationId, (previous) => [
        ...(previous ?? []),
        {
          role: "assistant",
          content: answer,
          provider,
          model,
          sources: sources && sources.length > 0 ? toSources(sources) : undefined,
        },
      ]);
      void queryClient.invalidateQueries({ queryKey: conversationsKey });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to get an answer. Please try again.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  const showEmptyState = storedMessages.length === 0 && !isLoading;

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#080B0A]">
      <div className="flex min-h-0 flex-1">
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain">
            {showEmptyState ? (
              <EmptyState onExample={(question) => void handleSend(question)} />
            ) : (
              <div className="mx-auto mt-auto flex w-full max-w-3xl flex-col gap-4 p-4 pb-8">
                {isFetching && storedMessages.length === 0 && activeId && (
                  <p className="px-2 text-sm text-muted-foreground/60">
                    Loading conversation…
                  </p>
                )}
                {messages.map((message, index) => {
                  const isLatest = index === messages.length - 1 && message.role === "assistant";
                  return (
                    <ChatMessageBubble
                      key={message.id}
                      message={message}
                      animate={isLatest}
                      onGrow={isLatest ? scrollToLatest : undefined}
                    />
                  );
                })}
                {isLoading && (
                  <div className="flex items-start">
                    <TypingIndicator category={loadingCategory} hasImages={loadingHasImages} />
                  </div>
                )}
                <div ref={endRef} />
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="relative w-full shrink-0 rounded-2xl border border-white/[0.06] bg-[#101C18] p-4 px-8 shadow-[0_4px_16px_-4px_rgba(0,0,0,0.5)] backdrop-blur-xl sm:mx-auto sm:max-w-3xl">
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" aria-hidden="true" />
            <div className="mx-auto w-full max-w-3xl space-y-2">
              {error && (
                <div
                  role="alert"
                  className="flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive backdrop-blur-sm"
                >
                  <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                  <span className="min-w-0">{error}</span>
                </div>
              )}
              <ChatInput
                onSend={(text, attachments) => void handleSend(text, attachments)}
                disabled={isLoading}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
