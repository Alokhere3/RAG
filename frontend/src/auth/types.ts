export type UserRole = "admin" | "user";
export type UserStatus = "active" | "inactive" | "suspended";

export interface AuthUser {
  id: string;
  email: string;
  displayName?: string | null;
  role: UserRole;
  status: UserStatus;
}

export interface LoginResponse {
  user: AuthUser;
  accessToken: string;
  tokenType: string;
}
