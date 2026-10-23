import { appConfig } from "../config/defaults";
import type { PublicConfigResponse } from "../types/config";
import type {
  HealthResponse,
  ReadinessResponse,
  SystemStatusState,
} from "../types/health";
import type { AuthUser, LoginResponse } from "../auth/types";
import type { DocumentItem, DocumentListResponse, IngestionJobItem, IngestionStatusResponse } from "../types/document";
import type {
  ConversationItem,
  ConversationListResponse,
  MessageItem,
  MessageListResponse,
} from "../types/chat";
import type {
  AdminUserItem,
  AdminUserListResponse,
  AdminUserRole,
  AdminUserStatus,
  AdminJobListResponse,
  AdminDiagnosticsResponse,
  CreateAdminUserPayload,
} from "../types/admin";


export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = appConfig.apiBaseUrl) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  private resolveUrl(path: string): string {
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    return this.baseUrl ? `${this.baseUrl}${cleanPath}` : cleanPath;
  }

  private accessToken: string | null = null;
  private refreshPromise: Promise<LoginResponse | null> | null = null;

  setAccessToken(token: string | null): void { this.accessToken = token; }
  getAccessToken(): string | null { return this.accessToken; }

  private async authRequest(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (this.accessToken) headers.set("Authorization", `Bearer ${this.accessToken}`);
    return fetch(this.resolveUrl(path), { ...init, headers, credentials: "include" });
  }

  async request(path: string, init: RequestInit = {}): Promise<Response> {
    const response = await this.authRequest(path, init);
    if (response.status !== 401 || path.includes("/auth/")) return response;
    const refreshed = await this.refresh();
    if (!refreshed) return response;
    return this.authRequest(path, init);
  }

  async login(email: string, password: string): Promise<LoginResponse> {
    const response = await this.authRequest("/api/v1/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) throw new Error((await response.json().catch(() => null))?.error?.message || "Unable to sign in.");
    const result = (await response.json()) as LoginResponse;
    this.setAccessToken(result.accessToken);
    return result;
  }

  async getCurrentUser(): Promise<AuthUser | null> {
    const response = await this.authRequest("/api/v1/auth/me");
    if (response.status === 401) return null;
    if (!response.ok) throw new Error("Unable to restore session.");
    return (await response.json()) as AuthUser;
  }

  async refresh(): Promise<LoginResponse | null> {
    if (!this.refreshPromise) {
      this.refreshPromise = this.authRequest("/api/v1/auth/refresh", { method: "POST" })
        .then(async response => response.ok ? (await response.json()) as LoginResponse : null)
        .then(result => { this.setAccessToken(result?.accessToken ?? null); return result; })
        .finally(() => { this.refreshPromise = null; });
    }
    return this.refreshPromise;
  }

  async logout(): Promise<void> {
    await this.authRequest("/api/v1/auth/logout", { method: "POST" });
    this.setAccessToken(null);
  }

  async uploadDocument(file: File): Promise<DocumentItem> {
    const formData = new FormData();
    formData.append("file", file);
    const response = await this.request("/api/v1/documents", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to upload document.");
    }
    return (await response.json()) as DocumentItem;
  }

  async getDocuments(limit: number = 50, offset: number = 0): Promise<DocumentListResponse> {
    const response = await this.request(`/api/v1/documents?limit=${limit}&offset=${offset}`, {
      method: "GET",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to load documents.");
    }
    return (await response.json()) as DocumentListResponse;
  }

  async deleteDocument(documentId: string): Promise<void> {
    const response = await this.request(`/api/v1/documents/${documentId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to delete document.");
    }
  }

  async triggerIngestion(
    documentId: string,
    forceReprocess: boolean = false
  ): Promise<IngestionJobItem> {
    const response = await this.request(
      `/api/v1/documents/${documentId}/ingest?force_reprocess=${forceReprocess}`,
      { method: "POST" }
    );
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to trigger document ingestion.");
    }
    return (await response.json()) as IngestionJobItem;
  }

  async getIngestionStatus(documentId: string): Promise<IngestionStatusResponse> {
    const response = await this.request(`/api/v1/documents/${documentId}/ingest/status`, {
      method: "GET",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to get ingestion status.");
    }
    return (await response.json()) as IngestionStatusResponse;
  }

  async cancelIngestion(documentId: string, jobId: string): Promise<IngestionJobItem> {
    const response = await this.request(
      `/api/v1/documents/${documentId}/ingest/jobs/${jobId}/cancel`,
      { method: "POST" }
    );
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to cancel ingestion job.");
    }
    return (await response.json()) as IngestionJobItem;
  }

  async getConversations(page: number = 1, pageSize: number = 50): Promise<ConversationListResponse> {
    const response = await this.request(`/api/v1/conversations?page=${page}&page_size=${pageSize}`, {
      method: "GET",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to load conversations.");
    }
    return (await response.json()) as ConversationListResponse;
  }

  async createConversation(title?: string): Promise<ConversationItem> {
    const response = await this.request("/api/v1/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(title ? { title } : {}),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to create conversation.");
    }
    return (await response.json()) as ConversationItem;
  }

  async getConversation(conversationId: string): Promise<ConversationItem> {
    const response = await this.request(`/api/v1/conversations/${conversationId}`, {
      method: "GET",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to get conversation.");
    }
    return (await response.json()) as ConversationItem;
  }

  async deleteConversation(conversationId: string): Promise<void> {
    const response = await this.request(`/api/v1/conversations/${conversationId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to delete conversation.");
    }
  }

  async getMessages(
    conversationId: string,
    page: number = 1,
    pageSize: number = 50
  ): Promise<MessageListResponse> {
    const response = await this.request(
      `/api/v1/conversations/${conversationId}/messages?page=${page}&page_size=${pageSize}`,
      { method: "GET" }
    );
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to load messages.");
    }
    return (await response.json()) as MessageListResponse;
  }

  async sendMessage(conversationId: string, content: string): Promise<MessageItem> {
    const response = await this.request(`/api/v1/conversations/${conversationId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to send message.");
    }
    return (await response.json()) as MessageItem;
  }

  async getConfig(): Promise<PublicConfigResponse> {
    const response = await fetch(this.resolveUrl("/api/v1/config"), {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Failed to load configuration (HTTP ${response.status})`);
    }
    const data = (await response.json()) as PublicConfigResponse;
    if (
      !data ||
      typeof data !== "object" ||
      !data.application ||
      !data.organization ||
      !data.assistant ||
      !data.branding ||
      !data.features
    ) {
      throw new Error("Invalid configuration structure received from server");
    }
    return data;
  }

  async checkHealth(): Promise<HealthResponse> {
    const response = await fetch(this.resolveUrl("/health"), {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Health probe returned status ${response.status}`);
    }
    return (await response.json()) as HealthResponse;
  }

  async checkReadiness(): Promise<ReadinessResponse> {
    const response = await fetch(this.resolveUrl("/health/ready"), {
      method: "GET",
      headers: { Accept: "application/json" },
    });

    // Both 200 (ready) and 503 (not_ready) carry structured dependency status
    if (response.status === 200 || response.status === 503) {
      const data = (await response.json()) as ReadinessResponse;
      return data;
    }

    throw new Error(`Readiness probe failed with unexpected HTTP status ${response.status}`);
  }

  async getSystemStatus(): Promise<SystemStatusState> {
    try {
      const readiness = await this.checkReadiness();

      return {
        backend: "healthy",
        database: readiness.dependencies.database === "ok" ? "healthy" : "unavailable",
        redis: readiness.dependencies.redis === "ok" ? "healthy" : "unavailable",
        isLoading: false,
        lastChecked: new Date().toLocaleTimeString(),
      };
    } catch (err) {
      // Backend itself is unreachable or failing critically
      return {
        backend: "unavailable",
        database: "unavailable",
        redis: "unavailable",
        isLoading: false,
        error: err instanceof Error ? err.message : "Backend unreachable",
        lastChecked: new Date().toLocaleTimeString(),
      };
    }
  }

  async getAdminUsers(params?: {
    page?: number;
    pageSize?: number;
    search?: string;
    role?: string;
    status?: string;
  }): Promise<AdminUserListResponse> {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", params.page.toString());
    if (params?.pageSize) query.set("page_size", params.pageSize.toString());
    if (params?.search) query.set("search", params.search);
    if (params?.role) query.set("role", params.role);
    if (params?.status) query.set("status", params.status);

    const queryString = query.toString() ? `?${query.toString()}` : "";
    const response = await this.request(`/api/v1/admin/users${queryString}`, {
      method: "GET",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to load users.");
    }
    return (await response.json()) as AdminUserListResponse;
  }

  async createAdminUser(payload: CreateAdminUserPayload): Promise<AdminUserItem> {
    const response = await this.request("/api/v1/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to create user.");
    }
    return (await response.json()) as AdminUserItem;
  }

  async updateAdminUserRole(userId: string, role: AdminUserRole): Promise<AdminUserItem> {
    const response = await this.request(`/api/v1/admin/users/${userId}/role`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to update user role.");
    }
    return (await response.json()) as AdminUserItem;
  }

  async updateAdminUserStatus(userId: string, status: AdminUserStatus): Promise<AdminUserItem> {
    const response = await this.request(`/api/v1/admin/users/${userId}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to update user status.");
    }
    return (await response.json()) as AdminUserItem;
  }

  async getAdminJobs(params?: {
    page?: number;
    pageSize?: number;
    status?: string;
  }): Promise<AdminJobListResponse> {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", params.page.toString());
    if (params?.pageSize) query.set("page_size", params.pageSize.toString());
    if (params?.status) query.set("status", params.status);

    const queryString = query.toString() ? `?${query.toString()}` : "";
    const response = await this.request(`/api/v1/admin/ingestion/jobs${queryString}`, {
      method: "GET",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to load ingestion jobs.");
    }
    return (await response.json()) as AdminJobListResponse;
  }

  async retryAdminJob(jobId: string): Promise<IngestionJobItem> {
    const response = await this.request(`/api/v1/admin/ingestion/jobs/${jobId}/retry`, {
      method: "POST",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to retry ingestion job.");
    }
    return (await response.json()) as IngestionJobItem;
  }

  async getAdminDiagnostics(): Promise<AdminDiagnosticsResponse> {
    const response = await this.request("/api/v1/admin/diagnostics/config", {
      method: "GET",
    });
    if (!response.ok) {
      const err = await response.json().catch(() => null);
      throw new Error(err?.error?.message || "Failed to load diagnostics.");
    }
    return (await response.json()) as AdminDiagnosticsResponse;
  }
}


export const apiClient = new ApiClient();
