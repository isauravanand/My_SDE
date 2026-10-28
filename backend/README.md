# MySDE — Backend (FastAPI, SQLAlchemy, PostgreSQL)

Production-grade FastAPI backend for the MySDE AI Software Engineering platform.

## 1. Prerequisites

- **Python 3.10+** (Python 3.10.10+ detected)
- **uv** (Modern Python package and project manager)
- **PostgreSQL 15+**

---

## 2. Windows PowerShell Setup & Execution

### 2.1 Navigate to Backend Directory
```powershell
Set-Location D:\My_SDE\backend
```

### 2.2 Configure Environment
```powershell
Copy-Item .env.example .env
```
Inspect `.env` and adjust the PostgreSQL connection string with your local credentials:
```ini
DATABASE_URL=postgresql+psycopg://postgres:your_local_password@localhost:5432/mysde_dev
```

### 2.3 Install Dependencies
Synchronize dependencies into `.venv` using `uv`:
```powershell
uv sync
```

### 2.4 Run Database Migrations
Apply all forward-only Alembic migrations:
- `20261019_0001` (Auth & Multi-Tenancy)
- `20261019_0002` (Projects, Tasks, and Activities)
- `20261019_0003` (GitHub App Integration & Repositories)
- `20261020_0004` (Code RAG Indexing Jobs & Chunks)
- `20261020_0005` (LangGraph Planning Models)
- `20261021_0006` (Execution Runs, Patch Artifacts, and Verification Results)
- `20261021_0007` (Repair Runs and Repair Attempts)
- `20261021_0008` (Publishing Runs, Git Branches & PR Tracking)
- `20261022_0009` (Billing Plans, Subscriptions, Usage Ledger & Webhooks — head)

```powershell
uv run alembic upgrade head
```

To preview SQL without executing:
```powershell
uv run alembic upgrade head --sql
```

### 2.5 Start Development Server
```powershell
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Interactive OpenAPI documentation:
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 3. GitHub App Integration Setup

The backend runs without GitHub App credentials configured. When unconfigured, GitHub endpoints return descriptive messages guiding setup.

### 3.1 Registering a GitHub App
1. Navigate to **GitHub Settings → Developer Settings → GitHub Apps → New GitHub App**.
2. **App Name:** `MySDE - <Your Org>` (e.g., `MySDE-LocalDev`).
3. **Homepage URL:** `http://localhost:5173`
4. **Callback URL:** `http://localhost:8000/api/v1/integrations/github/callback`
5. **Webhook URL:** Your local tunnel URL (see below) or temporary URL `http://localhost:8000/api/v1/integrations/github/webhook`.
6. **Webhook Secret:** Choose a random secret string and save it to `GITHUB_WEBHOOK_SECRET`.
7. **Permissions:**
   - **Repository contents:** Read & Write
   - **Pull requests:** Read & Write
   - **Issues:** Read & Write
   - **Metadata:** Read-only (required)
8. **Subscribe to events:** Check *Installation*, *Installation repositories*, *Issues*, and *Pull request*.
9. Generate a **Private Key** (.pem) and save it locally.

### 3.2 Environment Variables
Add to `backend/.env`:
```ini
GITHUB_APP_ID=123456
GITHUB_APP_SLUG=mysde-local-dev
GITHUB_APP_CLIENT_ID=Iv1.xxxxxxxxxxxx
GITHUB_APP_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_APP_PRIVATE_KEY_PATH=./github-app-private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here
GITHUB_CALLBACK_URL=http://localhost:8000/api/v1/integrations/github/callback

# Phase 8: Bounded Repair Defaults
REPAIR_MAX_ATTEMPTS=3
REPAIR_MAX_DURATION_SECONDS=600
REPAIR_MAX_MODEL_CALLS=6
```

### 3.3 Forwarding Webhooks Locally
GitHub requires a publicly accessible HTTPS endpoint for webhooks. For local development, use **Smee.io** or **ngrok**:
```powershell
# Using smee-client
npx smee -u https://smee.io/your_channel_id --target http://localhost:8000/api/v1/integrations/github/webhook

# Or using ngrok
ngrok http 8000
```
Update your GitHub App's Webhook URL to your Smee channel or ngrok tunnel URL.

---

## 4. Phase 5: Code RAG Architecture & Ingestion Lifecycle

