import React, { useState, useEffect, useCallback } from "react";
import { apiClient } from "../../services/api";
import type {
  AdminUserItem,
  AdminUserRole,
  AdminUserStatus,
  AdminDiagnosticsResponse,
  CreateAdminUserPayload,
} from "../../types/admin";
import type { IngestionJobItem } from "../../types/document";

export const AdminPanel: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"users" | "jobs" | "diagnostics">("users");

  // User state
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersLoading, setUsersLoading] = useState(false);
  const [userSearch, setUserSearch] = useState("");
  const [userRoleFilter, setUserRoleFilter] = useState<string>("");
  const [userStatusFilter, setUserStatusFilter] = useState<string>("");
  const [userError, setUserError] = useState<string | null>(null);
  const [userSuccess, setUserSuccess] = useState<string | null>(null);

  // User create modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserDisplayName, setNewUserDisplayName] = useState("");
  const [newUserRole, setNewUserRole] = useState<AdminUserRole>("user");
  const [createSubmitting, setCreateSubmitting] = useState(false);

  // Ingestion jobs state
  const [jobs, setJobs] = useState<IngestionJobItem[]>([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobStatusFilter, setJobStatusFilter] = useState<string>("");
  const [jobError, setJobError] = useState<string | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);

  // Diagnostics state
  const [diagnostics, setDiagnostics] = useState<AdminDiagnosticsResponse | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagError, setDiagError] = useState<string | null>(null);

  // Fetch users
  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    setUserError(null);
    try {
      const res = await apiClient.getAdminUsers({
        page: 1,
        pageSize: 50,
        search: userSearch || undefined,
        role: userRoleFilter || undefined,
        status: userStatusFilter || undefined,
      });
      setUsers(res.items);
      setUsersTotal(res.total);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Failed to load users");
    } finally {
      setUsersLoading(false);
    }
  }, [userSearch, userRoleFilter, userStatusFilter]);

  // Fetch jobs
  const loadJobs = useCallback(async () => {
    setJobsLoading(true);
    setJobError(null);
    try {
      const res = await apiClient.getAdminJobs({
        page: 1,
        pageSize: 50,
        status: jobStatusFilter || undefined,
      });
      setJobs(res.items);
      setJobsTotal(res.total);
    } catch (err) {
      setJobError(err instanceof Error ? err.message : "Failed to load ingestion jobs");
    } finally {
      setJobsLoading(false);
    }
  }, [jobStatusFilter]);

  // Fetch diagnostics
  const loadDiagnostics = useCallback(async () => {
    setDiagLoading(true);
    setDiagError(null);
    try {
      const res = await apiClient.getAdminDiagnostics();
      setDiagnostics(res);
    } catch (err) {
      setDiagError(err instanceof Error ? err.message : "Failed to load diagnostics");
    } finally {
      setDiagLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === "users") {
      void loadUsers();
    } else if (activeTab === "jobs") {
      void loadJobs();
    } else if (activeTab === "diagnostics") {
      void loadDiagnostics();
    }
  }, [activeTab, loadUsers, loadJobs, loadDiagnostics]);

  // User Actions
  const handleToggleRole = async (user: AdminUserItem) => {
    const nextRole: AdminUserRole = user.role === "admin" ? "user" : "admin";
    if (!window.confirm(`Are you sure you want to change ${user.email}'s role to ${nextRole}?`)) {
      return;
    }
    setUserError(null);
    setUserSuccess(null);
    try {
      await apiClient.updateAdminUserRole(user.id, nextRole);
      setUserSuccess(`Successfully updated ${user.email} to ${nextRole}.`);
      void loadUsers();
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Failed to update role");
    }
  };

  const handleToggleStatus = async (user: AdminUserItem) => {
    const nextStatus: AdminUserStatus = user.status === "active" ? "suspended" : "active";
    if (!window.confirm(`Are you sure you want to change ${user.email}'s status to ${nextStatus}?`)) {
      return;
    }
    setUserError(null);
    setUserSuccess(null);
    try {
      await apiClient.updateAdminUserStatus(user.id, nextStatus);
      setUserSuccess(`Successfully updated ${user.email} to ${nextStatus}.`);
      void loadUsers();
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Failed to update status");
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateSubmitting(true);
    setUserError(null);
    try {
      const payload: CreateAdminUserPayload = {
        email: newUserEmail,
        password: newUserPassword,
        display_name: newUserDisplayName || undefined,
        role: newUserRole,
      };
      await apiClient.createAdminUser(payload);
      setShowCreateModal(false);
      setNewUserEmail("");
      setNewUserPassword("");
      setNewUserDisplayName("");
      setNewUserRole("user");
      setUserSuccess(`Created user ${payload.email} successfully.`);
      void loadUsers();
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Job retry action
  const handleRetryJob = async (jobId: string) => {
    setRetryingJobId(jobId);
    setJobError(null);
    try {
      await apiClient.retryAdminJob(jobId);
      void loadJobs();
    } catch (err) {
      setJobError(err instanceof Error ? err.message : "Failed to retry ingestion job");
    } finally {
      setRetryingJobId(null);
    }
  };

  return (
    <div className="admin-container" data-testid="admin-panel">
      <div className="admin-header">
        <div>
          <h1 className="admin-title">Platform Administration</h1>
          <p className="admin-subtitle">
            Manage system users, oversee background ingestion jobs, and verify runtime platform health.
          </p>
        </div>
        <div className="admin-tab-group" role="tablist">
          <button
            role="tab"
            aria-selected={activeTab === "users"}
            className={`admin-subtab-btn ${activeTab === "users" ? "active" : ""}`}
            onClick={() => setActiveTab("users")}
            data-testid="admin-subtab-users"
          >
            Users ({usersTotal})
          </button>
          <button
            role="tab"
            aria-selected={activeTab === "jobs"}
            className={`admin-subtab-btn ${activeTab === "jobs" ? "active" : ""}`}
            onClick={() => setActiveTab("jobs")}
            data-testid="admin-subtab-jobs"
          >
            Ingestion Jobs ({jobsTotal})
          </button>
          <button
            role="tab"
            aria-selected={activeTab === "diagnostics"}
            className={`admin-subtab-btn ${activeTab === "diagnostics" ? "active" : ""}`}
            onClick={() => setActiveTab("diagnostics")}
            data-testid="admin-subtab-diagnostics"
          >
            Diagnostics
          </button>
        </div>
      </div>

      {/* ================= USERS TAB ================= */}
      {activeTab === "users" && (
        <section className="admin-section" aria-label="User Management">
          <div className="admin-controls-bar">
            <div className="admin-filter-group">
              <input
                type="text"
                placeholder="Search email or display name..."
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                className="admin-search-input"
                data-testid="user-search-input"
              />
              <select
                value={userRoleFilter}
                onChange={(e) => setUserRoleFilter(e.target.value)}
                className="admin-filter-select"
                data-testid="user-role-filter"
              >
                <option value="">All Roles</option>
                <option value="admin">Admin</option>
                <option value="user">User</option>
              </select>
              <select
                value={userStatusFilter}
                onChange={(e) => setUserStatusFilter(e.target.value)}
                className="admin-filter-select"
                data-testid="user-status-filter"
              >
                <option value="">All Statuses</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
            <button
              onClick={() => setShowCreateModal(true)}
              className="admin-btn admin-btn-primary"
              data-testid="add-user-btn"
            >
              + Add User
            </button>
          </div>

          {userError && (
            <div className="admin-alert admin-alert-error" data-testid="user-error-alert" role="alert">
              {userError}
            </div>
          )}
          {userSuccess && (
            <div className="admin-alert admin-alert-success" data-testid="user-success-alert">
              {userSuccess}
            </div>
          )}

          {usersLoading ? (
            <div className="admin-loading" data-testid="users-loading">Loading users...</div>
          ) : (
            <div className="admin-table-wrapper">
              <table className="admin-table" data-testid="users-table">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Display Name</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-center text-muted">
                        No users found matching query.
                      </td>
                    </tr>
                  ) : (
                    users.map((u) => (
                      <tr key={u.id} data-testid={`user-row-${u.id}`}>
                        <td className="font-semibold">{u.email}</td>
                        <td>{u.display_name || "-"}</td>
                        <td>
                          <span className={`admin-badge badge-${u.role}`} data-testid={`user-role-${u.id}`}>
                            {u.role.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`admin-badge badge-${u.status === "active" ? "success" : "danger"}`}
                            data-testid={`user-status-${u.id}`}
                          >
                            {u.status.toUpperCase()}
                          </span>
                        </td>
                        <td className="text-muted text-sm">
                          {new Date(u.created_at).toLocaleDateString()}
                        </td>
                        <td className="text-right">
                          <button
                            onClick={() => handleToggleRole(u)}
                            className="admin-action-btn"
                            title="Toggle Role"
                            data-testid={`toggle-role-${u.id}`}
                          >
                            Set {u.role === "admin" ? "User" : "Admin"}
                          </button>
                          <button
                            onClick={() => handleToggleStatus(u)}
                            className="admin-action-btn ml-2"
                            title="Toggle Status"
                            data-testid={`toggle-status-${u.id}`}
                          >
                            {u.status === "active" ? "Suspend" : "Activate"}
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* ================= INGESTION JOBS TAB ================= */}
      {activeTab === "jobs" && (
        <section className="admin-section" aria-label="Ingestion Jobs Oversight">
          <div className="admin-controls-bar">
            <div className="admin-filter-group">
              <select
                value={jobStatusFilter}
                onChange={(e) => setJobStatusFilter(e.target.value)}
                className="admin-filter-select"
                data-testid="job-status-filter"
              >
                <option value="">All Job Statuses</option>
                <option value="queued">Queued</option>
                <option value="processing">Processing</option>
                <option value="succeeded">Succeeded</option>
                <option value="failed">Failed</option>
                <option value="cancelled">Cancelled</option>
              </select>
              <button
                onClick={() => void loadJobs()}
                className="admin-btn admin-btn-secondary"
                data-testid="refresh-jobs-btn"
              >
                Refresh
              </button>
            </div>
          </div>

          {jobError && (
            <div className="admin-alert admin-alert-error" data-testid="job-error-alert" role="alert">
              {jobError}
            </div>
          )}

          {jobsLoading ? (
            <div className="admin-loading" data-testid="jobs-loading">Loading ingestion jobs...</div>
          ) : (
            <div className="admin-table-wrapper">
              <table className="admin-table" data-testid="jobs-table">
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Document ID</th>
                    <th>Status</th>
                    <th>Attempts</th>
                    <th>Error Detail</th>
                    <th>Created</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="text-center text-muted">
                        No ingestion jobs found.
                      </td>
                    </tr>
                  ) : (
                    jobs.map((job) => (
                      <tr key={job.id} data-testid={`job-row-${job.id}`}>
                        <td className="font-mono text-xs">{job.id.slice(0, 8)}...</td>
                        <td className="font-mono text-xs">{job.documentId.slice(0, 8)}...</td>
                        <td>
                          <span
                            className={`admin-badge badge-${
                              job.status === "succeeded"
                                ? "success"
                                : job.status === "failed"
                                ? "danger"
                                : job.status === "processing"
                                ? "warning"
                                : "neutral"
                            }`}
                            data-testid={`job-status-${job.id}`}
                          >
                            {job.status.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          {job.attemptCount} / {job.maxAttempts}
                        </td>
                        <td className="text-sm text-danger truncate max-w-xs" title={job.errorMessage || ""}>
                          {job.errorMessage || "-"}
                        </td>
                        <td className="text-muted text-sm">
                          {new Date(job.createdAt).toLocaleTimeString()}
                        </td>
                        <td className="text-right">
                          {(job.status === "failed" || job.status === "cancelled") && (
                            <button
                              onClick={() => handleRetryJob(job.id)}
                              disabled={retryingJobId === job.id}
                              className="admin-action-btn"
                              data-testid={`retry-job-${job.id}`}
                            >
                              {retryingJobId === job.id ? "Retrying..." : "Retry Job"}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* ================= DIAGNOSTICS TAB ================= */}
      {activeTab === "diagnostics" && (
        <section className="admin-section" aria-label="Runtime Diagnostics">
          <div className="diagnostics-actions">
            <button
              onClick={() => void loadDiagnostics()}
              className="admin-btn admin-btn-secondary"
              data-testid="refresh-diag-btn"
            >
              Refresh Diagnostics
            </button>
          </div>

          {diagError && (
            <div className="admin-alert admin-alert-error" data-testid="diag-error-alert" role="alert">
              {diagError}
            </div>
          )}

          {diagLoading || !diagnostics ? (
            <div className="admin-loading" data-testid="diag-loading">Loading platform diagnostics...</div>
          ) : (
            <div className="diagnostics-grid" data-testid="diagnostics-grid">
              {Object.entries(diagnostics).map(([sectionKey, sectionData]) => (
                <div key={sectionKey} className="diagnostics-card" data-testid={`diag-section-${sectionKey}`}>
                  <h3 className="diagnostics-card-title">
                    {sectionKey.replace(/_/g, " ").toUpperCase()}
                  </h3>
                  <div className="diagnostics-card-body">
                    {Object.entries(sectionData as Record<string, unknown>).map(([propKey, propVal]) => (
                      <div key={propKey} className="diagnostics-prop-row">
                        <span className="diagnostics-prop-key">{propKey}</span>
                        <span className="diagnostics-prop-value font-mono">
                          {typeof propVal === "boolean"
                            ? propVal
                              ? "TRUE"
                              : "FALSE"
                            : typeof propVal === "object" && propVal !== null
                            ? JSON.stringify(propVal)
                            : String(propVal)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ================= CREATE USER MODAL ================= */}
      {showCreateModal && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" data-testid="create-user-modal">
          <div className="modal-card">
            <div className="modal-header">
              <h2 className="modal-title">Register New User</h2>
              <button
                className="modal-close-btn"
                onClick={() => setShowCreateModal(false)}
                aria-label="Close modal"
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateUser} className="modal-body">
              <div className="form-group">
                <label htmlFor="user-email-input">Email Address</label>
                <input
                  id="user-email-input"
                  type="email"
                  required
                  placeholder="analyst@client.corp"
                  value={newUserEmail}
                  onChange={(e) => setNewUserEmail(e.target.value)}
                  className="form-input"
                  data-testid="new-user-email"
                />
              </div>

              <div className="form-group">
                <label htmlFor="user-password-input">Password</label>
                <input
                  id="user-password-input"
                  type="password"
                  required
                  minLength={8}
                  placeholder="Minimum 8 characters"
                  value={newUserPassword}
                  onChange={(e) => setNewUserPassword(e.target.value)}
                  className="form-input"
                  data-testid="new-user-password"
                />
              </div>

              <div className="form-group">
                <label htmlFor="user-name-input">Display Name (Optional)</label>
                <input
                  id="user-name-input"
                  type="text"
                  placeholder="Dr. Jane Doe"
                  value={newUserDisplayName}
                  onChange={(e) => setNewUserDisplayName(e.target.value)}
                  className="form-input"
                  data-testid="new-user-display-name"
                />
              </div>

              <div className="form-group">
                <label htmlFor="user-role-select">Role Assignment</label>
                <select
                  id="user-role-select"
                  value={newUserRole}
                  onChange={(e) => setNewUserRole(e.target.value as AdminUserRole)}
                  className="form-input"
                  data-testid="new-user-role"
                >
                  <option value="user">User (Standard Document & Chat)</option>
                  <option value="admin">Admin (Full Control)</option>
                </select>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="admin-btn admin-btn-secondary"
                  disabled={createSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createSubmitting}
                  className="admin-btn admin-btn-primary"
                  data-testid="submit-create-user"
                >
                  {createSubmitting ? "Creating..." : "Create User"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
