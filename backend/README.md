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
- `20261019_0003` (GitHub App Integration & Repositories — head)

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

## 4. Verification & Testing Tiers

- **Locally Verified (Automated Suite):**
  - Full OAuth state lifecycle (creation, expiration, single-use consumption, replay protection).
  - Multi-tenant boundary isolation and anti-takeover safeguards.
  - Role-based permissions (owner/admin vs member).
  - Mocked GitHub installation callbacks and repository synchronization.
  - Rate limiting (429) and timeout (504) error handling.
  - Webhook HMAC SHA-256 signature verification and delivery deduplication.
  - Forward-only database migrations.
- **Requires Configured GitHub App:**
  - RS256 token exchange using a real private key against GitHub API.
- **Requires Live GitHub Installation:**
  - Full round-trip browser installation flow from GitHub marketplace/settings page into local server.

---

## 5. Testing and Code Quality

### 5.1 Run Ruff Linting
```powershell
uv run ruff check .
```

### 5.2 Run Full Pytest Suite (44 tests)
```powershell
uv run pytest -v
```
