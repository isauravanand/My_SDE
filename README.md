# MySDE — Autonomous AI Software Engineering SaaS Platform

**MySDE** is an autonomous AI software engineer designed to turn GitHub issues into verified, production-grade pull requests. It analyzes codebases using semantic RAG, generates verifiable implementation plans, applies changes in isolated sandboxes, executes automated test suites, engages in bounded self-repair loops, and requests human review before publishing pull requests to GitHub.

---

## 1. System Architecture & Lifecycle

```text
GitHub Issue / Task
        │
        ▼
[1. Codebase RAG] ───► AST Chunking & Vector Search over Repo Snapshot
        │
        ▼
[2. Planning Agent] ──► LangGraph Orchestrator + Groq/OpenAI LLM ──► Plan Dossier
        │
        ▼ (Human Approval)
[3. Sandbox Execution] ► Mount Commit Snapshot ──► Generate Patch ──► Security Validator
        │
        ├──► Test Suite Passes ────────────────────────────┐
        │                                                  │
        └──► Test Suite Fails ──► [4. Bounded AI Repair] ─►┘
                                         │
                                         ▼ (Human Approval)
                               [5. Publish to GitHub]
                                         │
                                         ▼
                                Pull Request Created
```

---

## 2. Platform Phases & Capabilities

- **Phase 0 & 1 (Foundation):** FastAPI backend, React 18 / Vite 6 frontend, Graphite & Acid Lime design system, health & readiness diagnostics, structured JSON logging with secret redaction.
- **Phase 2 (Auth & Multi-Tenancy):** Argon2id password hashing, server-side opaque sessions in PostgreSQL, HttpOnly secure cookies, CSRF protection, and workspace-level isolation.
- **Phase 3 (Projects, Tasks & Dashboard):** Multi-tenant CRUD, status transitions, pagination, activity logging, and real-time dashboard metrics.
- **Phase 4 (GitHub App Integration):** RS256 JWT authentication, short-lived installation access tokens, HMAC SHA-256 webhook verification, repository syncing, and branch selection.
- **Phase 5 (Codebase RAG & Semantic Retrieval):** Recursive code chunking with language-aware separators, dense vector embeddings (OpenAI / Fake deterministic provider), metadata filtering, and ground-truth benchmark suite (**Recall@3: 100%, MRR: 0.9375**).
- **Phase 6 (Autonomous Planning Agent):** LangGraph cyclic workflow, Groq (`llama-3.3-70b-versatile` / `gpt-oss-120b`) and OpenAI LLM providers, evidence ID validation, and interactive `PlanViewerModal`.
- **Phase 7 (Isolated Sandbox & Code Execution):** Snapshot mounting, high-fidelity UI styling directives, Docker & mock execution sandboxes, command policy enforcement, strict unified diff validator, and `ExecutionModal`.
- **Phase 8 (Bounded Autonomous AI Repair Loops):** Categorizes test failures (syntax, assertion, infrastructure), generates targeted repair diffs, anti-cheating policy enforcement, and execution budget caps.
- **Phase 9 (Git Branch & PR Publishing):** Automated branch generation (`mysde/task-<id>`), immutable blob/tree/commit creation via GitHub App, conflict prechecks, and PR generation with full change summaries.
- **Phase 10 (Observability & Recovery):** Execution run traces, forensic stage timelines, time-windowed metrics, and automated background recovery for stale runs (`RunTraceModal`).
- **Phase 11 (SaaS Billing, Metering & Subscriptions):** Tiered subscription plans (Free, Pro, Team), Razorpay & mock payment providers, usage ledger, parallel concurrency limits, and `BillingPage`.

---

## 3. Documentation Index

The complete architectural, API, and security specifications are located in [`docs/`](docs/):

