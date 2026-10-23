# Phase 2 — Authentication & Authorization Foundation

**Project:** Reusable Self-Hosted RAG Platform  
**Phase:** 2  
**Status:** Planned  
**Predecessor:** Phase 1 — Configuration & White-Label System

---

# 1. Phase Objective

Phase 2 establishes a secure identity and access-control foundation for the RAG platform without prematurely implementing document, RAG, or LLM functionality.

Target architecture:

```text
                    Client Deployment
                           │
                    ┌──────▼──────┐
                    │   Browser   │
                    └──────┬──────┘
                           │
                    Authentication
                           │
                    ┌──────▼──────┐
                    │   FastAPI   │
                    │ Auth Layer  │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
          PostgreSQL                  Redis
       identity/session             ephemeral
          persistence               coordination
```

By the end of Phase 2, the application must support:

- User identity management
- Secure password authentication
- Access and refresh token architecture
- Secure refresh-token rotation
- Logout and session revocation
- Authentication middleware/dependencies
- Role-based authorization foundation
- Protected API routes
- Current-user endpoint
- Secure password storage
- Authentication database models
- Database migrations
- Frontend authentication state
- Protected frontend routes
- Session restoration
- Unauthorized handling
- Token refresh handling
- Security-focused tests

---

# 2. Critical Deployment Architecture Decision

This project uses a **dedicated deployment per client**.

It is **not** a shared SaaS multi-tenant application.

Target model:

```text
                    RAG CODEBASE
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
        Client A                 Client B
        Server                  Server
             │                       │
       PostgreSQL A             PostgreSQL B
       Redis A                  Redis B
             │                       │
       Client A data            Client B data
```

Therefore Phase 2 must **not** introduce:

```text
tenant_id
organization_id on every table
cross-tenant database isolation
tenant routing
shared SaaS tenancy
```

Instead:

```text
One deployment
      ↓
One client
      ↓
One logical organization
      ↓
Many users
      ↓
RBAC
```

The identity model should remain extensible enough to introduce a broader organization abstraction later without requiring a complete authentication rewrite.

---

# 3. Scope

## 3.1 In Scope

### Identity

- User model
- User status
- Email identity
- Password hash
- Display name
- User timestamps
- Last-login tracking

### Authentication

- Login
- Logout
- Access token
- Refresh token
- Refresh rotation
- Token expiration
- Session revocation
- Current-user endpoint

### Authorization

- Roles
- Permission/role checking foundation
- Protected APIs
- Authorization dependencies

### Security

- Password hashing
- Secure token generation
- Refresh token hashing
- Cookie security
- CORS/credentials compatibility
- Brute-force protection foundation
- Security logging
- Authentication error handling

### Frontend

- Authentication state
- Login page
- Protected routes
- Session restoration
- Logout
- Unauthorized handling
- Token refresh handling

### Testing

- Authentication unit tests
- Authentication API tests
- Authorization tests
- Security tests
- Frontend authentication tests
- Docker integration
- Regression tests

---

# 4. Explicitly Out of Scope

Do **not** implement:

```text
Document upload
PDF processing
OCR
Chunking
Embeddings
Vector search
Hybrid search
Reranking
LLM providers
Prompt management
RAG orchestration
Chat
Streaming
Conversation history
Billing
Usage metering
Admin analytics
Kubernetes
Cloud-specific infrastructure
SaaS multi-tenancy
SSO/SAML
OAuth providers
Social login
MFA
Passwordless authentication
```

SSO, MFA, OAuth, and passwordless authentication may be added later without compromising the foundation if the interfaces are designed correctly.

---

# 5. Phase 2 Chunk Structure

Phase 2 consists of ten implementation chunks:

```text
Phase 2
│
├── 2.1 Authentication Architecture & Security Contract
├── 2.2 User & Role Persistence
├── 2.3 Password Security & Credential Services
├── 2.4 Access & Refresh Token System
├── 2.5 Authentication API
├── 2.6 Authorization & Protected APIs
├── 2.7 Frontend Authentication
├── 2.8 Session Security & Abuse Protection
├── 2.9 End-to-End Authentication Verification
└── 2.10 Phase 2 Acceptance Audit
```

