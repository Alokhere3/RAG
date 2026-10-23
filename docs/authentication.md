# Authentication & Authorization Architecture Specification

**Phase:** Phase 2 — Authentication & Authorization Foundation  
**Version:** 1.0.0  
**Status:** Approved Architecture Contract  

---

## 1. Architectural Principles & Deployment Model

### Single-Tenant Deployment Architecture
The RAG platform utilizes an **isolated deployment model per client** (dedicated container stack, dedicated PostgreSQL database, dedicated Redis cache).

```text
               Client A Deployment                Client B Deployment
            ┌──────────────────────┐           ┌──────────────────────┐
            │   Nginx + Frontend   │           │   Nginx + Frontend   │
            │   FastAPI Auth Core  │           │   FastAPI Auth Core  │
            │   PostgreSQL (Client)│           │   PostgreSQL (Client)│
            │   Redis (Client)     │           │   Redis (Client)     │
            └──────────────────────┘           └──────────────────────┘
```

#### Tenancy Rules
- **No shared multi-tenant SaaS tables**: There is NO `tenant_id` or `organization_id` column required on database tables.
- **Single logical tenant per database**: All users in a given database belong to the deploying organization.
- **Future Extensibility**: User and session models are structured cleanly so that multi-organization grouping can be introduced in the future if required, without changing the authentication token contract.

---

## 2. Identity Model

### User Entity Specification
The persistent user identity is represented by the `User` model:

| Field | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID (v4) | Primary Key, Indexed | Opaque unique identifier |
| `email` | String(255) | Unique, Indexed, Not Null | Normalized (lowercase, trimmed) user email |
| `password_hash` | String(255) | Not Null | Cryptographic hash (Argon2id / bcrypt fallback) |
| `display_name` | String(100) | Not Null | Human-readable user name |
| `role` | Enum | Not Null, Default `USER` | Role enum (`ADMIN`, `USER`) |
| `status` | Enum | Not Null, Default `ACTIVE` | Account status (`ACTIVE`, `INACTIVE`, `SUSPENDED`) |
| `created_at` | DateTime (UTC) | Not Null, Default `utcnow` | Account registration timestamp |
| `updated_at` | DateTime (UTC) | Not Null, Default `utcnow` | Last profile update timestamp |
| `last_login_at` | DateTime (UTC) | Nullable | Timestamp of most recent successful login |

### User Lifecycle States
```text
                  ┌──────────────┐
                  │   INACTIVE   │ (Registered / Pending activation)
                  └──────┬───────┘
                         │ Activation
                         ▼
┌──────────────┐  Login  ┌──────────────┐  Block   ┌──────────────┐
│  SUSPENDED   │ ◄───────┤    ACTIVE    ├────────► │  SUSPENDED   │
└──────┬───────┘         └──────┬───────┘          └──────┬───────┘
       │                        │                         │
       └────────────────────────┴─────────────────────────┘
                    Suspended users: Login rejected,
                    active tokens revoked immediately
```

- **`ACTIVE`**: User can authenticate and consume authorized platform endpoints.
- **`INACTIVE`**: Account disabled or unconfirmed. Authentication attempts return `401 Unauthorized` with generic message.
- **`SUSPENDED`**: Administratively blocked. Authentication attempts return `401 Unauthorized`. Any presented tokens trigger immediate rejection.

---

## 3. Role-Based Access Control (RBAC)

### Initial Role Hierarchy
To prevent premature over-engineering, Phase 2 implements a minimal, strict two-role model:

```text
       ┌───────────┐
       │   ADMIN   │  Full platform access, user management, system diagnostics
       └─────┬─────┘
             │ Inherits all user capabilities
             ▼
       ┌───────────┐
       │   USER    │  Standard access to query knowledge base, view profile
       └───────────┘
```

- **`ADMIN`**:
  - Manage users (list, invite, deactivate, update roles)
  - Inspect platform health and system metrics
  - Configure organizational features
- **`USER`**:
  - Authenticate and manage own session
  - Read public configuration
  - Future: Ingest documents and interact with knowledge assistant

### Anti-Redundancy & Canonical Format Rule
- **Canonical Representation**: Roles are strictly represented by the typed `UserRole` enum (`ADMIN`, `USER`).
- **Single Backend Resolver**: Access control evaluation is centralized in `AccessControlService` and FastAPI dependency `require_role(required_role)`.
- **Single Frontend Source**: The client UI consumes a single `useAuth()` hook providing `user.role` and `hasRole(role)`.

