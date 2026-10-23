import { useEffect, useState, useCallback } from "react";
import { apiClient } from "../services/api";
import type { SystemStatusState } from "../types/health";

export function useHealth(pollIntervalMs?: number) {
  const [status, setStatus] = useState<SystemStatusState>({
    backend: "loading",
    database: "loading",
    redis: "loading",
    isLoading: true,
  });

  const checkStatus = useCallback(async () => {
    const latest = await apiClient.getSystemStatus();
    setStatus(latest);
  }, []);

  useEffect(() => {
    checkStatus();

    if (pollIntervalMs && pollIntervalMs > 0) {
      const timer = setInterval(checkStatus, pollIntervalMs);
      return () => clearInterval(timer);
    }
  }, [checkStatus, pollIntervalMs]);

  return { status, refresh: checkStatus };
}
