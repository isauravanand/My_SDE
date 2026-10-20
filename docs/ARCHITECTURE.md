# MySDE — Architecture Design Document

**Document Version:** 3.0.0  
**Phase:** Phase 3 (Projects, Tasks, and API-Connected Dashboard)  
**System Classification:** Modular Monolith SaaS Architecture  

---

## 1. System Architecture Overview

MySDE uses a **Modular Monolith** architecture. All core SaaS functionality, domain services, and database access are maintained within a unified backend service, while compute-intensive agent runs, test executions, and sandbox operations are dispatched asynchronously to dedicated worker processes and containerized sandboxes.

```mermaid
graph TD
    User([Developer / Browser]) -->|HTTPS| ViteSPA[Vite React SPA]
    ViteSPA -->|REST API with Cookies & CSRF| API[FastAPI Backend Core]

    subgraph Backend Core [FastAPI Modular Monolith]
        Router[API v1 Router] --> Deps[Auth & Workspace Guards]
        Deps --> Services[Domain Services]
        Services --> DB[(PostgreSQL Database)]
        Services --> Act[Activity Logger]
    end

    subgraph Domain Services
        ProjSvc[ProjectService]
        TaskSvc[TaskService]
        DashSvc[DashboardService]
        ActSvc[ActivityService]
        GhSvc[GitHubService]
        GhHook[GitHubWebhookHandler]
        GhClient[GitHubApiClient]
    end
```

---

## 2. Frontend / Backend Boundaries

### 2.1 Backend Responsibilities
- **Authentication & Multi-Tenant Authorization:** Enforcing workspace-level access control.
- **Data Persistence:** Storing metadata, projects, tasks, audit trails, and user configurations in PostgreSQL.
- **Domain Services:**
  - `ProjectService`: Project CRUD, slug generation, archiving, task count aggregation.
  - `TaskService`: Task lifecycle management, validation of status transitions (`completed_at`), archived project checks, workspace assignee validation.
  - `DashboardService`: Aggregated metrics for active projects, open tasks, in-progress tasks, and completed tasks.
  - `ActivityService`: Audit event emission without leaking credentials.
  - `GitHubService`: GitHub App installations, repository metadata syncing, and workspace project binding.
  - `GitHubWebhookHandler`: HMAC SHA-256 signature verification and idempotent event ingestion.
  - `GitHubApiClient`: RS256 JWT signing, short-lived installation access tokens, and GitHub REST API integration.

### 2.2 Frontend Responsibilities
- **Presentation & State Management:** Single Page Application (SPA) built with React 18, Vite, and TanStack Query v5.
- **Tenant-Scoped Data Caching:** TanStack Query keys are explicitly partitioned by `activeWorkspace.id` (e.g. `['projects', workspaceId]`, `['tasks', workspaceId]`, `['dashboard', 'summary', workspaceId]`).
- **Workspace Switching:** Seamlessly invalidates stale queries and synchronizes active workspace context across all views.
- **Zero Secrets Rule:** Frontend never receives or stores raw repository tokens, GitHub App private keys, or LLM credentials.

---

## 3. API Architecture & Layering

The backend enforces strict separation of concerns through architectural layering:

```text
HTTP Request
     │
     ▼
[Endpoints / Controllers]  ── (Thin layer: validates DTOs, parses headers, returns responses)
     │
     ▼
[FastAPI Dependencies]     ── (Resolves session, verifies workspace membership, validates permissions)
     │
     ▼
[Domain Services]          ── (Business logic, status state transitions, transactions, activity logs)
     │
     ▼
[Database / Models]        ── (PostgreSQL schema entities via SQLAlchemy 2.0 ORM)
```

- **Endpoints (`app/api/v1/endpoints/`):** Thin route handlers that validate request payloads using Pydantic v2 schemas and delegate directly to domain services.
- **Dependencies (`app/api/deps.py`):**
  - `get_current_user`: Authenticates session from `mysde_session` cookie.
  - `resolve_project_workspace`: Fetches project and verifies active membership in owning workspace.
  - `resolve_task_workspace`: Fetches task and verifies active membership in owning workspace.
- **Domain Services (`app/services/`):** Houses business rules, state machines, and transactional coordination.
- **Models (`app/models/`):** SQLAlchemy ORM models with cross-dialect support (`app.db.base.GUID` for UUIDs).

---

## 4. Database Access Strategy

1. **SQLAlchemy 2.x:** Modern 2.0 style syntax (`select()`, `scalars()`) with strict typing.
2. **Session Lifecycle:** FastAPI dependency injection (`get_db`) yields database sessions with deterministic scope.
3. **Connection Pooling:** Configured with `pool_pre_ping=True`, conservative `pool_size` (10-20), and `max_overflow` (10).
4. **Migration Strategy:** Forward-only Alembic migrations (`20261019_0001`, `20261019_0002`).

---

## 5. Security & Authorization

- **Multi-Tenant Isolation:** Every task and project is bound to a `workspace_id`. Cross-workspace reads, mutations, or project reassignments return HTTP 404 to prevent resource enumeration.
- **Archival Protection:** Archived projects cannot receive new tasks until explicitly restored.
- **Assignee Authorization:** Tasks can only be assigned to valid members of the owning workspace.
- **CSRF Protection:** State-changing methods require `X-CSRF-Token` matching the client's `mysde_csrf` cookie.
