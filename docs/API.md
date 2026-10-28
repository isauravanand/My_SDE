# MySDE — API Specification & Conventions

**Document Version:** 3.0.0  
**Phase:** Phase 3 (Projects, Tasks, and API-Connected Dashboard)  
**Base URL:** `/api/v1`  
**Protocol:** RESTful HTTPS / JSON  

---

## 1. Authentication & Cookie Conventions

Stateful server-managed sessions are utilized:
- **Session Cookie:** `mysde_session` (`HttpOnly`, `Path=/`, `SameSite=Lax`, `Secure` in production).
- **CSRF Cookie:** `mysde_csrf` (`Path=/`, `SameSite=Lax`).
- **CSRF Header:** For `POST`, `PUT`, `PATCH`, `DELETE` requests, clients must pass `X-CSRF-Token: <mysde_csrf_cookie_value>`.
- **CORS Requirements:** Web clients must set `credentials: 'include'` on all `fetch` or Axios calls.

---

## 2. Standard Response Envelope & Error Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request payload validation failed.",
    "details": [
      {
        "field": "title",
        "issue": "String should have at least 1 characters"
      }
    ],
    "request_id": "req_01j78bcd90ef"
  }
}
```

---

## 3. Endpoints Specification

### 3.1 Authentication (`/api/v1/auth`)

#### `POST /api/v1/auth/register`
Creates a user account, default workspace, owner membership, verification token, and starts a session.
- **Request Body:**
  ```json
  {
    "email": "developer@company.com",
    "password": "SuperSecretPassword123!",
    "full_name": "Jane Developer"
  }
  ```
- **Response (201 Created):** `UserResponse` + sets `mysde_session` & `mysde_csrf` cookies.

#### `POST /api/v1/auth/login`
Authenticates credentials and establishes a new server-side session.
- **Request Body:**
  ```json
  {
    "email": "developer@company.com",
    "password": "SuperSecretPassword123!"
  }
  ```
- **Response (200 OK):** `UserResponse` + sets cookies.

#### `POST /api/v1/auth/logout`
Revokes active session in PostgreSQL and clears cookies.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Response (200 OK):** `{"message": "Logged out successfully."}`

#### `GET /api/v1/auth/me`
Retrieves currently authenticated user profile.
- **Response (200 OK):** `UserResponse`

#### `POST /api/v1/auth/verify-email`
Verifies user email via single-use token.
- **Request Body:** `{"token": "single_use_token_string"}`
- **Response (200 OK):** `{"message": "Email verified successfully."}`

#### `POST /api/v1/auth/resend-verification`
Dispatches a new single-use verification email.

#### `POST /api/v1/auth/forgot-password`
Privacy-preserving password reset initiator.

#### `POST /api/v1/auth/reset-password`
Resets password and invalidates all existing active sessions.

---

### 3.2 Workspaces (`/api/v1/workspaces`)

#### `GET /api/v1/workspaces`
Lists all workspaces accessible to the authenticated user.

#### `POST /api/v1/workspaces`
Creates a new workspace with authenticated user as owner.

#### `GET /api/v1/workspaces/{workspace_id}`
Retrieves single workspace (returns 404 if user lacks membership).

#### `GET /api/v1/workspaces/{workspace_id}/members`
Lists all members in the workspace with assigned roles (`owner`, `admin`, `member`).

#### `PATCH /api/v1/workspaces/{workspace_id}/members/{membership_id}`
Updates a member's role (requires `owner` or `admin` role; owner cannot be downgraded).

---

### 3.3 Projects (`/api/v1/projects`)

#### `GET /api/v1/projects`
Lists all projects in the authorized workspace.
- **Query Parameters:**
  - `workspace_id` (UUID, optional): Filter by workspace (defaults to user's first workspace).
  - `status` (string, optional): `active` or `archived`.
  - `search` (string, optional): Search by project name or description.
- **Response (200 OK):**
  ```json
  [
    {
      "id": "19b5fc77-c91f-4b05-9f5b-1c5c643724c1",
      "workspace_id": "e44d3204-c3bf-4786-9a3b-28f0927df4d6",
      "name": "Backend Service",
      "slug": "backend-service",
      "description": "Core RESTful APIs",
      "status": "active",
      "task_count": 12,
      "created_by": "c1f10815-9922-4869-923f-42ee93c830ef",
      "created_at": "2026-10-19T12:00:00Z",
      "updated_at": "2026-10-19T12:00:00Z",
      "archived_at": null
    }
  ]
  ```

#### `POST /api/v1/projects`
Creates a project within the workspace. Slugs are unique within each workspace.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Request Body:**
  ```json
  {
    "workspace_id": "e44d3204-c3bf-4786-9a3b-28f0927df4d6",
    "name": "Backend Service",
    "slug": "backend-service",
    "description": "Core RESTful APIs"
  }
  ```
- **Response (201 Created):** `ProjectResponse`

#### `GET /api/v1/projects/{project_id}`
Retrieves a project by ID (scoped to authorized workspace). Returns 404 for unowned projects.

#### `PATCH /api/v1/projects/{project_id}`
Updates project name, slug, or description.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Request Body:** `{"name": "Updated Backend Service", "description": "New description"}`
- **Response (200 OK):** `ProjectResponse`

#### `POST /api/v1/projects/{project_id}/archive`
Archives a project and sets `archived_at`. Archived projects cannot receive new tasks.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Response (200 OK):** `ProjectResponse`

#### `POST /api/v1/projects/{project_id}/restore`
Restores an archived project back to `active`.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Response (200 OK):** `ProjectResponse`

---

### 3.4 Tasks (`/api/v1/tasks` & `/api/v1/projects/{project_id}/tasks`)

#### `GET /api/v1/projects/{project_id}/tasks`
Retrieves paginated tasks belonging to a specific project.
- **Query Parameters:**
  - `status` (`backlog`, `todo`, `in_progress`, `in_review`, `done`, `cancelled`)
  - `priority` (`low`, `medium`, `high`, `critical`)
  - `search` (string)
  - `limit` (integer, default 50, max 100)
  - `offset` (integer, default 0)
  - `sort_by` (`created_at`, `updated_at`, `priority`, `due_at`)
  - `sort_order` (`asc`, `desc`)
- **Response (200 OK):**
  ```json
  {
    "items": [
      {
        "id": "7b8e19b5-c91f-4b05-9f5b-1c5c643724c1",
        "workspace_id": "e44d3204-c3bf-4786-9a3b-28f0927df4d6",
        "project_id": "19b5fc77-c91f-4b05-9f5b-1c5c643724c1",
        "title": "Fix session invalidation on logout",
        "description": "Ensure redis and postgres sessions are revoked immediately.",
        "status": "in_progress",
        "priority": "high",
        "task_type": "bug",
        "created_by": "c1f10815-9922-4869-923f-42ee93c830ef",
        "assignee_id": "c1f10815-9922-4869-923f-42ee93c830ef",
        "due_at": null,
        "completed_at": null,
        "archived_at": null,
        "created_at": "2026-10-19T13:00:00Z",
        "updated_at": "2026-10-19T13:30:00Z"
      }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0
  }
  ```

#### `POST /api/v1/projects/{project_id}/tasks`
Creates a task under a project.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Restrictions:** Cannot create tasks in archived projects; assignee must belong to the workspace.
- **Request Body:**
  ```json
  {
    "title": "Fix session invalidation on logout",
    "description": "Detailed specs...",
    "status": "todo",
    "priority": "high",
    "task_type": "bug",
    "assignee_id": null,
    "due_at": null
  }
  ```
- **Response (201 Created):** `TaskResponse`

#### `GET /api/v1/tasks`
Workspace-wide task search, filtering, and pagination.
- **Query Parameters:** `workspace_id`, `status`, `priority`, `assignee_id`, `search`, `limit`, `offset`, `sort_by`, `sort_order`.

#### `GET /api/v1/tasks/{task_id}`
Retrieves task details (returns 404 for unowned workspace resources).

#### `PATCH /api/v1/tasks/{task_id}`
Partially updates a task.
- Validated status transitions update `completed_at` (set on `done`, cleared when transitioning away from `done`).
- Cross-workspace project reassignment or assignment to non-members is strictly forbidden.

#### `POST /api/v1/tasks/{task_id}/archive`
Archives a task and sets `archived_at`.

#### `POST /api/v1/tasks/{task_id}/restore`
Restores an archived task.

---

### 3.5 Dashboard (`/api/v1/dashboard`)

#### `GET /api/v1/dashboard/summary`
Calculates real-time, tenant-isolated counts for workspace dashboard.
- **Query Parameters:** `workspace_id` (UUID, required)
- **Response (200 OK):**
  ```json
  {
    "workspace_id": "e44d3204-c3bf-4786-9a3b-28f0927df4d6",
    "total_projects": 3,
    "open_tasks": 7,
    "in_progress_tasks": 2,
    "completed_tasks": 15,
    "active_agent_runs": null
  }
  ```

#### `GET /api/v1/dashboard/recent-activity`
Returns workspace audit trail logs in reverse chronological order.
- **Query Parameters:** `workspace_id` (UUID, required), `limit` (integer, default 10)
- **Response (200 OK):**
  ```json
  [
    {
      "id": "c71e2289-42b7-4c7b-8326-8c4d2d4d9c79",
      "workspace_id": "e44d3204-c3bf-4786-9a3b-28f0927df4d6",
      "actor_id": "c1f10815-9922-4869-923f-42ee93c830ef",
      "event_type": "task_completed",
      "resource_type": "task",
      "resource_id": "7b8e19b5-c91f-4b05-9f5b-1c5c643724c1",
      "metadata": {
        "title": "Fix session invalidation on logout"
      },
      "created_at": "2026-10-19T14:15:00Z"
    }
  ]
  ```

---

### 3.6 GitHub App Integrations (`/api/v1/integrations/github`)

#### `GET /api/v1/integrations/github/status`
Returns safe metadata describing whether the GitHub App is configured in environment and linked to the workspace.
- **Query Parameters:** `workspace_id` (UUID, required)
- **Response (200 OK):**
  ```json
  {
    "is_configured": true,
    "is_connected": true,
    "installation_id": 554433,
    "account_login": "acme-corp",
    "account_type": "Organization",
    "account_avatar_url": "https://avatars.githubusercontent.com/u/1234",
    "status": "active",
    "total_repositories": 14,
    "selected_repositories": 3,
    "last_synced_at": "2026-10-19T14:45:00Z",
    "app_slug": "mysde-ai-engineer"
  }
  ```

#### `GET /api/v1/integrations/github/install`
Generates a short-lived (15 min), single-use cryptographic state token bound to the current user and workspace, and returns the installation URL.
- **Requires:** Workspace `owner` or `admin` role.
- **Response (200 OK):**
  ```json
  {
    "install_url": "https://github.com/apps/mysde-ai-engineer/installations/new?state=sec_token_...",
    "state": "sec_token_..."
  }
  ```

#### `GET /api/v1/integrations/github/callback`
GitHub redirect target. Validates single-use state token, verifies user binding, prevents cross-workspace installation reuse, stores installation metadata, synchronizes initial repositories, and redirects the browser back to `/repositories?installed=true`.

#### `GET /api/v1/integrations/github/repositories`
Lists synchronized GitHub repositories for the workspace.
- **Query Parameters:** `workspace_id` (UUID), `search` (string), `is_selected` (boolean), `limit` (int), `offset` (int).
- **Response (200 OK):**
  ```json
  {
    "items": [
      {
        "id": "2195f2a1-cf8d-4cb0-910a-3a13d04344e1",
        "workspace_id": "e44d3204-c3bf-4786-9a3b-28f0927df4d6",
        "installation_id": "4020a1f0-2911-4770-87b6-c9569fa5b5dc",
        "github_repo_id": 1029384,
        "owner_login": "acme-corp",
        "name": "core-backend",
        "full_name": "acme-corp/core-backend",
        "default_branch": "main",
        "is_private": true,
        "is_archived": false,
        "is_selected": true,
        "last_synced_at": "2026-10-19T14:45:00Z",
        "created_at": "2026-10-19T14:45:00Z",
        "updated_at": "2026-10-19T14:45:00Z"
      }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0
  }
  ```

#### `POST /api/v1/integrations/github/repositories/sync`
Manually pulls fresh repository metadata from the GitHub App API for the workspace.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Requires:** Workspace `owner` or `admin` role.
- **Response (200 OK):** `{"message": "Repositories synchronized successfully", "synced_count": 14}`

#### `PATCH /api/v1/integrations/github/repositories/{repository_id}`
Selects or deselects a repository for active use within MySDE workspace projects.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Requires:** Workspace `owner` or `admin` role.
- **Request Body:** `{"is_selected": true}`
- **Response (200 OK):** `GitHubRepositoryResponse`

#### `POST /api/v1/integrations/github/disconnect`
Disconnects the GitHub App installation from the workspace and marks it `uninstalled`.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Requires:** Workspace `owner` or `admin` role.
- **Response (200 OK):** `{"message": "GitHub App disconnected successfully"}`

#### `POST /api/v1/integrations/github/webhook`
Public webhook endpoint for GitHub events.
- **Headers:** `X-Hub-Signature-256`, `X-GitHub-Delivery`, `X-GitHub-Event`.
- **Security:** Verified with constant-time HMAC SHA-256 signature using `GITHUB_WEBHOOK_SECRET`.
- **Idempotency:** Tracked in `github_webhook_deliveries` using `X-GitHub-Delivery`.
- **Supported Events:** `installation` (`created`, `deleted`, `suspend`, `unsuspend`) and `installation_repositories` (`added`, `removed`).

---

### 3.7 Code RAG (`/api/v1/rag`)

#### `POST /api/v1/rag/repositories/{repository_id}/index`
Enqueues an asynchronous repository code indexing run to parse, filter, chunk, embed, and index source code into Code RAG.
- **Query Params:** `workspace_id=<workspace_uuid>`
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Requires:** Workspace member.
- **Request Body:**
  ```json
  {
    "target_ref": "main",
    "force_reindex": false
  }
  ```
- **Response (202 Accepted):** `IndexingJobResponse`

#### `GET /api/v1/rag/repositories/{repository_id}/index/status`
Retrieves status, statistics, and exclusion breakdown for the most recent indexing job.
- **Query Params:** `workspace_id=<workspace_uuid>`
- **Response (200 OK):** `IndexingJobResponse | null`
  ```json
  {
    "id": "e4b9...-uuid",
    "repository_id": "...",
    "target_ref": "main",
    "commit_sha": "7a3f8902c...",
    "status": "completed",
    "files_discovered": 142,
    "files_accepted": 85,
    "files_excluded": 57,
    "files_failed": 0,
    "chunks_count": 312,
    "embedding_provider": "fake",
    "embedding_model": "mock-embed-384",
    "embedding_dimensions": 384,
    "exclusions_summary": {
      "secret_file": 2,
      "binary_or_compiled": 18,
      "lockfile_or_minified": 4,
      "directory_excluded": 33
    },
    "started_at": "2026-10-20T13:40:00Z",
    "completed_at": "2026-10-20T13:40:08Z"
  }
  ```

#### `GET /api/v1/rag/repositories/{repository_id}/index/jobs`
Lists recent indexing runs for the repository.
- **Query Params:** `workspace_id=<workspace_uuid>&limit=10`
- **Response (200 OK):** `list[IndexingJobResponse]`

#### `POST /api/v1/rag/repositories/{repository_id}/retrieve`
Performs semantic vector search with lexical re-ranking over indexed repository code chunks.
- **Query Params:** `workspace_id=<workspace_uuid>`
- **Request Body:**
  ```json
  {
    "query": "Where is user password verified with argon2?",
    "top_k": 5,
    "language": "python",
    "file_path_pattern": "src/*"
  }
  ```
- **Response (200 OK):** `RetrievalResultResponse`
  ```json
  {
    "repository_id": "...",
    "repository_name": "acme-corp/web-service",
    "commit_sha": "7a3f8902c...",
    "is_indexed": true,
    "results": [
      {
        "chunk_id": "...",
        "file_path": "src/core/security.py",
        "file_language": "python",
        "start_line": 12,
        "end_line": 28,
        "symbol_name": "verify_password",
        "symbol_type": "function",
        "chunk_content": "def verify_password(hash: str, password: str) -> bool: ...",
        "score": 0.9425,
        "commit_sha": "7a3f8902c...",
        "github_url": "https://github.com/acme-corp/web-service/blob/7a3f8902c/src/core/security.py#L12-L28"
      }
    ],
    "total_results": 1
  }
  ```

#### `GET /api/v1/rag/tasks/{task_id}/retrieve-context`
Automatically discovers relevant repository code context for an engineering task using its title, description, and connected repository.
- **Query Params:** `top_k=5`
- **Response (200 OK):** `RetrievalResultResponse`

---

### 3.9 Planning & LangGraph Agent (`/api/v1/planning` & `/api/v1/tasks/{task_id}/plan`)

#### `POST /api/v1/tasks/{task_id}/plan`
Triggers an asynchronous LangGraph planning run for an authorized task.
- **Query Params:** `workspace_id=<UUID>` (optional, auto-resolved from task)
- **Request Body:**
  ```json
  {
    "force_new": false
  }
  ```
- **Response (202 Accepted):** `PlanningRunResponse`
- **Error Codes:** 400 Bad Request (concurrent run in progress), 404 Not Found (task not found / unauthorized)

#### `GET /api/v1/tasks/{task_id}/plan`
Retrieves the latest active implementation plan or active planning run for a task.
- **Response (200 OK):**
  ```json
  {
    "task_id": "...",
    "active_run": { "id": "...", "status": "completed", ... },
    "latest_plan": { "id": "...", "plan_data": { ... } }
  }
  ```

#### `GET /api/v1/tasks/{task_id}/plans`
Lists historical implementation plans for a task with pagination.
- **Query Params:** `limit=10`, `offset=0`
- **Response (200 OK):** Array of `ImplementationPlanResponse`

#### `GET /api/v1/planning/runs/{run_id}`
Retrieves the execution status and diagnostics of a planning run.
- **Response (200 OK):** `PlanningRunResponse`

#### `POST /api/v1/planning/runs/{run_id}/cancel`
Cancels an active or queued planning run.
- **Response (200 OK):** `PlanningRunResponse` with `status: "cancelled"`

#### `GET /api/v1/planning/plans/{plan_id}`
Retrieves a specific validated implementation plan by UUID.
- **Response (200 OK):** `ImplementationPlanResponse`

---

### 3.10 Isolated Execution & Verification (`/api/v1/execution` & `/api/v1/tasks/{task_id}/execution`)

#### `POST /api/v1/tasks/{task_id}/execution`
Initiates a new execution run to prepare a snapshot and generate a validated patch proposal.
- **Request Body:**
  ```json
  {
    "plan_id": "<UUID | null>",
    "verification_commands": ["syntax_check", "pytest"]
  }
  ```
- **Response (201 Created):** `ExecutionRunResponse` with `status: "awaiting_patch_approval"`.

#### `GET /api/v1/tasks/{task_id}/executions`
Lists prior execution runs for an authorized task with pagination.
- **Query Params:** `limit=10`, `offset=0`
- **Response (200 OK):** Array of `ExecutionRunResponse`.

#### `GET /api/v1/execution/runs/{run_id}`
Retrieves run status, patch metadata, and sandbox verification results.
- **Response (200 OK):** `ExecutionRunResponse`.

#### `GET /api/v1/execution/runs/{run_id}/patch`
Retrieves the proposed patch artifact and raw unified git diff.
- **Response (200 OK):** `PatchArtifactResponse`.

#### `POST /api/v1/execution/runs/{run_id}/approve`
Explicitly approves the proposed patch and triggers sandboxed application and verification checks.
- **Request Body:**
  ```json
  {
    "run_checks": true,
    "verification_commands": ["syntax_check", "pytest"]
  }
  ```
- **Response (200 OK):** `ExecutionRunResponse` with updated status, cleanup status, and verification evidence.

#### `POST /api/v1/execution/runs/{run_id}/reject`
Rejects the proposed patch and marks the execution run cancelled.
- **Request Body:**
  ```json
  {
    "reason": "Unwanted file modified"
  }
  ```
- **Response (200 OK):** `ExecutionRunResponse` with `status: "cancelled"`.

#### `POST /api/v1/execution/runs/{run_id}/cancel`
Requests cancellation of an ongoing execution run.
- **Response (200 OK):** `ExecutionRunResponse` with `status: "cancelled"`.

---

### 3.12 Bounded AI Repair Loops (`/api/v1/repair` & `/api/v1/executions/{run_id}/repair`)

#### `POST /api/v1/executions/{run_id}/repair`
Initiates a bounded repair run for an eligible failed execution run.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Requires:** Workspace member.
- **Request Body:**
  ```json
  {
    "rerun_all_checks": false
  }
  ```
- **Response (201 Created):** `RepairRunResponse`
- **Error Codes:**
  - `400 Bad Request`: Execution run is not eligible (not failed or has no failed checks).
  - `404 Not Found`: Execution run not found or unauthorized.
  - `409 Conflict`: A repair run is already in progress for this execution.

#### `GET /api/v1/executions/{run_id}/repair`
Retrieves the latest repair run and attempt history for an execution run.
- **Response (200 OK):** `RepairRunResponse | null`

#### `GET /api/v1/repairs/{repair_id}`
Retrieves a repair run by its UUID with all ordered repair attempts.
- **Response (200 OK):** `RepairRunResponse`

#### `POST /api/v1/repairs/{repair_id}/cancel`
Requests cooperative cancellation of an active repair run.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Response (200 OK):** `RepairRunResponse` with `status: "cancelled"`

#### `GET /api/v1/repairs/{repair_id}/summary`
Retrieves a high-level summary of the repair run, outcome, and verification counts.
- **Response (200 OK):** `RepairSummaryResponse`
  ```json
  {
    "repair_run_id": "...",
    "execution_run_id": "...",
    "task_id": "...",
    "status": "completed",
    "final_outcome": "verified_success",
    "attempts_count": 1,
    "max_attempts": 3,
    "all_checks_passed": true,
    "verification_passed_count": 2,
    "verification_failed_count": 0,
    "verification_skipped_count": 0,
    "completed_at": "2026-10-21T14:40:00Z"
  }
  ```

---

---

### 3.13 Git Branch, Commit, and Pull Request Publishing (`/api/v1/executions/{run_id}/publish`)

#### `GET /api/v1/executions/{run_id}/publish/precheck`
Evaluates all pre-conditions before publishing: execution status, verification results, human approval status, patch freshness, base branch staleness, and existing blockers.
- **Query Parameters:** `workspace_id=<uuid>`
- **Response (200 OK):** `PublishingPrecheckResponse`
  ```json
  {
    "can_publish": true,
    "is_approved": true,
    "approved_patch_hash": "a1b2c3...",
    "current_patch_hash": "a1b2c3...",
    "is_patch_stale": false,
    "verification_passed": true,
    "passed_checks_count": 2,
    "failed_checks_count": 0,
    "execution_base_sha": "0123456789...",
    "remote_base_sha": "0123456789...",
    "is_base_stale": false,
    "blockers": [],
    "repository_full_name": "owner/repo",
    "default_branch": "main"
  }
  ```

#### `POST /api/v1/executions/{run_id}/publish/approve`
Explicitly binds human approval to the exact patch hash proposal. Validates file safety (rejects `.env`, credentials, traversal) and confirms verification tests passed.
- **Query Parameters:** `workspace_id=<uuid>`
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Request Body:**
  ```json
  {
    "patch_hash": "a1b2c3..."
  }
  ```
- **Response (200 OK):** `PublishingRunResponse` with `status: "approved"`

#### `POST /api/v1/executions/{run_id}/publish`
Publishes the approved changes to a collision-resistant branch (`mysde/task-<task_id[:8]>-<slug>`), creates an immutable Git tree and commit, pushes the ref, and opens a GitHub Pull Request with verification evidence. Idempotent on repeated calls.
- **Query Parameters:** `workspace_id=<uuid>`
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Request Body:**
  ```json
  {
    "base_branch": null,
    "pr_title": null,
    "pr_body": null
  }
  ```
- **Response (201 Created):** `PublishingRunResponse`
  ```json
  {
    "id": "...",
    "execution_run_id": "...",
    "task_id": "...",
    "repository_id": "...",
    "status": "completed",
    "base_branch": "main",
    "head_branch": "mysde/task-96aeac9c-fix-calculator-discount",
    "head_commit_sha": "e9f01a...",
    "pr_number": 42,
    "pr_url": "https://github.com/owner/repo/pull/42",
    "pr_title": "[BUG] Fix calculate_discount edge case",
    "pr_state": "open",
    "published_at": "2026-10-21T18:00:00Z"
  }
  ```

#### `GET /api/v1/executions/{run_id}/publish`
Retrieves the latest publishing run status, commit SHA, and PR link for an execution.
- **Query Parameters:** `workspace_id=<uuid>`
- **Response (200 OK):** `PublishingRunResponse`

#### `POST /api/v1/publishing/{publishing_id}/retry`
Safely retries a failed or interrupted publishing workflow.
- **Query Parameters:** `workspace_id=<uuid>`
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Response (200 OK):** `PublishingRunResponse`

---

### 3.14 System Diagnostics
- `GET /health`: Liveness probe (`{"status": "ok", ...}`).
- `GET /ready`: Readiness probe checking database connectivity (`SELECT 1`). Database failure messages and connection strings are strictly redacted from HTTP response payloads to prevent credential leakage.

---

### 3.15 Observability, Metrics & Reliability Recovery (Phase 10)

#### `GET /api/v1/observability/runs/{run_id}/trace`
Retrieves an end-to-end timeline trace of an agent run from planning to publishing.
- **Query Parameters:** `workspace_id=<uuid>` (required)
- **Response (200 OK):** `RunTraceResponse`
  - Returns `execution_run_id`, `task_id`, `status`, `duration_seconds`, sandbox runtime, honest `model_usage` ("unavailable" when not supplied by upstream provider), and chronological `timeline` of stage transitions.
  - Redacts sensitive credentials, private keys, and tokens.

#### `GET /api/v1/observability/metrics`
Returns aggregate workspace reliability, duration, and error category metrics with a clearly defined denominator.
- **Query Parameters:**
  - `workspace_id=<uuid>` (required)
  - `time_window_days=<int>` (optional, default: 30)
- **Response (200 OK):** `ObservabilityMetricsResponse`
  - Denominator for `success_rate_percent` is explicitly defined as `(successful_runs / total_terminal_runs) * 100` where terminal runs include `completed`, `failed`, `cancelled`, and `timed_out`.
  - Includes average sandbox durations, repair resolution counts, and failure classification buckets.

#### `GET /api/v1/observability/runs`
Returns filtered workspace agent execution runs.
- **Query Parameters:**
  - `workspace_id=<uuid>` (required)
  - `status=<str>` (optional: completed, failed, running, timed_out, cancelled)
  - `date_from=<iso8601>` (optional)
  - `date_to=<iso8601>` (optional)
  - `limit=<int>` (optional, max: 100)
- **Response (200 OK):** `list[ObservabilityRunSummary]`

#### `POST /api/v1/observability/recover-stale`
Audits and safely transitions abandoned or interrupted execution, repair, and publishing runs left in active states past a configurable timeout into terminal states (`timed_out` or `failed`).
- **Query Parameters:**
  - `workspace_id=<uuid>` (required)
  - `timeout_minutes=<int>` (optional, default: 15)
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Response (200 OK):** `RecoverStaleRunsResponse`
  ```json
  {
    "recovered_executions": 1,
    "recovered_repairs": 0,
    "recovered_publishing": 0,

---

### 3.15 SaaS Billing, Subscriptions, and Usage Metering (`/api/v1/billing`)

#### `GET /api/v1/billing/plans`
Public endpoint returning all active subscription plan tiers (`free`, `pro`, `team`) along with quotas, concurrency limits, pricing in INR/USD cents, and feature entitlements.
- **Response (200 OK):** `list[PlanResponse]`

#### `GET /api/v1/billing/subscription`
Returns active subscription status and live quota consumption for the specified workspace.
- **Query Parameters:** `workspace_id=<uuid>` (required)
- **Response (200 OK):** `SubscriptionResponse`
  - Current plan and standing (`active`, `past_due`, `canceled`)
  - Billing period boundaries (`current_period_start`, `current_period_end`)
  - Live meters (`agent_runs_used`, `agent_runs_limit`, `repair_runs_used`, `repair_runs_limit`, `tokens_used`, `tokens_limit`, `parallel_runs_active`, `max_parallel_runs`)

#### `POST /api/v1/billing/checkout`
Initiates a checkout session or plan upgrade flow for the workspace. Requires `owner` or `admin` role.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Query Parameters:** `workspace_id=<uuid>` (required)
- **Request Body:**
  ```json
  {
    "plan_code": "pro",
    "currency": "INR"
  }
  ```
- **Response (200 OK):** `CheckoutResponse` containing provider session ID and checkout URL.

#### `POST /api/v1/billing/cancel`
Schedules workspace subscription cancellation at the end of the current billing cycle.
- **Headers:** `X-CSRF-Token: <csrf_token>`
- **Query Parameters:** `workspace_id=<uuid>` (required)
- **Response (200 OK):** `CancelSubscriptionResponse`

#### `GET /api/v1/billing/usage`
Auditable tenant-scoped ledger history of billable events.
- **Query Parameters:** `workspace_id=<uuid>` (required), `limit=<int>` (default: 50)
- **Response (200 OK):** `list[UsageLedgerItemResponse]`

#### `POST /api/v1/billing/webhooks/{provider}`
Public webhook receiver for provider notifications (`mock`, `razorpay`). Verifies HMAC signatures over raw request body before processing idempotently via `processed_webhook_events`.
- **Headers:** `X-Razorpay-Signature: <hex_sig>` (or `X-Mock-Signature: <hex_sig>`)
- **Response (200 OK):** `{"status": "success" | "already_processed", "event_id": "<id>"}`