Each chunk must be independently implemented, tested, reviewed, and accepted before proceeding.

---

# 6. Chunk 2.1 — Authentication Architecture & Security Contract

## Objective

Define the complete authentication architecture before implementing it.

Inspect Phase 0 and Phase 1 first. Do not immediately start writing authentication endpoints.

## Identity Model

Conceptual model:

```text
User
 ├── id
 ├── email
 ├── password_hash
 ├── display_name
 ├── role
 ├── status
 ├── created_at
 ├── updated_at
 └── last_login_at
```

## User Status

Initial states:

```text
active
inactive
suspended
```

Do not introduce unnecessary states.

## Role Model

Initial roles should be minimal:

```text
ADMIN
USER
```

Add a third role only if there is a concrete product requirement.

Do not create speculative roles such as:

```text
SUPER_ADMIN
ORG_ADMIN
CONTENT_MANAGER
DOCUMENT_ADMIN
```

without a real authorization requirement.

## Token Model

Recommended architecture:

```text
Access Token
    ↓
Short-lived
    ↓
JWT
    ↓
Authorization header
```

and:

```text
Refresh Token
    ↓
Longer-lived
    ↓
Opaque random token
    ↓
HttpOnly Secure cookie
    ↓
Hashed server-side
```

Do not use a long-lived JWT refresh token as the primary design.

## Security Contract

Access token:

```text
10–15 minutes
```

Exact duration must be configuration-driven.

Refresh token:

```text
7–30 days
```

Exact duration must be configuration-driven.

Production cookie:

```text
HttpOnly
Secure
SameSite=Lax
```

Cookie domain and path must be deployment-aware and must not be hardcoded to a particular client/domain.

## Acceptance Criteria

- [ ] Authentication architecture documented.
- [ ] User lifecycle defined.
- [ ] Roles defined.
- [ ] Access token strategy defined.
- [ ] Refresh token strategy defined.
- [ ] Cookie strategy defined.
- [ ] Revocation strategy defined.
- [ ] Security assumptions documented.
- [ ] No unnecessary authentication implementation introduced.

---

# 7. Chunk 2.2 — User & Role Persistence

## Objective

Create persistent identity storage.

## User Table

Conceptually:

```text
users
--------------------------------
id
email
password_hash
display_name
role
status
created_at
updated_at
last_login_at
```

Use UUIDs rather than sequential public IDs.

## Email

Normalize email before lookup/storage.

Example:

```text
ALOK@EXAMPLE.COM
```

becomes:

```text
alok@example.com
```

Enforce uniqueness at the database level.

## Password Hash

Never store:

```text
password
```

Store only:

```text
password_hash
```

Recommended algorithm:

```text
Argon2id
```

Use bcrypt only as a deliberate fallback if Argon2id is not practical in the established dependency/runtime environment.

## Roles

For current project scale, use a role enum or constrained field rather than building a generic permission database prematurely.

Initial values:

```text
ADMIN
USER
```

## Alembic

Create an appropriate migration, for example:

```text
0002_auth_users.py
```

The migration must support:

```text
upgrade
downgrade
```

## Tests

- [ ] User creation
- [ ] Duplicate email rejection
- [ ] Email normalization
- [ ] Role validation
- [ ] Status validation
- [ ] UUID generation
- [ ] Migration upgrade
- [ ] Migration downgrade

---

# 8. Chunk 2.3 — Password Security & Credential Services

## Objective

Create a dedicated credential service.

Potential structure:

```text
backend/app/services/auth/
├── password.py
├── tokens.py
├── sessions.py
└── authentication.py
```

Adapt naming to the existing repository rather than duplicating existing service patterns.

## Password API

Provide:

```python
hash_password(password)
verify_password(password, password_hash)
```

