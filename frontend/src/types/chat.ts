export interface SourceFile {
  filename: string;
  chunkIds: number[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  provider?: string;
  model?: string;
  sources?: SourceFile[];
}