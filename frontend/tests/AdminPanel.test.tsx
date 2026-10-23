import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AdminPanel } from "../src/features/admin/AdminPanel";
import { apiClient } from "../src/services/api";
import type { AdminUserItem } from "../src/types/admin";
import type { IngestionJobItem } from "../src/types/document";

const mockAdminUser: AdminUserItem = {
  id: "user-1",
  email: "admin@example.com",
  display_name: "Lead Admin",
  role: "admin",
  status: "active",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const mockStandardUser: AdminUserItem = {
  id: "user-2",
  email: "user@example.com",
  display_name: "Research Analyst",
  role: "user",
  status: "active",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const mockFailedJob: IngestionJobItem = {
  id: "job-failed-123",
  documentId: "doc-abc-456",
  status: "failed",
  attemptCount: 3,
  maxAttempts: 3,
  errorMessage: "Worker crashed parsing malformed document stream",
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
};

describe("AdminPanel (Phase 8 - Chunk 8.4)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("renders users list by default", async () => {
    vi.spyOn(apiClient, "getAdminUsers").mockResolvedValue({
      items: [mockAdminUser, mockStandardUser],
      total: 2,
      page: 1,
      page_size: 50,
    });

    render(<AdminPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("admin-panel")).toBeInTheDocument();
      expect(screen.getByText("Platform Administration")).toBeInTheDocument();
      expect(screen.getByTestId("user-row-user-1")).toBeInTheDocument();
      expect(screen.getByTestId("user-row-user-2")).toBeInTheDocument();
      expect(screen.getByText("admin@example.com")).toBeInTheDocument();
      expect(screen.getByText("user@example.com")).toBeInTheDocument();
    });
  });

  it("handles toggling user role to user", async () => {
    vi.spyOn(apiClient, "getAdminUsers").mockResolvedValue({
      items: [mockStandardUser],
      total: 1,
      page: 1,
      page_size: 50,
    });
    vi.spyOn(apiClient, "updateAdminUserRole").mockResolvedValue({
      ...mockStandardUser,
      role: "admin",
    });

    render(<AdminPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("toggle-role-user-2")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("toggle-role-user-2"));

    await waitFor(() => {
      expect(apiClient.updateAdminUserRole).toHaveBeenCalledWith("user-2", "admin");
    });
  });

  it("handles toggling user status to suspended", async () => {
    vi.spyOn(apiClient, "getAdminUsers").mockResolvedValue({
      items: [mockStandardUser],
      total: 1,
      page: 1,
      page_size: 50,
    });
    vi.spyOn(apiClient, "updateAdminUserStatus").mockResolvedValue({
      ...mockStandardUser,
      status: "suspended",
    });

    render(<AdminPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("toggle-status-user-2")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("toggle-status-user-2"));

    await waitFor(() => {
      expect(apiClient.updateAdminUserStatus).toHaveBeenCalledWith("user-2", "suspended");
    });
  });

  it("displays error alert when last-admin protection rejects operation", async () => {
    vi.spyOn(apiClient, "getAdminUsers").mockResolvedValue({
      items: [mockAdminUser],
      total: 1,
      page: 1,
      page_size: 50,
    });
    vi.spyOn(apiClient, "updateAdminUserRole").mockRejectedValue(
      new Error("Cannot demote the last remaining active administrator.")
    );

    render(<AdminPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("toggle-role-user-1")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("toggle-role-user-1"));

    await waitFor(() => {
      expect(screen.getByTestId("user-error-alert")).toBeInTheDocument();
      expect(screen.getByText("Cannot demote the last remaining active administrator.")).toBeInTheDocument();
    });
  });

  it("opens create user modal and registers a new user", async () => {
    vi.spyOn(apiClient, "getAdminUsers").mockResolvedValue({
      items: [mockAdminUser],
      total: 1,
      page: 1,
      page_size: 50,
    });
    vi.spyOn(apiClient, "createAdminUser").mockResolvedValue({
      id: "user-new",
      email: "analyst@example.com",
      display_name: "New Analyst",
      role: "user",
      status: "active",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    render(<AdminPanel />);

    await waitFor(() => {
      expect(screen.getByTestId("add-user-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("add-user-btn"));

    expect(screen.getByTestId("create-user-modal")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("new-user-email"), {
      target: { value: "analyst@example.com" },
    });
    fireEvent.change(screen.getByTestId("new-user-password"), {
      target: { value: "SecretPassword123!" },
    });
    fireEvent.change(screen.getByTestId("new-user-display-name"), {
      target: { value: "New Analyst" },
    });

    fireEvent.click(screen.getByTestId("submit-create-user"));

    await waitFor(() => {
      expect(apiClient.createAdminUser).toHaveBeenCalledWith({
        email: "analyst@example.com",
        password: "SecretPassword123!",
        display_name: "New Analyst",
        role: "user",
      });
      expect(screen.queryByTestId("create-user-modal")).not.toBeInTheDocument();
    });
  });

  it("switches to Ingestion Jobs subtab and handles job retry", async () => {
    vi.spyOn(apiClient, "getAdminUsers").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    vi.spyOn(apiClient, "getAdminJobs").mockResolvedValue({
      items: [mockFailedJob],
      total: 1,
      page: 1,
      pageSize: 50,
    });
    vi.spyOn(apiClient, "retryAdminJob").mockResolvedValue({
      ...mockFailedJob,
      status: "queued",
      attemptCount: 0,
      errorMessage: null,
    });

    render(<AdminPanel />);

    const jobsTab = screen.getByTestId("admin-subtab-jobs");
    fireEvent.click(jobsTab);

    await waitFor(() => {
      expect(screen.getByTestId("jobs-table")).toBeInTheDocument();
      expect(screen.getByTestId("job-row-job-failed-123")).toBeInTheDocument();
      expect(screen.getByText("FAILED")).toBeInTheDocument();
      expect(screen.getByTestId("retry-job-job-failed-123")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("retry-job-job-failed-123"));

    await waitFor(() => {
      expect(apiClient.retryAdminJob).toHaveBeenCalledWith("job-failed-123");
    });
  });

  it("switches to Diagnostics subtab and renders safe system configuration", async () => {
    vi.spyOn(apiClient, "getAdminUsers").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    vi.spyOn(apiClient, "getAdminDiagnostics").mockResolvedValue({
      application: { name: "RAG Platform", environment: "development", debug: true },
      security: { token_algorithm: "HS256", token_expire_minutes: 60, password_min_length: 8 },
      embedding: { provider: "mock", model: "sentence-transformers/all-MiniLM-L6-v2", dimensions: 384 },
      llm: { provider: "mock", model: "mock-deterministic-llm" },
      storage_and_ingestion: { backend: "filesystem", max_upload_size_bytes: 52428800 },
      features: { enable_documents: true, enable_ingestion: true },
    });

    render(<AdminPanel />);

    const diagTab = screen.getByTestId("admin-subtab-diagnostics");
    fireEvent.click(diagTab);

    await waitFor(() => {
      expect(screen.getByTestId("diagnostics-grid")).toBeInTheDocument();
      expect(screen.getByTestId("diag-section-application")).toBeInTheDocument();
      expect(screen.getByTestId("diag-section-security")).toBeInTheDocument();
      expect(screen.getByTestId("diag-section-embedding")).toBeInTheDocument();
      expect(screen.getByText("sentence-transformers/all-MiniLM-L6-v2")).toBeInTheDocument();
    });
  });
});