Requirements:

- Never log passwords.
- Never return password hashes through API responses.
- Use a vetted password hashing library.
- Keep password policy configuration-driven where appropriate.

## Password Policy

Use a reasonable minimum length, for example:

```text
8–12 characters minimum
```

Prefer a strong minimum length over arbitrary composition rules.

Do not impose unnecessary requirements such as multiple symbols or uppercase counts without a business/security requirement.

## Tests

- [ ] Password hashes successfully.
- [ ] Correct password verifies.
- [ ] Incorrect password fails.
- [ ] Empty/invalid password fails.
- [ ] Password cannot be reversed.
- [ ] Password never appears in serialized user response.
- [ ] Password never appears in logs.

---

# 9. Chunk 2.4 — Access & Refresh Token System

## Objective

Implement secure session/token infrastructure.

## Access Token

JWT payload should contain only required claims.

Example:

```json
{
  "sub": "user-uuid",
  "type": "access",
  "iat": 123,
  "exp": 456,
  "jti": "token-id"
}
```

Do not put:

```text
password
large permission objects
private configuration
unnecessary sensitive user data
```

inside the token.

## JWT Configuration

Configuration should come from the Phase 1 settings system:

```text
JWT_SECRET
JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS
```

Never hardcode secrets.

The algorithm must be allowlisted and must not be selected dynamically from untrusted token input.

## Refresh Tokens

Generate cryptographically secure random bytes.

Conceptual flow:

```text
Browser
   ↓
opaque refresh token
   ↓
HttpOnly cookie
   ↓
server stores token hash
```

Never store the raw refresh token in PostgreSQL.

## Refresh Session Table

Recommended:

```text
auth_sessions
--------------------------------
id
user_id
token_hash
expires_at
created_at
revoked_at
last_used_at
user_agent
ip_address
```

Only retain user-agent/IP information if operationally justified. Treat it as security-sensitive operational data.

## Refresh Rotation

Flow:

```text
Refresh request
      ↓
Find token hash
      ↓
Validate session
      ↓
Revoke old refresh token
      ↓
Create new refresh token
      ↓
Issue new access token
      ↓
Set new cookie
```

If a revoked refresh token is reused, treat it as potential token theft and invalidate the appropriate session/family according to the documented policy.

## Tests

- [ ] Access token creation
- [ ] Access token validation
- [ ] Expired access token
- [ ] Invalid signature
- [ ] Wrong token type
- [ ] Refresh token creation
- [ ] Refresh token hashing
- [ ] Refresh rotation
- [ ] Revocation
- [ ] Reuse detection

---

# 10. Chunk 2.5 — Authentication API

## Objective

Expose authentication operations.

Recommended API:

```text
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

Password-change functionality should be deferred unless required by the current product scope.

## Login

Request:

```json
{
  "email": "user@example.com",
  "password": "..."
}
```

Response:

```json
{
  "user": {
    "id": "...",
    "email": "...",
    "displayName": "...",
    "role": "user"
  },
  "accessToken": "..."
}
```

Refresh token must be set through a secure cookie rather than returned in JSON.

## Authentication Errors

Do not distinguish:

```text
user doesn't exist
```

from:

```text
password is wrong
```

Use a generic response:

```text
Invalid email or password.
```

This reduces account enumeration.

## `/me`

```http
GET /api/v1/auth/me
```

returns authenticated user information.

Never return:

```text
password_hash
raw refresh token
session internals
```

## Logout

Should:

1. Identify the current session.
2. Revoke the refresh session.
3. Clear the refresh cookie.
4. Return success.

## Tests

- [ ] Successful login
- [ ] Invalid password
- [ ] Unknown email
- [ ] Email normalization
- [ ] Access token returned
- [ ] Refresh cookie set
- [ ] Secure cookie attributes
- [ ] `/me`
- [ ] Logout
- [ ] Revoked session
- [ ] Refresh
- [ ] Refresh rotation
- [ ] Generic authentication errors

---

# 11. Chunk 2.6 — Authorization & Protected APIs

## Objective

Establish reusable authorization dependencies.

Conceptual APIs:

```python
get_current_user()
require_role(Role.ADMIN)
```

Architecture:

```text
Request
  ↓
