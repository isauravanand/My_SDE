# MySDE — Security Specification & Guidelines

**Document Version:** 3.0.0  
**Phase:** Phase 3 (Projects, Tasks, and API-Connected Dashboard)  
**Classification:** Confidential / Engineering Standard  

---

## 1. Threat Modeling & Core Security Tenets

As an AI-driven development tool that accesses proprietary repositories, generates code, and runs tests, MySDE operates in a high-trust environment.

### 1.1 Non-Negotiable Tenets
1. **Never Execute Untrusted Code In-Process:** Repository code, third-party libraries, build scripts, and test runners must NEVER run on the main FastAPI application server or host machine.
2. **Secrets Never Enter Logs or AI Context:** Tokens, private keys, passwords, and `.env` contents must be filtered prior to persistence, transmission, or prompt ingestion.
3. **Strict Multi-Tenant Isolation:** Workspace boundaries are absolute. No user or agent run may access or mutate records belonging to another workspace.
4. **Human Authorization for Code Delivery:** Branch creation and PR publication require explicit user approval.
5. **Zero Client-Side Token Storage:** Authentication credentials and raw session tokens are NEVER stored in localStorage or sessionStorage.

---

## 2. Authentication & Session Architecture

### 2.1 Password Hashing with Argon2id
All user passwords are encrypted using the **Argon2id** password-hashing standard via `argon2-cffi`:
- **Time cost:** 2 iterations
- **Memory cost:** 64 MB (65536 KiB)
- **Parallelism:** 1 thread
- **Hash length:** 32 bytes
- **Salt length:** 16 bytes

### 2.2 Server-Managed Opaque Sessions
Instead of stateless JWTs (which cannot be revoked instantly without distributed blacklists), MySDE uses **stateful server-side sessions** stored in PostgreSQL:
- **Raw Token:** 32-byte cryptographically secure random token generated with `secrets.token_urlsafe(32)`.
- **Database Persistence:** The raw token is NEVER stored in the database. Only its SHA-256 hex digest (`token_hash`) is indexed and persisted.
- **Delivery via HttpOnly Cookie:** Delivered to browsers as an `HttpOnly` cookie (`mysde_session`).
- **Cookie Security Attributes:**
  - `HttpOnly`: Enabled (prevents access via JavaScript / XSS).
  - `SameSite`: Configured to `Lax` (blocks cross-site tracking and simple CSRF vectors).
  - `Secure`: True in production environments (enforces HTTPS delivery).
  - `Path`: Restricted to `/`.
  - `Max-Age`: 7 days with automatic expiration and revocation verification on every request.

### 2.3 Cross-Site Request Forgery (CSRF) Defense
Cookie-authenticated state-changing operations (`POST`, `PUT`, `PATCH`, `DELETE`) are fortified against CSRF attacks:
- **Readable CSRF Cookie (`mysde_csrf`):** Contains an independent random token.
- **Custom Header Requirement (`X-CSRF-Token`):** The SPA reads the `mysde_csrf` cookie and injects its value into the `X-CSRF-Token` header on state-changing requests.
- **Constant-Time Verification:** The backend compares the header against the cookie using `hmac.compare_digest` in constant time before processing the request.

### 2.4 Rate Limiting
Authentication-sensitive endpoints (`/auth/login`, `/auth/register`, `/auth/forgot-password`, `/auth/resend-verification`) are rate-limited via an in-memory sliding-window bucket (10 requests per minute per IP address), returning HTTP 429 when limits are breached.

---

## 3. Account Recovery & Email Verification

### 3.1 Single-Use Security Tokens
- All verification and password reset workflows use single-use cryptographic tokens.
- Stored exclusively as SHA-256 hashes in `security_tokens`.
- Enforces strict expiration (24h for email verification, 60m for password resets).
- Immediately invalidated upon successful consumption (`consumed_at = NOW()`).
- On password reset, all existing active user sessions are revoked atomically.

### 3.2 Privacy-Preserving Responses
- Endpoint `/auth/forgot-password` returns an identical success response regardless of whether the email address is registered, preventing user enumeration attacks.

