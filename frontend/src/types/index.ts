export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: Date;
}

export interface SourceDocument {
  content: string;
  source: string;
  score?: number;
}

export interface ChatResponse {
  content: string;
  session_id: string;
  sources: SourceDocument[];
  metadata: {
    model?: string;
    use_rag?: boolean;
    message_count?: number;
  };
}

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  status: string;
  chunk_count: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  model_loaded: boolean;
  embedding_loaded: boolean;
  vector_db_ready: boolean;
}

export interface DocumentInfo {
  document_id: string;
  source: string;
  chunk_count: number;
  file_type: string | null;
  created_at: string | null;
}

export interface DocumentListResponse {
  documents: DocumentInfo[];
  total_count: number;
  total_chunks: number;
}

export interface DocumentDeleteResponse {
  deleted: boolean;
  document_id: string;
  chunks_removed: number;
}
