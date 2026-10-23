import type { IngestionJobItem } from "./document";

export type AdminUserRole = "admin" | "user";
export type AdminUserStatus = "active" | "inactive" | "suspended";

export interface AdminUserItem {
  id: string;
  email: string;
  display_name?: string | null;
  role: AdminUserRole;
  status: AdminUserStatus;
  created_at: string;
  updated_at: string;
}

export interface AdminUserListResponse {
  items: AdminUserItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminJobListResponse {
  items: IngestionJobItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface AdminDiagnosticsResponse {
  application: Record<string, unknown>;
  security: Record<string, unknown>;
  embedding: Record<string, unknown>;
  llm: Record<string, unknown>;
  storage_and_ingestion: Record<string, unknown>;
  features: Record<string, unknown>;
}

export interface CreateAdminUserPayload {
  email: string;
  password: string;
  display_name?: string;
  role?: AdminUserRole;
}