- **[Product Requirements Document (PRD)](docs/PRD.md)** — Vision, user journeys, MVP scope, and functional specifications.
- **[System Architecture](docs/ARCHITECTURE.md)** — Modular monolith design, frontend/backend boundaries, and TanStack Query state patterns.
- **[Database Design & Schema](docs/DATABASE_DESIGN.md)** — Multi-tenant schema specifications (Workspaces, Memberships, Projects, Tasks, RAG, Planning, Execution, Repair, Publishing, Billing).
- **[Security Specification](docs/SECURITY.md)** — Argon2id, CSRF defenses, cross-workspace security boundaries, and sandbox isolation.
- **[API Specification](docs/API.md)** — Full RESTful endpoints for Auth, Workspaces, Projects, Tasks, GitHub, RAG, Planning, Execution, Repair, Publishing, Observability, and Billing.

---

## 4. Repository Structure

```text
D:\My_SDE\
├── backend\
│   ├── app\
│   │   ├── main.py                  # FastAPI entrypoint & lifecycle management
│   │   ├── api\v1\
│   │   │   ├── router.py            # Central API v1 router
│   │   │   └── endpoints\           # Auth, Billing, RAG, Execution, Observability, Planning, Publishing, Repair
│   │   ├── billing\                 # Razorpay provider, mock provider, factory
│   │   ├── core\                    # Settings, structured logging, security headers
│   │   ├── db\                      # Session factory, Base model, GUID type
│   │   ├── execution\               # Sandbox runners (Docker/Mock), patch generator, validator, snapshot
│   │   ├── models\                  # User, Workspace, Task, RAG, Planning, Execution, Repair, Publishing, Billing
│   │   ├── planning\                # LangGraph planning agent, LLM adapters (Groq, OpenAI, Mock), prompts
│   │   ├── rag\                     # Chunking, filtering, vector embeddings, ingestion
│   │   ├── schemas\                 # Pydantic v2 DTOs for request/response serialization
│   │   └── services\                # Domain business logic services
│   ├── alembic\                     # Forward-only database migration scripts (0001 to 0009)
│   ├── tests\                       # Comprehensive test suites (220 passing tests)
│   ├── pyproject.toml               # Python dependencies & tool config (uv, ruff, pytest)
│   └── README.md
├── frontend\
│   ├── src\
│   │   ├── app\                     # App container, router, and query client
│   │   ├── components\              # UI components, layout, ExecutionModal, PlanViewerModal, RunTraceModal
│   │   ├── lib\                     # Centralized API client (api.js) and helpers
│   │   └── pages\                   # Dashboard, Projects, Tasks, Repositories, Billing, Runs
│   ├── package.json                 # Node dependencies
│   ├── vite.config.js               # Vite 6 bundler config
│   └── tailwind.config.js           # Graphite & Acid Lime design system tokens
├── docs\                            # Architecture, PRD, Database, API, and Security specs
├── .gitignore                       # Root ignore rules
└── README.md
```

---

## 5. Getting Started (Windows PowerShell)

### 5.1 Backend Setup
```powershell
# Navigate to backend
Set-Location D:\My_SDE\backend

# Initialize environment
Copy-Item .env.example .env

# Install dependencies into virtual environment
uv sync

# Run database migrations
uv run alembic upgrade head

# Run tests & lint checks (220 passed)
uv run ruff check .
uv run pytest -v

# Start FastAPI development server
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Backend API will be live at `http://127.0.0.1:8000` with Swagger UI at `http://127.0.0.1:8000/docs`.

### 5.2 Frontend Setup
```powershell
# In a separate terminal, navigate to frontend
Set-Location D:\My_SDE\frontend

# Initialize environment
Copy-Item .env.example .env

# Install dependencies
npm install

# Verify production build
npm run build

# Start development server
npm run dev
```
Frontend application will launch at `http://localhost:5173`.

---

## 6. Testing & Quality Verification

```powershell
# Run all 220 backend tests
uv run pytest

# Run RAG Ground-Truth Benchmark
uv run pytest tests/unit/test_rag_eval.py -s

# Run Autonomous AI Repair Benchmark (6/6 passing)
uv run pytest tests/unit/test_repair_eval.py -v

# Run Code Execution & Sandbox Security Tests
uv run pytest tests/integration/test_execution_api.py tests/unit/test_sandbox_isolation.py

# Lint checks
uv run ruff check app tests
```