Access Token
  ↓
Current User
  ↓
Authorization
  ↓
Endpoint
```

## Authentication Dependency

`get_current_user()` should:

1. Extract the Authorization header.
2. Validate Bearer token format.
3. Validate JWT signature.
4. Validate expiry.
5. Validate token type.
6. Resolve the user.
7. Verify user status.
8. Return the authenticated user.

## Authorization

Use reusable dependencies rather than duplicating checks in every endpoint.

Conceptual example:

```python
@router.get("/admin-only")
async def admin_endpoint(
    user: User = Depends(require_role(Role.ADMIN))
):
    ...
```

Do not add permanent fake business endpoints solely for authorization testing.

## HTTP Semantics

Use:

```text
401 = unauthenticated
403 = authenticated but unauthorized
```

## Tests

- [ ] No token → 401
- [ ] Malformed token → 401
- [ ] Expired token → 401
- [ ] Invalid signature → 401
- [ ] Wrong token type → 401
- [ ] Inactive/suspended user denied according to policy
- [ ] Valid user → 200
- [ ] Admin → admin operation allowed
- [ ] Normal user → admin operation denied with 403

---

# 12. Chunk 2.7 — Frontend Authentication

## Objective

Integrate authentication into React without storing sensitive refresh credentials in browser storage.

## Suggested Structure

```text
frontend/src/auth/
├── types.ts
├── authApi.ts
├── AuthProvider.tsx
├── useAuth.ts
├── ProtectedRoute.tsx
└── authStorage.ts
```

Adapt to the existing project structure rather than creating duplicate abstractions.

## Token Storage

Recommended:

```text
Access token
    ↓
Memory only

Refresh token
    ↓
HttpOnly cookie
```

Avoid:

```text
localStorage.accessToken
localStorage.refreshToken
sessionStorage.refreshToken
```

## Application Startup

Target flow:

```text
React startup
      ↓
ConfigProvider
      ↓
AuthProvider
      ↓
GET /auth/me
      │
      ├── 200 → authenticated
      │
      └── 401 → attempt refresh
                     │
                     ├── success → authenticated
                     └── failure → logged out
```

Configuration must initialize before authentication if authentication depends on runtime API configuration.

## Login

```text
Login form
   ↓
POST /auth/login
   ↓
Access token in memory
   ↓
User state
   ↓
Protected application
```

## API Interceptor

Centralized API handling should support:

```text
401
 ↓
refresh
 ↓
retry original request once
```

Important:

- Never allow infinite refresh loops.
- Prevent concurrent 401 responses from triggering uncontrolled refresh storms.
- Use a single-flight refresh mechanism where appropriate.

## Logout

```text
logout
 ↓
POST /auth/logout
 ↓
clear memory token
 ↓
clear user
 ↓
navigate /login
```

## Tests

- [ ] Login UI
- [ ] Login success
- [ ] Login failure
- [ ] Protected route
- [ ] Auth restoration
- [ ] Refresh
- [ ] Logout
- [ ] 401 handling
- [ ] Concurrent 401 behavior
- [ ] No token in localStorage
- [ ] No refresh token in JavaScript storage

---

# 13. Chunk 2.8 — Session Security & Abuse Protection

## Objective

Harden authentication against common attacks.

## Login Rate Limiting

Use Redis from Phase 0.

Conceptually:

```text
IP + email
      ↓
rate-limit key
      ↓
