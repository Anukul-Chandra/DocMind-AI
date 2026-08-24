import { useCallback, useEffect, useRef, useState } from "react";

import { InlineText } from "@/lib/render-inline";
import {
  parseMarkdownBlocks,
  type MdBlock,
} from "@/lib/markdown-blocks";
import { cn } from "@/lib/utils";

/**
 * Presentation-only progressive reveal for an already received answer.
 * The slice is re-parsed as Markdown every frame, so formatting stays
 * visually correct while the text grows top-to-bottom.
 */
const MIN_DURATION_MS = 700;
const MAX_DURATION_MS = 4500;
/** Base pace; actual steps snap to word boundaries for clean chunking. */
const CHARS_PER_SECOND = 420;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return true;
  }
}

/** Advance the cut point to the end of the current word (or separator run). */
function snapToWordBoundary(text: string, index: number): number {
  while (index < text.length && !/\s/.test(text[index])) index += 1;
  return index;
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
  const watchdogRef = useRef<number | null>(null);
  const finishedRef = useRef(false);
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
    let lastTickAt = 0;
    finishedRef.current = false;

    // One reveal step; driven by rAF when frames are available and by a
    // watchdog timer when they are not (background tabs, throttled heads).
    const step = () => {
      if (cancelled || finishedRef.current) return;
      const now = performance.now();
      lastTickAt = now;
      const t = Math.min((now - start) / duration, 1);
      // Ease-out: the head of the answer appears promptly, the tail settles.
      const eased = 1 - Math.pow(1 - t, 2.2);
      const target = t >= 1 ? total : Math.max(1, Math.round(total * eased));
      setRevealed(t >= 1 ? total : snapToWordBoundary(content, target));
      if (t >= 1) {
        finishedRef.current = true;
        setDone(true);
        return;
      }
    };

    const onFrame = () => {
      if (cancelled || finishedRef.current) return;
      step();
      frameRef.current = requestAnimationFrame(onFrame);
    };
    frameRef.current = requestAnimationFrame(onFrame);

    watchdogRef.current = window.setInterval(() => {
      if (cancelled || finishedRef.current) return;
      if (performance.now() - lastTickAt > 250) step();
    }, 200);

    return () => {
      cancelled = true;
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      if (watchdogRef.current !== null) window.clearInterval(watchdogRef.current);
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
    finishedRef.current = true;
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    if (watchdogRef.current !== null) window.clearInterval(watchdogRef.current);
    setRevealed(content.length);
    setDone(true);
  }, [content.length]);

  const revealedText = done ? content : content.slice(0, revealed);
  const blocks = parseMarkdownBlocks(revealedText);
  const showCaret = effectiveActive && !done;

  function renderCaret() {
    return showCaret ? <span className="docmind-caret" aria-hidden="true" /> : null;
  }

  function renderHeading(block: MdBlock & { type: "heading" }, isLast: boolean) {
    const content = (
      <>
        <span
          className="h-3 w-0.5 shrink-0 rounded-full bg-brand/55"
          aria-hidden="true"
        />
        <span className="min-w-0">
          <InlineText text={block.text} />
          {isLast && renderCaret()}
        </span>
      </>
    );
    const className = "flex items-center gap-2.5 font-semibold tracking-tight text-foreground";
    if (block.level <= 1) {
      return <h3 className={cn(className, "text-lg")}>{content}</h3>;
    }
    if (block.level === 2) {
      return <h4 className={cn(className, "text-base")}>{content}</h4>;
    }
    return <h5 className={cn(className, "text-sm text-foreground/90")}>{content}</h5>;
  }

  function renderBlock(block: MdBlock, isLast: boolean) {
    switch (block.type) {
      case "heading":
        return renderHeading(block, isLast);
      case "paragraph":
        return (
          <p className="whitespace-pre-wrap">
            <InlineText text={block.text} />
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
                <span className="min-w-0 flex-1">
                  <InlineText text={item.text} />
                  {isLast && index === block.items.length - 1 && renderCaret()}
                </span>
              </li>
            ))}
          </ul>
        );
      case "blockquote":
        return (
          <blockquote className="border-l-2 border-brand/40 pl-3.5 text-muted-foreground">
            <span className="whitespace-pre-wrap">
              <InlineText text={block.text} />
              {isLast && renderCaret()}
            </span>
          </blockquote>
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
      case "hr":
        return (
          <hr
            className="h-px border-0 bg-gradient-to-r from-brand/40 via-border/60 to-transparent"
            aria-hidden="true"
          />
        );
    }
  }

  return (
    <div
      ref={hostRef}
      onClick={showCaret ? finishNow : undefined}
      className={cn("space-y-3.5 text-sm leading-relaxed text-foreground", showCaret && "cursor-pointer")}
      title={showCaret ? "Click to reveal the full response" : undefined}
    >
      {blocks.map((block, index) => (
        <div key={index}>{renderBlock(block, index === blocks.length - 1)}</div>
      ))}
      {blocks.length === 0 && showCaret && <span className="docmind-caret" aria-hidden="true" />}
    </div>
  );
}
