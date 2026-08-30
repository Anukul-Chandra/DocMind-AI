export interface ConversationMeta {
  conversation_id: string;
  owner_id?: string;
  title?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  message_count?: number;
}

export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
  conversation_id?: string;
  /** Preview object URLs for image attachments sent with this message. */
  images?: string[];
  provider?: string;
  model?: string;
  sources?: SourceFileLike[];
}

export interface SourceFileLike {
  filename: string;
  chunkIds: number[];
}