Redis
```

Use progressive throttling/rate limiting rather than permanent account lockout based on a small number of failures.

Exact limits must be configuration-driven.

## Timing

Authentication failures should avoid obvious timing differences between:

```text
unknown email
```

and:

```text
wrong password
```

Use the password verification path appropriately to reduce account-enumeration/timing leakage.

## Cookie Security

Production refresh cookie should use:

```text
HttpOnly
Secure
SameSite=Lax
```

and an explicit path appropriate to the API.

Do not hardcode production cookie domains.

For cross-site deployments, SameSite and CORS must be deliberately configured rather than copied from development.

## CSRF Consideration

Because refresh tokens are cookie-based, explicitly document the CSRF model.

If state-changing APIs authenticate using:

```text
Authorization: Bearer ...
```

and the refresh cookie is only used to obtain access tokens, the CSRF exposure is reduced.

Still ensure:

- Explicit SameSite policy
- Strict CORS
- Origin validation where appropriate
- No sensitive state-changing operation is authenticated solely by the refresh cookie

## Security Logging

Log security events such as:

```text
login success
login failure
logout
refresh
refresh reuse/revocation
```

Never log:

```text
password
access token
refresh token
JWT secret
cookie contents
```

---

# 14. Chunk 2.9 — End-to-End Authentication Verification

This is the integration gate before the final audit.

## Scenario A — Admin

Create:

```text
admin@example.com
```

Verify:

```text
password stored as hash
login succeeds
access token issued
refresh cookie issued
/me works
```

## Scenario B — Normal User

Create:

```text
user@example.com
```

Verify:

```text
login succeeds
/me works
admin operation denied
```

## Scenario C — Logout

```text
login
 ↓
logout
 ↓
refresh
```

Expected:

```text
refresh fails
old session revoked
```

## Scenario D — Refresh Rotation

```text
login
 ↓
refresh token A
 ↓
refresh
 ↓
token B
```

Verify:

```text
A revoked
B valid
```

## Scenario E — Refresh Reuse

Attempt to reuse token A after rotation.

Expected:

```text
reuse detected
session/family invalidated according to policy
new authentication required
```

## Scenario F — Expired Access Token

```text
expired access token
      ↓
API request
      ↓
401
      ↓
refresh
      ↓
new access token
      ↓
retry once
```

## Scenario G — Configuration Switching

Phase 1 white-label behavior must remain intact regardless of:

```text
organization name
assistant name
theme
logo
```

---

# 15. Chunk 2.10 — Phase 2 Acceptance Audit

This chunk is **READ-ONLY verification**.

The auditor must:

## Repository

- Inspect all Phase 2 changes.
- Check Git status/diff.
- Identify unrelated modifications.

## Backend

Run the complete test suite:

```text
pytest
```

## Frontend

Run:

```text
npm test
npm run build
```

## Database

Verify:

```text
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

## Docker

Verify:

```text
docker compose build
docker compose up -d
docker compose ps
```

## Authentication

Verify:

```text
login
logout
refresh
refresh rotation
refresh reuse
/me
expired token
invalid token
inactive user
```

## Authorization

Verify:

```text
authenticated user
unauthenticated user
admin
normal user
```

## Security

Search for:

```text
password logging
token logging
JWT secret leakage
refresh token persistence
localStorage tokens
sessionStorage tokens
hardcoded secrets
hardcoded cookie domains
```

## Scope

Confirm no:

```text
document processing
embedding
vector search
LLM
RAG
chat
streaming
```

has been introduced.

---

# 16. Authentication Data Model

Target database structure:

```text
PostgreSQL
│
├── users
│
└── auth_sessions
```

## users

```text
id
email
password_hash
display_name
role
status
created_at
updated_at
last_login_at
```

## auth_sessions

```text
id
user_id
token_hash
expires_at
created_at
revoked_at
last_used_at
user_agent
ip_address
```

Use foreign-key constraints.

---

# 17. Token Lifecycle

```text
                    LOGIN
                      │
                      ▼
                Credentials
                   valid?
                 /       \
               no         yes
               │           │
              401          ▼
                       Create session
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
             Access token      Refresh token
             memory only       HttpOnly cookie
                  │                 │
                  ▼                 ▼
                APIs          Refresh endpoint
                                    │
                                    ▼
                              Rotate token
                                    │
                              ┌─────┴─────┐
                              ▼           ▼
                            Valid       Reuse
                              │           │
                              ▼           ▼
                           Continue    Revoke
```

