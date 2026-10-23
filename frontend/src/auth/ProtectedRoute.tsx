import React from "react";
import { LoginPage } from "./LoginPage";
import { useAuth } from "./AuthProvider";

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isLoading } = useAuth();
  if (isLoading) return <main className="app-main"><div className="loading-state">Restoring session…</div></main>;
  return user ? <>{children}</> : <LoginPage />;
};