---

## 4. Multi-Tenant Authorization & Workspace Isolation

- **Default Workspace Atomic Creation:** Upon registration, a User, a default Workspace, an owner `WorkspaceMembership`, and a verification token are committed atomically.
- **Owner Protection Rules:** The workspace owner cannot have their role downgraded or removed through ordinary membership operations.
- **Enumeration Prevention:** Attempting to access a workspace or member that does not belong to the authenticated user returns HTTP 404 (Not Found) rather than 403 (Forbidden).

---

## 5. Projects & Tasks Security Safeguards (Phase 3)

### 5.1 Workspace Boundary Verification
All Project and Task routes pass through dedicated dependency injection guards:
- `resolve_project_workspace`: Checks that the project exists AND that the authenticated user possesses an active membership in the owning workspace.
- `resolve_task_workspace`: Resolves the task and guarantees the authenticated user is authorized for the task's workspace.
- Unowned or inaccessible resources consistently yield HTTP 404 (Not Found) to completely hide resource existence from unauthorized callers.

### 5.2 Negative Security Rules Enforced
1. **Cross-Workspace Reads:** A user cannot view projects or tasks belonging to another workspace.
2. **Cross-Workspace Creation:** A user cannot create a task in a project belonging to another workspace.
3. **Cross-Workspace Reassignment:** A user cannot reassign a task's `project_id` to a project in another workspace.
4. **Unauthorized Assignee Guard:** A task cannot be assigned to an account that is not an active member of that workspace.
5. **Archived Project Immutability:** Tasks cannot be created under an archived project unless it is explicitly restored first.

### 5.3 Audit Trail & Activity Log Privacy
- Activity logs record event types, resource types, and structured metadata.
- Sensitive parameters (passwords, tokens, verification hashes) are explicitly excluded from activity metadata.

---

## 6. GitHub App Security & Webhook Protections (Phase 4)

### 6.1 Cryptographic Key Management & Zero Client-Side Secret Leakage
- **RS256 JWT Generation:** The GitHub App private key is loaded server-side only (via file path or environment variable) and used to sign short-lived RS256 JWTs (maximum 9-minute validity).
- **Ephemeral Installation Tokens:** Installation access tokens are generated on-demand server-side and cached in memory with automatic expiration buffers. Raw tokens are never logged, persisted to disk, or sent to the frontend.
- **Header Masking:** Sensitive Authorization headers and private keys are scrubbed by the structured logging engine.

### 6.2 OAuth & Callback Flow Fortification
- **Single-Use State Tokens:** Installation requests generate a 32-byte cryptographically secure random token (`secrets.token_urlsafe(32)`), stored in `github_oauth_states` with a 15-minute expiration time.
- **User & Workspace Binding:** On callback, the state token is validated to match the initiating user's ID and the target workspace ID.
- **Replay Protection:** State tokens are marked `consumed_at = NOW()` immediately upon successful callback validation and cannot be reused.
- **Cross-Workspace Association Guard:** If a GitHub `installation_id` is already actively bound to another workspace, attempting to bind it to a second workspace is rejected with HTTP 409 (Conflict).

### 6.3 Webhook HMAC Verification & Deduplication
- **Constant-Time HMAC:** Every webhook payload is verified using `hmac.compare_digest` against `X-Hub-Signature-256` using the pre-shared `GITHUB_WEBHOOK_SECRET`.
- **Durable Delivery Deduplication:** GitHub's `X-GitHub-Delivery` GUID is stored in `github_webhook_deliveries`. Duplicate delivery attempts are recognized and acknowledged idempotently without re-executing state changes.
- **Untrusted Webhook Payloads:** Webhook events cannot mutate resources across workspace boundaries; the target workspace is always resolved through verified, server-persisted installation records.

### 6.4 Role-Based Integration Governance
- Connecting, disconnecting, and toggling repository selections are strictly restricted to users holding the `owner` or `admin` role in the target workspace. Standard `member` accounts are rejected with HTTP 403 (Forbidden).