### 4.1 Ingestion Pipeline
1. **Authorization:** Validates user is an authorized workspace member and repository is selected.
2. **Git Commit Resolution:** Resolves target branch/ref to immutable 40-character commit SHA via GitHub Git API.
3. **Recursive Tree Traversal:** Fetches full repository tree metadata.
4. **File Filtering Policy:**
   - Excludes `.git/`, `node_modules/`, `.venv/`, `dist/`, `build/`, `vendor/`, `coverage/`.
   - Excludes lockfiles (`package-lock.json`, `poetry.lock`, `Cargo.lock`, `pnpm-lock.yaml`).
   - Excludes secret-bearing paths (`.env*`, `id_rsa*`, `*.pem`, `*.key`, `credentials.json`).
   - Excludes compiled binaries and detects null bytes (`b"\x00"`).
   - Enforces configurable file size limits (default 512 KB) and repository file quotas (default 1000 files).
5. **Semantic & Line-Aware Chunking:**
   - Detects class and function boundaries in Python, JavaScript, TypeScript, Go, Rust, Java.
   - Preserves 1-based start and end line ranges.
   - Calculates SHA-256 content hashes to eliminate duplicate chunks.
6. **Vector Embeddings:**
   - Provider abstraction supports `fake` (deterministic unit-normalized vectors for testing/offline dev) and `openai` (`text-embedding-3-small`).
7. **Vector Similarity Retrieval:**
   - Vectorized cosine dot-product powered by NumPy.
   - Hybrid lexical boost for exact keyword and symbol matches.
   - Automatic line-range deduplication to prevent redundant overlapping snippets.

### 4.2 Embedding Configuration
In `backend/.env`:
```ini
# Local offline development & test suite (default):
EMBEDDING_PROVIDER=fake
EMBEDDING_MODEL=mock-embed-384
EMBEDDING_DIMENSIONS=384

# For OpenAI API:
# EMBEDDING_PROVIDER=openai
# EMBEDDING_MODEL=text-embedding-3-small
# EMBEDDING_DIMENSIONS=1536
# EMBEDDING_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxx
```

---

## 5. Phase 6: AI Planning & LLM Providers

MySDE uses an evidence-grounded planning agent to synthesize implementation plans. The backend supports multiple LLM providers via a clean provider abstraction:

- `mock` (default): Fast, deterministic offline planning for testing and zero-cost local development.
- `groq`: Ultra-fast LPU inference powered by the official Groq SDK.
- `openai`: OpenAI API or compatible endpoints.

