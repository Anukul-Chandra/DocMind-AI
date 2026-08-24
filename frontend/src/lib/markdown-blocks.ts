export interface HeadingBlock {
  type: "heading";
  level: number;
  text: string;
}

export interface ParagraphBlock {
  type: "paragraph";
  text: string;
}

export interface ListItem {
  /** Original ordered marker (e.g. "3") so numbering stays faithful. */
  marker: string | null;
  text: string;
}

export interface ListBlock {
  type: "list";
  ordered: boolean;
  items: ListItem[];
}

export interface CodeBlock {
  type: "code";
  lang: string | null;
  lines: string[];
  open: boolean;
}

export interface BlockquoteBlock {
  type: "blockquote";
  text: string;
}

export interface ThematicBreakBlock {
  type: "hr";
}

export type MdBlock =
  | HeadingBlock
  | ParagraphBlock
  | ListBlock
  | CodeBlock
  | BlockquoteBlock
  | ThematicBreakBlock;

const FENCE_OPEN = /^\s*```(\w*)\s*$/;
const FENCE_CLOSE = /^\s*```\s*$/;
const HEADING = /^(#{1,4})\s+(.*)$/;
const UL_ITEM = /^[-*+]\s+(.*)$/;
const OL_ITEM = /^(\d+)[.)]\s+(.*)$/;
const THEMATIC_BREAK = /^\s{0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$/;
const BLOCKQUOTE = /^>\s?(.*)$/;

/**
 * Minimal block-level markdown parser used by the progressive chat reveal.
 * Inline syntax is intentionally left as plain text — identical to how
 * responses were rendered previously.
 */
export function parseMarkdownBlocks(input: string): MdBlock[] {
  const blocks: MdBlock[] = [];
  const lines = input.split("\n");

  let paragraph: string[] = [];
  let list: { ordered: boolean; items: ListItem[] } | null = null;

  function flushParagraph() {
    if (paragraph.length > 0) {
      blocks.push({ type: "paragraph", text: paragraph.join("\n") });
      paragraph = [];
    }
  }

  function flushList() {
    if (list && list.items.length > 0) {
      blocks.push({ type: "list", ordered: list.ordered, items: list.items });
    }
    list = null;
  }

  function flushAll() {
    flushParagraph();
    flushList();
  }

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    const fence = FENCE_OPEN.exec(line);
    if (fence) {
      flushAll();
      i += 1;
      const codeLines: string[] = [];
      let open = true;
      while (i < lines.length) {
        if (FENCE_CLOSE.test(lines[i])) {
          open = false;
          i += 1;
          break;
        }
        codeLines.push(lines[i]);
        i += 1;
      }
      blocks.push({
        type: "code",
        lang: fence[1] || null,
        lines: codeLines,
        open,
      });
      continue;
    }

    if (/^\s*$/.test(line)) {
      flushAll();
      i += 1;
      continue;
    }

    if (THEMATIC_BREAK.test(line)) {
      flushAll();
      blocks.push({ type: "hr" });
      i += 1;
      continue;
    }

    const quote = BLOCKQUOTE.exec(line);
    if (quote) {
      flushAll();
      const quoted: string[] = [quote[1]];
      i += 1;
      while (i < lines.length) {
        const next = BLOCKQUOTE.exec(lines[i]);
        if (!next) break;
        quoted.push(next[1]);
        i += 1;
      }
      blocks.push({ type: "blockquote", text: quoted.join("\n") });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      flushAll();
      blocks.push({
        type: "heading",
        level: heading[1].length,
        text: heading[2],
      });
      i += 1;
      continue;
    }

    const ul = UL_ITEM.exec(line);
    if (ul) {
      flushParagraph();
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push({ marker: null, text: ul[1] });
      i += 1;
      continue;
    }

    const ol = OL_ITEM.exec(line);
    if (ol) {
      flushParagraph();
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push({ marker: ol[1], text: ol[2] });
      i += 1;
      continue;
    }

    flushList();
    paragraph.push(line);
    i += 1;
  }

  flushAll();
  return blocks;
}