---

# 18. API Contract

Recommended Phase 2 API:

```text
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

Additional password-management endpoints are deferred unless required.

---

# 19. Error Contract

Reuse the centralized Phase 0 error structure:

```json
{
  "error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "Invalid email or password.",
    "request_id": "..."
  }
}
```

Potential error codes:

```text
AUTHENTICATION_FAILED
TOKEN_INVALID
TOKEN_EXPIRED
SESSION_REVOKED
FORBIDDEN
USER_INACTIVE
RATE_LIMITED
```

Do not expose internal exception details.

---

# 20. Security Requirements

Phase 2 must satisfy all of the following:

- [ ] Passwords are never stored plaintext.
- [ ] Password hashes never leave backend APIs.
- [ ] Access tokens are short-lived.
- [ ] Refresh tokens are opaque.
- [ ] Refresh tokens are stored hashed.
- [ ] Refresh tokens are HttpOnly.
- [ ] Production refresh cookies use Secure.
- [ ] Cookie SameSite policy is explicit.
- [ ] JWT secret is configuration-driven.
- [ ] JWT algorithm is configuration-driven and allowlisted.
- [ ] Token type is validated.
- [ ] Token expiry is validated.
- [ ] Refresh rotation is implemented.
- [ ] Revocation is implemented.
- [ ] Refresh reuse is detected.
- [ ] Authentication errors do not reveal account existence.
- [ ] Tokens are never logged.
- [ ] Passwords are never logged.
- [ ] Login abuse is rate-limited.
- [ ] Access control is centralized.
- [ ] Feature flags are not treated as authorization.
- [ ] No credentials are stored in localStorage.

---

# 21. Testing Matrix

| ID | Test | Expected |
|---|---|---|
| A001 | User creation | PASS |
| A002 | Duplicate email | Rejected |
| A003 | Password hashing | PASS |
| A004 | Password verification | PASS |
| A005 | Invalid password | 401 |
| A006 | Unknown email | 401 |
| A007 | Successful login | 200 |
| A008 | Access token validation | PASS |
| A009 | Expired access token | 401 |
| A010 | Invalid signature | 401 |
| A011 | `/auth/me` authenticated | 200 |
| A012 | `/auth/me` unauthenticated | 401 |
| A013 | Refresh | 200 |
| A014 | Refresh rotation | PASS |
| A015 | Refresh reuse | Rejected/revoked |
| A016 | Logout | PASS |
| A017 | Revoked session | Rejected |
| A018 | Admin authorization | PASS |
| A019 | Normal-user authorization | 403 |
| A020 | Login rate limiting | PASS |
| A021 | Cookie security | PASS |
| A022 | Token logging audit | PASS |
| A023 | Frontend auth restoration | PASS |
| A024 | Frontend logout | PASS |
| A025 | 401 retry | PASS |
| A026 | Concurrent refresh | Single-flight |
| A027 | Phase 1 regression | PASS |
| A028 | Phase boundary | PASS |

---

# 22. Definition of Done

## Identity

- [ ] User model implemented
- [ ] User migration implemented
- [ ] Email uniqueness enforced
- [ ] User status implemented
- [ ] Role implemented

## Authentication

- [ ] Login
- [ ] Logout
- [ ] Refresh
- [ ] `/me`
- [ ] Access token
- [ ] Refresh token
- [ ] Rotation
- [ ] Revocation
- [ ] Reuse detection

## Authorization

- [ ] Current-user dependency
- [ ] Role dependency
- [ ] 401/403 semantics
- [ ] Protected endpoint verification

## Frontend

- [ ] AuthProvider
- [ ] Login
- [ ] Protected routes
- [ ] Session restoration
- [ ] Refresh handling
- [ ] Logout
- [ ] Unauthorized handling

## Security

- [ ] Argon2id/bcrypt password hashing
- [ ] No plaintext passwords
- [ ] No browser refresh-token storage
- [ ] Secure cookies
- [ ] Secret masking
- [ ] Rate limiting
- [ ] Token reuse detection
- [ ] Security logging

## Regression

- [ ] Phase 0 tests pass
- [ ] Phase 1 tests pass
- [ ] Phase 2 backend tests pass
- [ ] Phase 2 frontend tests pass
- [ ] Production frontend build passes
- [ ] Docker stack passes
- [ ] Alembic migration cycle passes

---

# 23. Phase 2 Final Report

The completion report should follow:

```text
PHASE 2 — AUTHENTICATION & AUTHORIZATION COMPLETION REPORT

