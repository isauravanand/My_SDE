# MySDE — Frontend (React, Vite, Tailwind CSS)

Responsive React Single Page Application for the MySDE AI Software Engineering platform.

## 1. Technology Stack

- **React 18** with **Vite 6**
- **JavaScript** (ESModules)
- **Tailwind CSS v3** with custom design tokens (Graphite surfaces `#0c0e12`, `#161922`, Acid Lime accent `#c6f135`)
- **React Router v6** (with public auth routes, `ProtectedRoute` guards, and nested layouts)
- **TanStack Query v5** for asynchronous server state, automatic caching, and tenant-scoped query invalidation
- **Lucide React** for icons

---

## 2. Windows PowerShell Setup & Execution

### 2.1 Navigate to Frontend Directory
```powershell
Set-Location D:\My_SDE\frontend
```

### 2.2 Configure Environment
```powershell
Copy-Item .env.example .env
```
Ensure `VITE_API_BASE_URL` points to your running backend:
```ini
VITE_API_BASE_URL=http://localhost:8000
```

### 2.3 Install Dependencies
```powershell
npm install
```

### 2.4 Start Development Server
```powershell
npm run dev
```
The application will launch at: [http://localhost:5173](http://localhost:5173)

### 2.5 Build for Production
```powershell
npm run build
```
Production assets are generated in `frontend/dist/`.

---

## 3. Application Pages & Capabilities

- `/` (**Dashboard**): Real-time metrics (Active Projects, Open Tasks, In Progress, Completed Tasks), interactive recent tasks list, and chronological audit activity feed.
- `/projects` (**Projects**): Card grid with search, status filtering (`all`, `active`, `archived`), project creation modal, task counters, and archive/restore actions.
- `/projects/:projectId` (**Project Detail**): Project metadata, scoped task list, task filtering, creation dialog, and archive/restore project controls.
- `/tasks` (**Tasks**): Workspace-wide searchable and filterable task table with pagination, inline status dropdowns, detail view modal, edit task modal, and archive/restore actions.
- `/repositories` (**Repositories & GitHub App Integration**): Real-time GitHub App status (Unconfigured, Disconnected, Connected), one-click installation flow, repository synchronization, search/filtering, active workspace project selection toggles, disconnect confirmation, and setup guide.
- `/login`, `/register`, `/verify-email`, `/forgot-password`, `/reset-password`: Authentication workflows with HttpOnly session cookies and CSRF protection.
