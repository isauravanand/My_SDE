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

### 3.7 System Diagnostics
- `GET /health`: Liveness probe (`{"status": "ok", ...}`).
- `GET /ready`: Readiness probe checking database connectivity (`SELECT 1`).
