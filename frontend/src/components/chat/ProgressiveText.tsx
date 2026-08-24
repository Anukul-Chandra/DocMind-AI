import { useCallback, useEffect, useRef, useState } from "react";

import {
  parseMarkdownBlocks,
  type MdBlock,
} from "@/lib/markdown-blocks";
import { cn } from "@/lib/utils";

/** Presentation-only typewriter for an already received answer. */
const MIN_DURATION_MS = 900;
const MAX_DURATION_MS = 5200;
const CHARS_PER_SECOND = 340;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return true;
  }
}

interface ProgressiveTextProps {
  content: string;
  /** Only the most recent assistant message animates; everything else renders statically. */
  active: boolean;
  /** Called when the rendered height changes so the chat can follow the growth. */
  onGrow?: () => void;
}

export function ProgressiveText({ content, active, onGrow }: ProgressiveTextProps) {
  const reducedMotion = useRef(prefersReducedMotion()).current;
  const effectiveActive = active && !reducedMotion && content.length > 0;

  const [revealed, setRevealed] = useState(() => (effectiveActive ? 1 : content.length));
  const [done, setDone] = useState(!effectiveActive);
  const frameRef = useRef<number | null>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const lastHeightRef = useRef(0);
  const onGrowRef = useRef(onGrow);
  onGrowRef.current = onGrow;

  useEffect(() => {
    if (!effectiveActive) {
      setRevealed(content.length);
      setDone(true);
      return;
    }
    setRevealed(1);
    setDone(false);

    const total = content.length;
    const duration = Math.min(
      MAX_DURATION_MS,
      Math.max(MIN_DURATION_MS, (total / CHARS_PER_SECOND) * 1000),
    );
    const start = performance.now();
    let cancelled = false;

    const tick = (now: number) => {
      if (cancelled) return;
      const t = Math.min((now - start) / duration, 1);
      // Ease-out: the head of the answer appears promptly, the tail settles.
      const eased = 1 - Math.pow(1 - t, 2.2);
      const count = t >= 1 ? total : Math.max(1, Math.round(total * eased));
      setRevealed(count);
      if (t >= 1) {
        setDone(true);
        return;
      }
      frameRef.current = requestAnimationFrame(tick);
    };

    frameRef.current = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [effectiveActive, content]);

  // Follow vertical growth while revealing.
  useEffect(() => {
    if (done || !onGrowRef.current || !hostRef.current) return;
    const height = hostRef.current.scrollHeight;
    if (height !== lastHeightRef.current) {
      lastHeightRef.current = height;
      onGrowRef.current();
    }
  }, [revealed, done]);

  const finishNow = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    setRevealed(content.length);
    setDone(true);
  }, [content.length]);

  const revealedText = done ? content : content.slice(0, revealed);
  const blocks = parseMarkdownBlocks(revealedText);
  const showCaret = effectiveActive && !done;

  function renderCaret() {
    return showCaret ? <span className="docmind-caret" aria-hidden="true" /> : null;
  }

  function renderBlock(block: MdBlock, isLast: boolean) {
    switch (block.type) {
      case "heading": {
        if (block.level <= 1) {
          return (
            <h3 className="pt-1 text-lg font-semibold tracking-tight text-foreground">
              {block.text}
              {isLast && renderCaret()}
            </h3>
          );
        }
        if (block.level === 2) {
          return (
            <h4 className="text-base font-semibold tracking-tight text-foreground">
              {block.text}
              {isLast && renderCaret()}
            </h4>
          );
        }
        return (
          <h5 className="text-sm font-semibold tracking-tight text-foreground/90">
            {block.text}
            {isLast && renderCaret()}
          </h5>
        );
      }
      case "paragraph":
        return (
          <p className="whitespace-pre-wrap">
            {block.text}
            {isLast && renderCaret()}
          </p>
        );
      case "list":
        return (
          <ul className="space-y-1.5">
            {block.items.map((item, index) => (
              <li key={index} className="flex gap-2.5">
                <span
                  className={cn(
                    "mt-0.5 shrink-0 select-none font-mono text-xs leading-relaxed",
                    item.marker === null ? "text-brand/80" : "text-muted-foreground",
                  )}
                  aria-hidden={item.marker === null ? true : undefined}
                >
                  {item.marker ?? "•"}
                </span>
                <span className="min-w-0 flex-1 whitespace-pre-wrap">
                  {item.text}
                  {isLast && index === block.items.length - 1 && renderCaret()}
                </span>
              </li>
            ))}
          </ul>
        );
      case "code":
        return (
          <div className="overflow-hidden rounded-xl border border-border/50 bg-background/50">
            {block.lang && (
              <div className="docmind-label border-b border-border/40 px-3 py-1 text-muted-foreground/50">
                {block.lang}
              </div>
            )}
            <pre className="overflow-x-auto px-4 py-3 font-mono text-xs leading-relaxed text-foreground/90">
              <code>
                {block.lines.join("\n")}
                {isLast && renderCaret()}
              </code>
            </pre>
          </div>
        );
    }
  }

  return (
    <div
      ref={hostRef}
      onClick={showCaret ? finishNow : undefined}
      className={cn("space-y-3", showCaret && "cursor-pointer")}
      title={showCaret ? "Click to reveal the full response" : undefined}
    >
      {blocks.map((block, index) => (
        <div key={index}>{renderBlock(block, index === blocks.length - 1)}</div>
      ))}
      {blocks.length === 0 && showCaret && <span className="docmind-caret" aria-hidden="true" />}
    </div>
  );
}