Status: PASS / PARTIAL / FAILED

Identity: PASS
User Persistence: PASS
Password Security: PASS
Authentication: PASS
Access Tokens: PASS
Refresh Tokens: PASS
Session Management: PASS
Authorization: PASS
Frontend Authentication: PASS
Security Hardening: PASS
Docker: PASS
Documentation: PASS

Backend Tests: X passed / Y failed
Frontend Tests: X passed / Y failed

Authentication E2E: PASS / FAIL
Authorization E2E: PASS / FAIL
Security Audit: PASS / FAIL
Regression: PASS / FAIL
Phase Boundary: PASS / FAIL

Known Issues:
...

Deferred Items:
...

Files Created:
...

Files Modified:
...

Next Phase:
Phase 3 — Document Management
```

---

# 24. Phase 2 Agent Execution Rules

These rules apply to every implementation chunk.

1. Inspect the actual repository before modifying anything.
2. Search for existing functionality before creating new abstractions.
3. Extend existing Phase 0/1 infrastructure instead of duplicating it.
4. Implement only the current chunk.
5. Do not implement document, RAG, or LLM functionality.
6. Do not introduce SaaS multi-tenancy.
7. Never store plaintext passwords.
8. Never store raw refresh tokens server-side.
9. Never put refresh tokens in localStorage.
10. Never log passwords or tokens.
11. Do not expose authentication internals through errors.
12. Reuse the existing centralized error handling.
13. Reuse the existing configuration system.
14. Use Redis for rate limiting and ephemeral coordination.
15. Use SQLAlchemy/Alembic established in Phase 0.
16. Every database change requires an Alembic migration.
17. Every security-sensitive behavior requires automated tests.
18. Run the full regression suite after each chunk.
19. Review generated code for unnecessary abstractions.
20. Do not weaken security merely to make tests pass.
21. Do not claim success without executable verification.
22. Record warnings and technical debt separately from blockers.
23. Stop after the current chunk and provide a completion report.
24. Do not begin the next chunk until the current chunk is accepted.

---

# 25. Phase 2 Success Definition

The strongest definition of success is:

> **A client can deploy the platform, create an administrator and normal user, authenticate securely, maintain a session, refresh credentials without exposing refresh tokens to JavaScript, log out, and enforce role-based access to protected APIs while all Phase 0 and Phase 1 functionality continues to work unchanged.**

Final architecture:

```text
                         Browser
                            │
                 ┌──────────┴──────────┐
                 │                     │
           Runtime Config          Authentication
                 │                     │
                 ▼                     ▼
            Config API             Auth API
                                       │
                              ┌────────┴────────┐
                              │                 │
                           Access           Refresh
                           Token             Cookie
                              │                 │
                              ▼                 ▼
                         Protected APIs      Sessions
                              │                 │
                              └────────┬────────┘
                                       ▼
                                  PostgreSQL
                                       │
                              ┌────────┴────────┐
                              │                 │
                            users         auth_sessions

                                  Redis
                                    │
                           rate limiting /
                           ephemeral auth
                           coordination
```

Phase 2 should leave the platform with a proper security boundary before the significantly higher-risk document ingestion and knowledge pipeline work begins.