### 5.1 Groq Setup & Configuration
To use Groq for high-speed planning and generation:
1. Obtain an API key from [Groq Console](https://console.groq.com/keys).
2. Configure `backend/.env`:
   ```ini
   LLM_PROVIDER=groq
   LLM_MODEL=llama-3.3-70b-versatile    # Recommended: llama-3.3-70b-versatile, llama-3.1-8b-instant
   LLM_API_KEY=gsk_your_groq_api_key_here
   PLANNING_TEMPERATURE=0.2
   PLANNING_MAX_OUTPUT_TOKENS=4096
   ```
3. Run the Groq smoke-test:
   ```bash
   uv run python scripts/smoke_test_groq.py
   ```

---

## 6. Isolated Sandbox & Execution (Phase 7)

MySDE provides an OS-enforced execution sandbox to apply validated patches and run automated checks on untrusted repository code.

### 5.1 Docker Sandbox Controls
When Docker daemon is running, container execution enforces:
- Non-root user: `--user 1000:1000`
- Read-only root filesystem: `--read-only` (with temporary `/workspace` volume)
- Network disabled by default: `--network none`
- Linux capabilities dropped: `--cap-drop ALL`
- No new privileges: `--security-opt no-new-privileges:true`
- Kernel limits: `--memory 1024m`, `--cpus 1.0`, `--pids-limit 100`
- Never mounts host root, home directory, or `/var/run/docker.sock`

### 5.2 Safe Fallback Runtime
If Docker is not running or unavailable in the host environment (such as standard Windows development machines without Docker Desktop), the system falls back to `MockSandbox`. The system safely reports container execution as unverified and does not execute untrusted commands directly on the host.

### 5.3 Permitted Verification Commands
Server-side allowlist:
- `syntax_check`: `python -m py_compile`
- `pytest`: `python -m pytest -v`
- `ruff_check`: `python -m ruff check .`
- `npm_test`: `npm test -- --run`
- `npm_lint`: `npm run lint`

---

## 6. Bounded AI Repair Loops & Verification (Phase 8)

Phase 8 provides an evidence-grounded repair loop orchestrated via LangGraph that analyzes failed checks, proposes safe patches, applies them in the sandbox, and reruns checks within strict limits.

### 6.1 Server-Enforced Budgets
Configurable via environment variables with conservative defaults:
- `REPAIR_MAX_ATTEMPTS`: 3 attempts per execution run
- `REPAIR_MAX_DURATION_SECONDS`: 600 seconds (10 minutes) deadline
- `REPAIR_MAX_MODEL_CALLS`: 6 model invocations per repair run

### 6.2 Anti-Cheating Invariants
The repair generator immediately rejects:
- Patches deleting test files or removing test assertions.
- Patches replacing assertions with dummy passes.
- Patches modifying package manifests or lockfiles (`package.json`, `pyproject.toml`, `requirements.txt`).

---

---

## 7. Phase 9: Safe Git Branch, Commit, and Pull Request Publishing

### 7.1 Publishing Workflow Lifecycle
1. **Approval Gate:** Human operator explicitly reviews proposed diff, changed file paths, and passed test verification evidence. Approving binds the exact SHA-256 patch hash to a `publishing_run`. Any patch regeneration or modification immediately invalidates approval.
2. **Pre-flight & File Safety:** Verifies 0 failed verification checks, rejects path traversal (`../`) and forbidden paths (`.env*`, `*.pem`, `*.key`, `id_rsa*`).
3. **Stale Base Branch Check:** Queries GitHub for the current commit SHA of the base branch. If newer commits exist on the remote base since the task execution began, publishing is halted (`409 Conflict`) to prevent stale merge conflicts.
4. **Collision-Resistant Task Branch:** Creates a dedicated branch (`mysde/task-<task_id[:8]>-<slug>`) pointing to the base commit.
5. **Immutable Git Tree & Commit Push:** Creates Git blobs, tree, and commit via the GitHub Git Data API, then points the branch ref to the new commit.
6. **Pull Request Creation:** Opens a Pull Request using GitHub API containing full task description, change summary, and verification evidence.
7. **Idempotency & Safe Recovery:** Repeated clicks return the existing completed PR without duplicate commits or branches.

### 7.2 GitHub App Permissions
For live publishing to GitHub, ensure your GitHub App has:
- **Repository Permissions:**
  - `Contents`: **Read and write** (to create branches, blobs, trees, and commits)
  - `Pull requests`: **Read and write** (to create and manage pull requests)
  - `Metadata`: **Read-only** (mandatory for all GitHub Apps)

---

## 8. Verification, Evaluation & Testing Tiers

### 8.1 Code RAG Evaluation Suite
Run the deterministic ground-truth benchmark measuring Recall@k and Mean Reciprocal Rank (MRR):
```powershell
uv run pytest tests/unit/test_rag_eval.py -s
```
**Current Benchmark Results:**
- **Recall@1:** 87.5%
- **Recall@3:** 100.0%
- **Recall@5:** 100.0%
- **MRR (Mean Reciprocal Rank):** 0.9375

### 8.2 Repair Evaluation Suite
Run the Phase 8 controlled fixture benchmark:
```powershell
uv run pytest tests/unit/test_repair_eval.py -v
```
**Benchmark Results (6/6 passing):**
- Case 1: Assertion Failure Repair (Single-attempt fix)
- Case 2: Syntax Error Repair (Single-attempt fix)
- Case 3: Non-repairable Infrastructure Failure (Safely terminated)
- Case 4: Anti-Cheating Policy Enforcement (Test deletion & assertion weakening rejected)
- Case 5: Attempt Budget Exhaustion (Terminated after 3 failed attempts)
- Case 6: Time Deadline Enforcement (Terminated after deadline exceeded)

### 8.3 Publishing Suite (Phase 9)
```powershell
uv run pytest tests/unit/test_publishing_service.py tests/integration/test_publishing_api.py -v
```

### 8.4 Observability & Recovery Suite (Phase 10)
```powershell
uv run pytest tests/unit/test_observability.py tests/integration/test_observability_api.py -v
```

### 8.5 SaaS Billing & Metering Suite (Phase 11)
```powershell
uv run pytest tests/unit/test_billing.py tests/integration/test_billing_api.py -v
```

### 8.6 Run Full Test Suite (220 tests)
```powershell
uv run pytest -v
```

### 8.7 Run Ruff Linter
```powershell
uv run ruff check .
```
