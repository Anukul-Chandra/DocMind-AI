import { useState } from "react";
import { BookOpen, FileText } from "lucide-react";

import type { SourceFile } from "@/types/chat";

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
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <BookOpen className="size-3.5" aria-hidden="true" />
        {open ? "Hide sources" : `View ${sources.length} source${sources.length === 1 ? "" : "s"}`}
      </button>
      {open && (
        <ul className="mt-2 space-y-1.5 rounded-lg border bg-muted/40 p-3">
          {sources.map((source) => (
            <li
              key={source.filename}
              className="flex items-center gap-2 text-xs text-muted-foreground"
            >
              <FileText className="size-3.5 shrink-0" aria-hidden="true" />
              <span className="truncate" title={source.filename}>
                {source.filename}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}