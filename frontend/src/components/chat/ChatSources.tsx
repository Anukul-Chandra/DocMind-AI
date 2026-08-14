import { useState } from "react";
import { BookOpen, FileText } from "lucide-react";

import type { SourceFile } from "@/types/chat";

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
        className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
      >
        <BookOpen className="size-3.5" aria-hidden="true" />
        {open
          ? "Hide sources"
          : `View ${sources.length} source${sources.length === 1 ? "" : "s"} · ${totalChunks} chunk${totalChunks === 1 ? "" : "s"}`}
      </button>
      {open && (
        <ul
          id="chat-sources-list"
          className="mt-2 space-y-1.5 rounded-lg border bg-muted/40 p-3"
        >
          {sources.map((source) => (
            <li
              key={source.filename}
              className="flex items-center gap-2 text-xs text-muted-foreground"
            >
              <FileText className="size-3.5 shrink-0" aria-hidden="true" />
              <span className="truncate" title={source.filename}>
                {source.filename}
              </span>
              <span className="ml-auto shrink-0">
                {source.chunkIds.length}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}