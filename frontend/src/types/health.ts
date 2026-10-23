export interface HealthResponse {
  status: string;
}

export interface ReadinessDependencies {
  database: "ok" | "unavailable" | string;
  redis: "ok" | "unavailable" | string;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready" | string;
  dependencies: ReadinessDependencies;
}

export type ComponentStatus = "loading" | "healthy" | "unavailable" | "error";

export interface SystemStatusState {
  backend: ComponentStatus;
  database: ComponentStatus;
  redis: ComponentStatus;
  isLoading: boolean;
  error?: string;
  lastChecked?: string;
}