---

## 4. Token & Session Architecture

### Dual-Token Architecture

```text
1. Login Request:
   POST /api/v1/auth/login (email, password)
      ↓
2. Credentials Verified:
   Backend validates password hash and checks user status == ACTIVE.
      ↓
3. Tokens Generated:
   ├── Short-Lived Access Token (JWT):
   │   • 15-minute expiration
   │   • Contains: sub (user_id), email, role, exp, iat, jti
   │   • Returned in JSON response body
   │
   └── Long-Lived Refresh Token (Opaque):
       • 7-day expiration
       • Cryptographically random 32-byte string
       • Stored hashed (SHA-256) in PostgreSQL refresh_tokens table
       • Delivered in HttpOnly, Secure, SameSite=Lax cookie
```

### Access Token Specification
- **Type**: JSON Web Token (JWT)
- **Signature Algorithm**: HMAC-SHA256 (`HS256`) using `JWT_SECRET`
- **Lifetime**: 15 minutes (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Storage Location**: Frontend in-memory state (React AuthContext)
- **Transmission**: HTTP `Authorization: Bearer <access_token>` header
- **Standard Claims**:
  ```json
  {
    "sub": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "role": "ADMIN",
    "token_type": "access",
    "iat": 1700000000,
    "exp": 1700000900,
    "jti": "8b8e04e0-7e44-4861-827c-3c3b018b1088"
  }
  ```

### Refresh Token Specification
- **Type**: High-entropy opaque string (e.g., `secrets.token_urlsafe(32)`)
- **Lifetime**: 7 days (configurable via `REFRESH_TOKEN_EXPIRE_DAYS`)
- **Storage Location**: Browser `HttpOnly` cookie (mitigates XSS extraction)
- **Database Storage**: Stored as SHA-256 hash in `refresh_tokens` table:
  ```text
  refresh_tokens
  ├── id (UUID)
  ├── user_id (UUID, FK -> users.id)
  ├── token_hash (String(64), SHA-256 hex digest)
  ├── expires_at (DateTime UTC)
  ├── created_at (DateTime UTC)
  ├── revoked_at (DateTime UTC, nullable)
  ├── replaced_by_token_id (UUID, nullable)
  ├── user_agent (String(255), nullable)
  └── ip_address (String(45), nullable)
  ```

---

## 5. Token Rotation & Replay Attack Protection

To defend against refresh token theft, the platform enforces **Strict Refresh Token Rotation with Automatic Reuse Detection**:

```text
Client                              Backend / Database
  │                                         │
  ├─── POST /api/v1/auth/refresh ──────────►│
  │    (with Cookie: refresh_token_v1)      │
  │                                         ├── 1. Look up SHA-256(refresh_token_v1)
  │                                         │
  │                                         ├── 2. CASE: Token is ACTIVE and UNREVOKED
  │                                         │   • Revoke refresh_token_v1 (revoked_at = NOW)
  │                                         │   • Issue refresh_token_v2 (linked via replaced_by)
  │                                         │   • Issue new access_token
  │◄── 200 OK (access_token) ───────────────┤
  │    Set-Cookie: refresh_token_v2         │
  │                                         │
  │                                         ├── 3. CASE: Token is ALREADY REVOKED (REUSE ATTEMPT!)
  │                                         │   • Potential token theft / replay attack detected!
  │                                         │   • Revoke ALL active sessions for this user
  │                                         │   • Log SECURITY_ALERT: REFRESH_TOKEN_REUSE
  │◄── 401 Unauthorized ────────────────────┤
  │    Clear-Cookie: refresh_token          │
```

---

## 6. Cookie Security Contract

The refresh token cookie is configured with defense-in-depth flags:

```http
Set-Cookie: rag_refresh_token=...; 
            Path=/api/v1/auth; 
            HttpOnly; 
            Secure; 
            SameSite=Lax; 
            Max-Age=604800
```

| Flag | Value | Purpose |
| :--- | :--- | :--- |
| **`HttpOnly`** | `true` | Prevents malicious client-side JavaScript / XSS scripts from reading the cookie |
| **`Secure`** | `true` in prod | Restricts transmission to TLS/HTTPS encrypted connections |
| **`SameSite`** | `Lax` | Protects against Cross-Site Request Forgery (CSRF) while allowing normal top-level navigation |
| **`Path`** | `/api/v1/auth` | Restricts browser cookie transmission strictly to auth endpoints (`/refresh`, `/logout`), withholding it from general API traffic |
| **`Domain`** | Omitted / dynamic | Deployment-aware; prevents hardcoding client domains |

---

## 7. Password Security & Storage

### Password Hashing Standards
- **Primary Algorithm**: **Argon2id** (memory-hard, resistant to GPU/ASIC cracking).
- **Secondary Fallback**: **bcrypt** (cost factor 12) if Argon2id C-extensions are unavailable in the host runtime.
- **Password Policies**:
  - Minimum length: 8 characters (12+ recommended for admin roles)
  - Maximum length: 128 characters (prevents DoS via computational hash exhaustion)
  - Never stored or logged in plain text anywhere.

---

## 8. Security Observability & Audit Logging

Login attempts are throttled through Redis using a combined IP/email key. The
window and attempt limit are configuration-driven (`LOGIN_RATE_LIMIT_ATTEMPTS`
and `LOGIN_RATE_LIMIT_WINDOW_SECONDS`). Redis failures fail open with a security
log event so an infrastructure outage does not disclose account state.

Structured logging events recorded by the authentication subsystem:

| Event Code | Severity | Trigger |
| :--- | :---: | :--- |
| `AUTH_LOGIN_SUCCESS` | INFO | User successfully authenticated |
| `AUTH_LOGIN_FAILURE` | WARN | Invalid password or unknown email |
| `AUTH_ACCOUNT_SUSPENDED` | WARN | Login attempted on suspended account |
| `AUTH_TOKEN_ISSUED` | INFO | New access token generated |
| `AUTH_TOKEN_REFRESHED` | INFO | Refresh token rotated successfully |
| `AUTH_TOKEN_REUSE_DETECTED` | **CRITICAL** | Revoked refresh token submitted (possible theft) |
| `AUTH_LOGOUT` | INFO | Session explicitly revoked by user |
| `ACCESS_RESOLUTION_STARTED` | DEBUG | Role authorization check initiated |
| `ACCESS_RESOLUTION_COMPLETED`| DEBUG | Role authorization resolved (allowed/denied) |

---

## 9. API Surface Definition (Phase 2 Master Contract)

All authentication endpoints are grouped under the `/api/v1/auth` namespace:

```http
POST /api/v1/auth/login        # Authenticate with email/password; returns access token + sets refresh cookie
POST /api/v1/auth/refresh      # Rotate refresh token cookie; returns new access token + new cookie
POST /api/v1/auth/logout       # Revoke current refresh session; clears cookie
GET  /api/v1/auth/me           # Protected: Return current authenticated user profile
```

Protected endpoints require:
```http
Authorization: Bearer <access_token>
```
If token is invalid, expired, or missing, endpoints return standard `HTTP 401 Unauthorized`:
```json
{
  "detail": "Could not validate credentials",
  "code": "UNAUTHORIZED"
}
```
If user lacks required role (e.g., standard USER requesting ADMIN resource), endpoints return standard `HTTP 403 Forbidden`:
```json
{
  "detail": "Insufficient permissions",
  "code": "FORBIDDEN"
}
```

---

## 10. Phase 2 Implementation Chunk Mapping

```text
Chunk 2.1: Authentication Architecture & Security Contract (THIS DOCUMENT)
Chunk 2.2: User & Role Persistence (SQLAlchemy User/RefreshToken models & Alembic migration)
Chunk 2.3: Password Security & Credential Services (Argon2id/bcrypt hashing & validation)
Chunk 2.4: Access & Refresh Token System (JWT generation, opaque token hashing & rotation)
Chunk 2.5: Authentication API (/login, /refresh, /logout, /me)
Chunk 2.6: Authorization & Protected APIs (FastAPI dependencies require_auth, require_role)
Chunk 2.7: Frontend Authentication (AuthContext, login page, protected routes, auto-refresh)
Chunk 2.8: Session Security & Abuse Protection (Redis rate limiting & reuse alerts)
Chunk 2.9: End-to-End Authentication Verification (Full login/refresh/role/logout verification)
Chunk 2.10: Phase 2 Acceptance Audit (Final sign-off against all requirements)
```
