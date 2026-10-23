import React, { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../../services/api";
import type { DocumentItem } from "../../types/document";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export const DocumentManager: React.FC = () => {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [processingDocIds, setProcessingDocIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocuments = useCallback(async (silent: boolean = false) => {
    if (!silent) {
      setIsLoading(true);
      setError(null);
    }
    try {
      const res = await apiClient.getDocuments();
      setDocuments(res.items);
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : "Failed to load documents.");
      }
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadDocuments(false);
  }, [loadDocuments]);

  // Auto-polling when documents are queued or processing
  useEffect(() => {
    const hasActiveJobs = documents.some(
      (doc) => doc.status === "queued" || doc.status === "processing"
    );

    if (!hasActiveJobs) return;

    const timer = setInterval(() => {
      void loadDocuments(true);
    }, 2500);

    return () => clearInterval(timer);
  }, [documents, loadDocuments]);

  const handleFileUpload = async (file: File) => {
    if (!file) return;
    setIsUploading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const created = await apiClient.uploadDocument(file);
      setSuccessMessage(`Successfully uploaded "${created.filename}". Ingestion job queued.`);
      await loadDocuments(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload document.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleFileUpload(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void handleFileUpload(file);
  };

  const handleRetryIngestion = async (docId: string, filename: string) => {
    setError(null);
    setSuccessMessage(null);
    setProcessingDocIds((prev) => new Set(prev).add(docId));
    try {
      await apiClient.triggerIngestion(docId, true);
      setSuccessMessage(`Ingestion triggered for "${filename}"`);
      await loadDocuments(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger ingestion.");
    } finally {
      setProcessingDocIds((prev) => {
        const next = new Set(prev);
        next.delete(docId);
        return next;
      });
    }
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"?`)) return;
    try {
      await apiClient.deleteDocument(docId);
      setSuccessMessage(`Deleted "${filename}"`);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document.");
    }
  };

  const renderStatusBadge = (doc: DocumentItem) => {
    const isRetrying = processingDocIds.has(doc.id);
    const status = isRetrying ? "processing" : doc.status.toLowerCase();

    switch (status) {
      case "ready":
      case "succeeded":
        return (
          <span className="status-badge status-badge-ready" data-testid={`status-${doc.id}`}>
            <span className="status-dot" style={{ backgroundColor: "#10b981" }} />
            Ready
          </span>
        );
      case "processing":
        return (
          <span className="status-badge status-badge-processing" data-testid={`status-${doc.id}`}>
            <span className="spin-icon">⟳</span>
            Extracting…
          </span>
        );
      case "queued":
        return (
          <span className="status-badge status-badge-queued" data-testid={`status-${doc.id}`}>
            <span className="status-dot" style={{ backgroundColor: "#f59e0b" }} />
            Queued
          </span>
        );
      case "failed": {
        const isOcr = doc.metadata?.error_code === "OCR_REQUIRED";
        return (
          <div>
            <span className="status-badge status-badge-failed" data-testid={`status-${doc.id}`}>
              <span className="status-dot" style={{ backgroundColor: "#ef4444" }} />
              Failed
            </span>
            {isOcr ? (
              <span className="error-hint" title="Document contains scanned pages or images without extractable text">
                Scanned file (OCR required)
              </span>
            ) : null}
          </div>
        );
      }
      case "uploaded":
      default:
        return (
          <span className="status-badge status-badge-uploaded" data-testid={`status-${doc.id}`}>
            <span className="status-dot" style={{ backgroundColor: "#64748b" }} />
            Uploaded
          </span>
        );
    }
  };

  return (
    <div className="status-card document-manager-card" data-testid="document-manager">
      <div className="brand-header">
        <h2 className="section-title">Document Management</h2>
        <p className="bot-name">Upload and manage source files for knowledge retrieval</p>
      </div>

      {error && (
        <div className="error-banner" role="alert" data-testid="doc-error-banner">
          {error}
        </div>
      )}

      {successMessage && (
        <div className="success-banner" role="status" data-testid="doc-success-banner">
          {successMessage}
        </div>
      )}

      {/* Upload Dropzone */}
      <div
        className={`dropzone ${isDragOver ? "dropzone-active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        data-testid="upload-dropzone"
      >
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: "none" }}
          accept=".pdf,.txt,.md,.markdown,.docx"
          onChange={handleFileInputChange}
          data-testid="file-input"
        />
        <div className="dropzone-content">
          <span className="dropzone-icon">📁</span>
          <p className="dropzone-text">
            {isUploading ? "Uploading document…" : "Drag and drop your file here, or click to browse"}
          </p>
          <span className="dropzone-hint">
            Supported formats: PDF, TXT, Markdown, DOCX (Max 25 MB)
          </span>
        </div>
      </div>

      {/* Document List */}
      <div className="status-section" style={{ marginTop: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h3 className="section-title" style={{ margin: 0 }}>
            Uploaded Documents ({documents.length})
          </h3>
          <button
            className="refresh-button"
            onClick={() => void loadDocuments(false)}
            disabled={isLoading}
            data-testid="refresh-docs-button"
          >
            {isLoading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {isLoading ? (
          <div className="loading-state" data-testid="docs-loading">
            Loading documents…
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state" data-testid="docs-empty">
            <span className="empty-state-icon">📄</span>
            <p>No documents uploaded yet.</p>
            <span className="dropzone-hint">Add files above to populate your knowledge base.</span>
          </div>
        ) : (
          <div className="doc-table-container">
            <table className="doc-table" data-testid="doc-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => {
                  const isRetrying = processingDocIds.has(doc.id);
                  const canRetry =
                    doc.status.toLowerCase() === "failed" ||
                    doc.status.toLowerCase() === "uploaded";

                  return (
                    <tr key={doc.id} data-testid={`doc-row-${doc.id}`}>
                      <td className="doc-name-cell" title={doc.filename}>
                        <span className="doc-icon">📄</span>
                        <span className="doc-name-text">{doc.filename}</span>
                      </td>
                      <td>
                        <span className="doc-type-badge">
                          {doc.filename.split(".").pop()?.toUpperCase() || "DOC"}
                        </span>
                      </td>
                      <td>{formatBytes(doc.fileSize)}</td>
                      <td>{formatDate(doc.createdAt)}</td>
                      <td>{renderStatusBadge(doc)}</td>
                      <td>
                        <div className="action-buttons">
                          {canRetry && (
                            <button
                              className="retry-button"
                              onClick={() => void handleRetryIngestion(doc.id, doc.filename)}
                              disabled={isRetrying}
                              title="Process or retry ingestion"
                              data-testid={`retry-doc-${doc.id}`}
                            >
                              {isRetrying ? "Queuing…" : "Process"}
                            </button>
                          )}
                          <button
                            className="delete-button"
                            onClick={() => void handleDelete(doc.id, doc.filename)}
                            title="Delete document"
                            data-testid={`delete-doc-${doc.id}`}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
