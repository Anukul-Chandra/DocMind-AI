import { useState } from "react";
import { BookOpen, FileText } from "lucide-react";

import type { SourceFile } from "@/types/chat";
import { cn } from "@/lib/utils";

interface ChatSourcesProps {
  sources: SourceFile[];
}

export function ChatSources({ sources }: ChatSourcesProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="w-full max-w-[85%]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="chat-sources-list"
        className={cn(
          "flex items-center gap-1.5 text-xs font-medium transition-all duration-200 hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30 rounded-lg px-2 py-1",
          "text-brand/70 hover:bg-brand/5",
        )}
      >
        <BookOpen className="size-3.5" aria-hidden="true" />
        {open
          ? "Hide sources"
          : `View {sources.length} source{sources.length === 1 ? "" : "s"} · {totalChunks} chunk{totalChunks === 1 ? "" : "s"}`}
      </button>
      {open && (
        <ul
          id="chat-sources-list"
          className="mt-3 space-y-2 rounded-xl border border-brand-border/30 bg-brand/3 p-4 shadow-brand/10 animate-in fade-in-20 slide-in-from-top-4"
        >
          {sources.map((source, index) => (
            <li
              key={source.filename}
              className="flex items-center gap-3 text-sm text-muted-foreground transition-colors hover:text-foreground"
              style={{ animationDelay: `${index * 30}ms` }}
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand ring-1 ring-brand-border/30">
                <FileText className="size-4" aria-hidden="true" />
              </span>
              <span className="truncate flex-1 font-medium text-foreground" title={source.filename}>
                {source.filename}
              </span>
              <span className="ml-auto shrink-0 inline-flex items-center gap-1 rounded-full bg-brand/10 px-2.5 py-1 text-brand text-xs font-medium ring-1 ring-brand-border/30">
                <span className="size-1.5 rounded-full bg-brand/50" aria-hidden="true" />
                {source.chunkIds.length} chunks
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}