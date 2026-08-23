import { useState } from "react";
import { BookOpen, FileText } from "lucide-react";

import type { SourceFile } from "@/types/chat";
import { cn } from "@/lib/utils";

interface ChatSourcesProps {
  sources: SourceFile[];
}

export function ChatSources({ sources }: ChatSourcesProps) {
  const [open, setOpen] = useState(false);
  const totalChunks = sources.reduce((sum, source) => sum + source.chunkIds.length, 0);

  return (
    <div className="w-full max-w-[85%]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="chat-sources-list"
        className={cn(
          "flex items-center gap-1.5 text-xs transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded-sm",
          "text-brand/70",
        )}
      >
        <BookOpen className="size-3.5" aria-hidden="true" />
        {open
          ? "Hide sources"
          : `View ${sources.length} source${sources.length === 1 ? "" : "s"} · ${totalChunks} chunk${totalChunks === 1 ? "" : "s"}`}
      </button>
      {open && (
        <ul
          id="chat-sources-list"
          className="mt-2 space-y-1.5 rounded-lg border border-brand-border/30 bg-brand/3 p-3 shadow-brand/5"
        >
          {sources.map((source) => (
            <li
              key={source.filename}
              className="flex items-center gap-2 text-xs text-muted-foreground"
            >
              <FileText className="size-3.5 shrink-0 text-brand/60" aria-hidden="true" />
              <span className="truncate" title={source.filename}>
                {source.filename}
              </span>
              <span className="ml-auto shrink-0 inline-flex items-center rounded-full bg-brand/10 px-2 py-0.5 text-brand text-[10px] font-medium ring-1 ring-brand-border/30">
                {source.chunkIds.length}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}