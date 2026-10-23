import React, { useState } from "react";
import { StatusPage } from "./pages/StatusPage";
import { DocumentManager } from "./features/documents/DocumentManager";
import { ChatInterface } from "./features/chat/ChatInterface";
import { AdminPanel } from "./features/admin/AdminPanel";
import { useAuth } from "./auth";
import "./index.css";

export const App: React.FC = () => {
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<"status" | "documents" | "chat" | "admin">("status");

  return (
    <>
      <header className="app-header">
        <nav className="nav-tabs" aria-label="Main Navigation">
          <button
            className={`nav-tab ${activeTab === "chat" ? "nav-tab-active" : ""}`}
            onClick={() => setActiveTab("chat")}
            data-testid="tab-chat"
          >
            Chat
          </button>
          <button
            className={`nav-tab ${activeTab === "documents" ? "nav-tab-active" : ""}`}
            onClick={() => setActiveTab("documents")}
            data-testid="tab-documents"
          >
            Documents
          </button>
          {user?.role === "admin" && (
            <button
              className={`nav-tab ${activeTab === "admin" ? "nav-tab-active" : ""}`}
              onClick={() => setActiveTab("admin")}
              data-testid="tab-admin"
            >
              Admin
            </button>
          )}
          <button
            className={`nav-tab ${activeTab === "status" ? "nav-tab-active" : ""}`}
            onClick={() => setActiveTab("status")}
            data-testid="tab-status"
          >
            Status
          </button>
        </nav>
        <div className="auth-toolbar">
          <span data-testid="user-email">{user?.email}</span>
          <button onClick={() => void logout()} data-testid="logout-button">
            Sign out
          </button>
        </div>
      </header>
      <main className="app-main">
        {activeTab === "status" && <StatusPage />}
        {activeTab === "documents" && <DocumentManager />}
        {activeTab === "chat" && <ChatInterface />}
        {activeTab === "admin" && user?.role === "admin" && <AdminPanel />}
      </main>
    </>
  );
};


export default App;

