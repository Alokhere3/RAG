import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DocumentManager } from "../src/features/documents/DocumentManager";
import { apiClient } from "../src/services/api";

describe("DocumentManager Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders Document Management heading and upload dropzone", async () => {
    vi.spyOn(apiClient, "getDocuments").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });

    render(<DocumentManager />);

    expect(screen.getByText("Document Management")).toBeInTheDocument();
    expect(screen.getByTestId("upload-dropzone")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("docs-empty")).toBeInTheDocument();
    });
  });

  it("renders document list when documents are returned", async () => {
    vi.spyOn(apiClient, "getDocuments").mockResolvedValue({
      items: [
        {
          id: "doc-123",
          filename: "architecture.pdf",
          contentType: "application/pdf",
          fileSize: 2048,
          checksum: "hash123",
          uploaderId: "user-1",
          status: "uploaded",
          createdAt: "2026-10-23T00:00:00.000Z",
          updatedAt: "2026-10-23T00:00:00.000Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });

    render(<DocumentManager />);

    await waitFor(() => {
      expect(screen.getByText("architecture.pdf")).toBeInTheDocument();
      expect(screen.getByText("2 KB")).toBeInTheDocument();
      expect(screen.getByTestId("doc-row-doc-123")).toBeInTheDocument();
    });
  });

  it("handles successful document upload", async () => {
    vi.spyOn(apiClient, "getDocuments").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });

    const uploadSpy = vi.spyOn(apiClient, "uploadDocument").mockResolvedValue({
      id: "doc-new",
      filename: "specs.txt",
      contentType: "text/plain",
      fileSize: 100,
      checksum: "hash_new",
      uploaderId: "user-1",
      status: "uploaded",
      createdAt: "2026-10-23T00:00:00.000Z",
      updatedAt: "2026-10-23T00:00:00.000Z",
    });

    render(<DocumentManager />);

    const input = screen.getByTestId("file-input");
    const file = new File(["test content"], "specs.txt", { type: "text/plain" });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(uploadSpy).toHaveBeenCalledWith(file);
      expect(screen.getByTestId("doc-success-banner")).toHaveTextContent(
        'Successfully uploaded "specs.txt"'
      );
    });
  });

  it("displays error banner on upload failure", async () => {
    vi.spyOn(apiClient, "getDocuments").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });

    vi.spyOn(apiClient, "uploadDocument").mockRejectedValue(
      new Error("File content does not match PDF format (MIME spoofing detected).")
    );

    render(<DocumentManager />);

    const input = screen.getByTestId("file-input");
    const fakeFile = new File(["fake"], "fake.pdf", { type: "application/pdf" });

    fireEvent.change(input, { target: { files: [fakeFile] } });

    await waitFor(() => {
      expect(screen.getByTestId("doc-error-banner")).toHaveTextContent(
        "MIME spoofing detected"
      );
    });
  });

  it("handles document deletion", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(apiClient, "getDocuments").mockResolvedValue({
      items: [
        {
          id: "doc-del",
          filename: "delete-me.txt",
          contentType: "text/plain",
          fileSize: 50,
          checksum: "hash_del",
          uploaderId: "user-1",
          status: "uploaded",
          createdAt: "2026-10-23T00:00:00.000Z",
          updatedAt: "2026-10-23T00:00:00.000Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });

    const deleteSpy = vi.spyOn(apiClient, "deleteDocument").mockResolvedValue(undefined);

    render(<DocumentManager />);

    await waitFor(() => {
      expect(screen.getByText("delete-me.txt")).toBeInTheDocument();
    });

    const deleteBtn = screen.getByTestId("delete-doc-doc-del");
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith("doc-del");
      expect(screen.getByTestId("doc-success-banner")).toHaveTextContent('Deleted "delete-me.txt"');
      expect(screen.queryByText("delete-me.txt")).not.toBeInTheDocument();
    });
  });

  it("displays ready status badge for ready documents", async () => {
    vi.spyOn(apiClient, "getDocuments").mockResolvedValue({
      items: [
        {
          id: "doc-ready",
          filename: "knowledge.md",
          contentType: "text/markdown",
          fileSize: 1024,
          checksum: "hash_ready",
          uploaderId: "user-1",
          status: "ready",
          createdAt: "2026-10-23T00:00:00.000Z",
          updatedAt: "2026-10-23T00:00:00.000Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });

    render(<DocumentManager />);

    await waitFor(() => {
      expect(screen.getByTestId("status-doc-ready")).toHaveTextContent("Ready");
    });
  });

  it("triggers ingestion when clicking process button on uploaded document", async () => {
    vi.spyOn(apiClient, "getDocuments").mockResolvedValue({
      items: [
        {
          id: "doc-proc",
          filename: "manual.pdf",
          contentType: "application/pdf",
          fileSize: 4096,
          checksum: "hash_proc",
          uploaderId: "user-1",
          status: "uploaded",
          createdAt: "2026-10-23T00:00:00.000Z",
          updatedAt: "2026-10-23T00:00:00.000Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });

    const triggerSpy = vi.spyOn(apiClient, "triggerIngestion").mockResolvedValue({
      id: "job-1",
      documentId: "doc-proc",
      status: "queued",
      attemptCount: 0,
      maxAttempts: 3,
      createdAt: "2026-10-23T00:00:00.000Z",
      updatedAt: "2026-10-23T00:00:00.000Z",
    });

    render(<DocumentManager />);

    await waitFor(() => {
      expect(screen.getByTestId("retry-doc-doc-proc")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("retry-doc-doc-proc"));

    await waitFor(() => {
      expect(triggerSpy).toHaveBeenCalledWith("doc-proc", true);
    });
  });

  it("displays OCR required explanation when failed document has OCR_REQUIRED error code", async () => {
    vi.spyOn(apiClient, "getDocuments").mockResolvedValue({
      items: [
        {
          id: "doc-failed",
          filename: "scanned.pdf",
          contentType: "application/pdf",
          fileSize: 8192,
          checksum: "hash_scanned",
          uploaderId: "user-1",
          status: "failed",
          metadata: {
            error_code: "OCR_REQUIRED",
          },
          createdAt: "2026-10-23T00:00:00.000Z",
          updatedAt: "2026-10-23T00:00:00.000Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });

    render(<DocumentManager />);

    await waitFor(() => {
      expect(screen.getByTestId("status-doc-failed")).toHaveTextContent("Failed");
      expect(screen.getByText("Scanned file (OCR required)")).toBeInTheDocument();
      expect(screen.getByTestId("retry-doc-doc-failed")).toBeInTheDocument();
    });
  });
});

