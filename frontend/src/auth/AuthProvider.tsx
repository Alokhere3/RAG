import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiClient } from "../services/api";
import type { AuthUser, UserRole } from "./types";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (role: UserRole) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let current = await apiClient.getCurrentUser();
        if (!current) current = (await apiClient.refresh())?.user ?? null;
        if (!cancelled) setUser(current);
      } catch { if (!cancelled) setUser(null); }
      finally { if (!cancelled) setIsLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    try { setUser((await apiClient.login(email, password)).user); }
    catch (err) { const message = err instanceof Error ? err.message : "Unable to sign in."; setError(message); throw err; }
  }, []);
  const logout = useCallback(async () => { await apiClient.logout(); setUser(null); }, []);
  const hasRole = useCallback((role: UserRole) => user?.role === "admin" || user?.role === role, [user]);

  const value = useMemo(() => ({ user, isLoading, error, login, logout, hasRole }), [user, isLoading, error, login, logout, hasRole]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context) return context;
  // Keeps presentational components independently testable; application startup wraps them.
  return { user: null, isLoading: false, error: null, login: async () => undefined, logout: async () => undefined, hasRole: () => false };
}
