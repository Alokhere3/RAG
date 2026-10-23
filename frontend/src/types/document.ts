export type IngestionJobStatus =
  | "queued"
  | "processing"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface IngestionJobItem {
  id: string;
  documentId: string;
  status: IngestionJobStatus;
  attemptCount: number;
  maxAttempts: number;
  errorMessage?: string | null;
  errorCode?: string | null;
  artifactKey?: string | null;
  createdAt: string;
  updatedAt: string;
  startedAt?: string | null;
  finishedAt?: string | null;
}

export interface IngestionStatusResponse {
  documentId: string;
  documentStatus: string;
  activeJob: IngestionJobItem | null;
  latestJob: IngestionJobItem | null;
}

export interface DocumentItem {
  id: string;
  filename: string;
  contentType: string;
  fileSize: number;
  checksum: string;
  uploaderId: string;
  status: "uploaded" | "processing" | "ready" | "failed" | "deleted" | string;
  createdAt: string;
  updatedAt: string;
  metadata?: Record<string, unknown>;
  latestJob?: IngestionJobItem | null;
}

export interface DocumentListResponse {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
}

