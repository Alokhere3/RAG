export interface CitationItem {
  document_id: string;
  document_title: string;
  chunk_id: string;
  chunk_index: number;
  relevance_score: number;
  snippet: string;
}

export interface MessageItem {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: CitationItem[] | null;
  latency_ms?: number | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  created_at: string;
}

export interface ConversationItem {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface ConversationListResponse {
  items: ConversationItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface MessageListResponse {
  items: MessageItem[];
  total: number;
  page: number;
  page_size: number;
}
