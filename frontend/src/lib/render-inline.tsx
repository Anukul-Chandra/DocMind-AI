import type { ReactNode } from "react";

/**
 * Minimal inline Markdown renderer: `code`, ***bold italic***, **bold**,
 * __bold__, *italic*, _italic_, [label](url).
 *
 * Anything that does not form a valid construct is emitted as literal text,
 * so malformed Markdown degrades gracefully instead of showing broken syntax.
 */

/**
 * Inline Markdown grammar. Instantiated per parse call — a shared /g regex
 * would leak `lastIndex` across recursive calls and hang the renderer.
 */
const INLINE_SOURCE =
  "(`[^\\n]+`)|(\\*\\*\\*[^*\\n]+\\*\\*\\*)|(\\*\\*[^*\\n]+\\*\\*)|(\\*[^*\\n]+\\*)|(__[^_\\n]+__)|(_[^_\\n]+_)|(\\[[^\\]\\n]+\\]\\([^)\\s]+\\))";

const MAX_DEPTH = 6;

function isWordChar(char: string | undefined): boolean {
  return char !== undefined && /[A-Za-z0-9_]/.test(char);
}

function safeHref(url: string): string | null {
  return /^(https?:\/\/|mailto:|\/)/i.test(url) ? url : null;
}

function parseInline(text: string, depth: number, keyBase: string): ReactNode[] {
  if (!text) return [];
  if (depth >= MAX_DEPTH) return [text];

  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  const pattern = new RegExp(INLINE_SOURCE, "g");

  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    // Guard against zero-progress matches (defensive; keeps the loop finite).
    if (match.index === pattern.lastIndex) pattern.lastIndex += 1;
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const token = match[0];
    const before = text[match.index - 1];
    const after = text[match.index + token.length];
    const k = `${keyBase}-${key++}`;

    if (match[1]) {
      // `code`
      nodes.push(
        <code
          key={k}
          className="rounded bg-brand/8 px-1.5 py-0.5 font-mono text-[0.85em] text-brand/90 ring-1 ring-inset ring-brand-border/25"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (match[2]) {
      // ***bold italic***
      nodes.push(
        <strong key={k} className="font-semibold text-foreground">
          <em>{parseInline(token.slice(3, -3), depth + 1, k)}</em>
        </strong>,
      );
    } else if (match[3]) {
      // **bold**
      nodes.push(
        <strong key={k} className="font-semibold text-foreground">
          {parseInline(token.slice(2, -2), depth + 1, k)}
        </strong>,
      );
    } else if (match[4]) {
      // *italic*
      nodes.push(<em key={k}>{parseInline(token.slice(1, -1), depth + 1, k)}</em>);
    } else if (match[5] || match[6]) {
      // __bold__ / _italic_ — require non-word boundaries to protect snake_case.
      const isWordFlanked = isWordChar(before) && isWordChar(after);
      if (isWordFlanked) {
        nodes.push(token);
      } else if (match[5]) {
        nodes.push(
          <strong key={k} className="font-semibold text-foreground">
            {parseInline(token.slice(2, -2), depth + 1, k)}
          </strong>,
        );
      } else {
        nodes.push(<em key={k}>{parseInline(token.slice(1, -1), depth + 1, k)}</em>);
      }
    } else if (match[7]) {
      // [label](url)
      const split = token.indexOf("](");
      const label = token.slice(1, split);
      const url = token.slice(split + 2, -1);
      const href = safeHref(url);
      nodes.push(
        href ? (
          <a
            key={k}
            href={href}
            target="_blank"
            rel="noreferrer noopener"
            className="text-brand underline decoration-brand/40 underline-offset-2 transition-colors hover:decoration-brand"
          >
            {label}
          </a>
        ) : (
          label
        ),
      );
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

export function InlineText({ text }: { text: string }) {
  return <>{parseInline(text, 0, "i")}</>;
}
