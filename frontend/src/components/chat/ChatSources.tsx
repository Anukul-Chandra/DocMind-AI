import { useState } from "react";
import { BookOpen, ChevronDown, FileText } from "lucide-react";

import type { SourceFile } from "@/types/chat";
import { cn } from "@/lib/utils";

function formatChunkIds(chunkIds: number[]): string {
  const sorted = [...chunkIds].sort((a, b) => a - b);
  const shown = sorted.slice(0, 4).map((id) => `#${String(id).padStart(2, "0")}`);
  const remaining = sorted.length - shown.length;
  return remaining > 0 ? `${shown.join(" ")} +${remaining}` : shown.join(" ");
}

interface ChatSourcesProps {
  sources: SourceFile[];
}

export function ChatSources({ sources }: ChatSourcesProps) {
  const [open, setOpen] = useState(false);
  const totalChunks = sources.reduce((sum, source) => sum + source.chunkIds.length, 0);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="chat-sources-list"
        className={cn(
          "flex w-full items-center gap-2 rounded-lg py-2 text-left transition-colors duration-200",
          "text-muted-foreground hover:bg-brand/5 hover:text-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-inset",
        )}
      >
        <BookOpen className="size-3.5 shrink-0 text-brand/70" aria-hidden="true" />
        <span className="min-w-0 truncate text-xs font-medium">
          {sources.length} source{sources.length === 1 ? "" : "s"} ·{" "}
          <span className="tabular-nums">{totalChunks}</span> chunk{totalChunks === 1 ? "" : "s"}
        </span>
        <span className="docmind-label ml-auto shrink-0 pl-3 text-muted-foreground/45" aria-hidden="true">
          Retrieved Context
        </span>
        <ChevronDown
          className={cn(
            "size-3.5 shrink-0 text-muted-foreground/60 transition-transform duration-200",
            open && "rotate-180",
          )}
          aria-hidden="true"
        />
      </button>

      {/* Smooth height transition; collapses fully when closed */}
      <div
        id="chat-sources-list"
        className={cn(
          "grid transition-[grid-template-rows] duration-300 ease-out",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="min-h-0 overflow-hidden">
          <ul className="mb-2 divide-y divide-border/40 overflow-hidden rounded-xl border border-border/40 bg-card/30">
            {sources.map((source, index) => (
              <li
                key={source.filename}
                className="flex items-center gap-3 px-3 py-2 transition-colors duration-200 hover:bg-brand/5"
              >
                <span
                  className="docmind-label w-5 shrink-0 tabular-nums text-muted-foreground/50"
                  aria-hidden="true"
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-brand/8 text-brand/80 ring-1 ring-inset ring-brand-border/20">
                  <FileText className="size-3.5" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium text-foreground" title={source.filename}>
                    {source.filename}
                  </span>
                  <span className="docmind-label mt-0.5 block truncate text-[0.625rem] text-muted-foreground/55">
                    {formatChunkIds(source.chunkIds)}
                  </span>
                </span>
                <span className="docmind-label shrink-0 tabular-nums text-muted-foreground/60">
                  {source.chunkIds.length} ch
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
