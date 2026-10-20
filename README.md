# MySDE — AI Software Engineering SaaS Platform

**MySDE** is an autonomous AI software engineer designed to turn GitHub issues into verified, production-grade pull requests. It executes code changes in isolated sandboxes, runs project test suites, engages in bounded repair loops, and presents evidence dossiers for explicit human approval before publishing.

---

## 1. Project Evolution & Phase Status

- **Phase 0 & 1 (Foundation):** Core FastAPI architecture, React 18 / Vite 6 frontend, Graphite & Acid Lime design system, health & readiness diagnostics, structured logging, and CI configuration.
- **Phase 2 (Auth & Multi-Tenancy):** Argon2id password encryption, server-side opaque sessions in PostgreSQL, HttpOnly session cookies, CSRF protection, and workspace-level isolation.
- **Phase 3 (Projects, Tasks & Dashboard):** PostgreSQL models & Alembic migrations for `Project`, `Task`, `ActivityLog`, multi-tenant CRUD, status transitions, pagination, and real-time dashboard.
- **Phase 4 (GitHub App Integration - CURRENT):**
  - **Data Layer:** PostgreSQL models & migration `20261019_0003` for `GitHubInstallation`, `GitHubRepository`, `GitHubOAuthState`, `GitHubWebhookDelivery`, and project/task repository bindings.
  - **Security & Authorization:** RS256 JWT signing, short-lived installation tokens in memory, cryptographically secure single-use state tokens, HMAC SHA-256 signature verification, and delivery deduplication.
  - **Backend APIs:** Integration status, installation authorization flow, secure callback handling, repository syncing/selection, disconnection, and webhook ingestion.
  - **Frontend UI:** Interactive Repositories dashboard (`/repositories`) with connection status, install flow, live repository search/filter/selection, manual sync, disconnect modal, and GitHub App setup guide.

---

## 2. Documentation Index

The complete architectural, API, and security specifications are located in [`docs/`](file:///d:/My_SDE/docs):

- **[Product Requirements Document (PRD)](file:///d:/My_SDE/docs/PRD.md)** — Vision, core user journeys, MVP scope, non-goals, and functional specifications.
- **[System Architecture](file:///d:/My_SDE/docs/ARCHITECTURE.md)** — Modular monolith design, frontend/backend boundaries, domain services, and TanStack Query state architecture.
- **[Database Design & Schema](file:///d:/My_SDE/docs/DATABASE_DESIGN.md)** — Multi-tenant schema specifications (Workspaces, Memberships, Projects, Tasks, Activity Logs).
- **[Security Specification](file:///d:/My_SDE/docs/SECURITY.md)** — Argon2id, CSRF defenses, cross-workspace security boundaries, and authorization safeguards.
- **[API Specification](file:///d:/My_SDE/docs/API.md)** — Full RESTful endpoints for Auth, Workspaces, Projects, Tasks, and Dashboard.

---

## 3. Project Structure

```text
D:\My_SDE\
├── backend\
│   ├── app\
│   │   ├── main.py                  # FastAPI application entrypoint & lifespan
│   │   ├── api\v1\
│   │   │   ├── router.py            # Mounted API v1 router
│   │   │   └── endpoints\           # Auth, Workspaces, Projects, Tasks, Dashboard, Health
│   │   ├── core\
│   │   │   ├── config.py            # Pydantic v2 settings & environment validation
│   │   │   ├── logging.py           # Structured logging with secret redaction
│   │   │   └── security.py          # Security headers & constant-time helpers
│   │   ├── db\
│   │   │   ├── base.py              # SQLAlchemy 2.0 Base & UUID/Timestamp mixins
│   │   │   └── session.py           # Engine lifecycle, session factory & DB probe
│   │   ├── models\                  # User, Workspace, Session, Project, Task, Activity
│   │   ├── schemas\                 # Pydantic DTOs for request/response serialization
│   │   └── services\                # ProjectService, TaskService, DashboardService, ActivityService
│   ├── alembic\                     # Database migration scripts (20261019_0001, 20261019_0002)
│   ├── tests\                       # Integration & security test suites (37 passing tests)
│   ├── pyproject.toml               # uv & package dependencies
│   ├── alembic.ini                  # Alembic migration configuration
│   ├── .env.example                 # Example backend environment variables
│   └── README.md
├── frontend\
│   ├── src\
│   │   ├── app\                     # App container, router, and query client
│   │   ├── components\              # Layout, Sidebar, Header, EmptyState, Badges
│   │   ├── features\
│   │   │   ├── auth\                # AuthContext, ProtectedRoute
│   │   │   └── dashboard\           # Metric cards, diagnostics banner, activity feed, recent tasks
│   │   ├── lib\                     # Centralized API client & utilities
│   │   └── pages\                   # Dashboard, Projects, ProjectDetail, Tasks, Auth pages
│   ├── package.json                 # Node dependencies
│   ├── vite.config.js               # Vite bundler configuration
│   ├── tailwind.config.js           # Graphite & Acid Lime design system tokens
│   ├── .env.example                 # Example frontend environment variables
│   └── README.md
├── docs\                            # Architectural and product documentation
├── .gitignore                       # Root ignore rules
└── README.md
```

---

## 4. Getting Started (Windows PowerShell)

### 4.1 Backend Setup
```powershell
# Navigate to backend
Set-Location D:\My_SDE\backend

# Initialize environment
Copy-Item .env.example .env

# Install dependencies into virtual environment
uv sync

# Run database migrations
uv run alembic upgrade head

# Run tests & lint checks
uv run ruff check .
uv run pytest -v

# Start FastAPI development server
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Backend API will be live at `http://127.0.0.1:8000` with interactive Swagger docs at `/docs`.

### 4.2 Frontend Setup
```powershell
# In a separate terminal, navigate to frontend
Set-Location D:\My_SDE\frontend

# Initialize environment
Copy-Item .env.example .env

# Install dependencies
npm install

# Build for production verification
npm run build

# Start development server
npm run dev
```
Frontend dashboard will launch at `http://localhost:5173`.
