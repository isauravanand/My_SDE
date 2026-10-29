/**
 * Centralized API client for MySDE Backend.
 * Uses credentials: 'include' for HttpOnly session cookie transmission.
 * Automatically injects X-CSRF-Token header from mysde_csrf cookie for state-changing requests.
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message, status, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

/**
 * Extract a cookie value by name from document.cookie.
 */
function getCookie(name) {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp('(^|;\\s*)(' + name + ')=([^;]*)'));
  return match ? decodeURIComponent(match[3]) : null;
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const method = (options.method || 'GET').toUpperCase();

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  // If state-changing request, inject CSRF token from cookie if available
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrfToken = getCookie('mysde_csrf');
    if (csrfToken && !headers['x-csrf-token'] && !headers['X-CSRF-Token']) {
      headers['x-csrf-token'] = csrfToken;
    }
  }

  const config = {
    ...options,
    method,
    headers,
    credentials: 'include', // Essential for sending/receiving HttpOnly cookies across ports
  };

  try {
    const response = await fetch(url, config);
    const contentType = response.headers.get('content-type');
    const isJson = contentType && contentType.includes('application/json');
    const data = isJson ? await response.json() : await response.text();

    if (!response.ok) {
      const errorMessage =
        (data && data.error && data.error.message) ||
        (data && data.detail) ||
        (typeof data === 'string' ? data : `Request failed with status ${response.status}`);
      throw new ApiError(errorMessage, response.status, data);
    }

    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      `Unable to connect to backend at ${API_BASE_URL}. Ensure the server is running.`,
      0,
      { originalError: error.message }
    );
  }
}

export const api = {
  // Generic HTTP
  get: (endpoint, options) => request(endpoint, { ...options, method: 'GET' }),
  post: (endpoint, body, options) =>
    request(endpoint, { ...options, method: 'POST', body: JSON.stringify(body) }),
  put: (endpoint, body, options) =>
    request(endpoint, { ...options, method: 'PUT', body: JSON.stringify(body) }),
  patch: (endpoint, body, options) =>
    request(endpoint, { ...options, method: 'PATCH', body: JSON.stringify(body) }),
  delete: (endpoint, options) => request(endpoint, { ...options, method: 'DELETE' }),

  // Diagnostic Probes
  getHealth: () => request('/health'),
  getReadiness: () => request('/ready'),
  getBaseUrl: () => API_BASE_URL,

  // Authentication Endpoints
  register: (payload) => request('/api/v1/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  login: (payload) => request('/api/v1/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  logout: () => request('/api/v1/auth/logout', { method: 'POST' }),
  getMe: () => request('/api/v1/auth/me', { method: 'GET' }),
  verifyEmail: (token) => request('/api/v1/auth/verify-email', { method: 'POST', body: JSON.stringify({ token }) }),
  resendVerification: (email) => request('/api/v1/auth/resend-verification', { method: 'POST', body: JSON.stringify({ email }) }),
  forgotPassword: (email) => request('/api/v1/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) }),
  resetPassword: (payload) => request('/api/v1/auth/reset-password', { method: 'POST', body: JSON.stringify(payload) }),

  // Workspace Endpoints
  getWorkspaces: () => request('/api/v1/workspaces', { method: 'GET' }),
  createWorkspace: (name) => request('/api/v1/workspaces', { method: 'POST', body: JSON.stringify({ name }) }),
  getWorkspace: (id) => request(`/api/v1/workspaces/${id}`, { method: 'GET' }),
  getWorkspaceMembers: (id) => request(`/api/v1/workspaces/${id}/members`, { method: 'GET' }),
  updateMemberRole: (workspaceId, membershipId, role) =>
    request(`/api/v1/workspaces/${workspaceId}/members/${membershipId}`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    }),

  // Projects Endpoints
  getProjects: (params = {}) => {
    const searchParams = new URLSearchParams();
    if (params.workspaceId) searchParams.append('workspace_id', params.workspaceId);
    if (params.status) searchParams.append('status', params.status);
    if (params.search) searchParams.append('search', params.search);
    const qs = searchParams.toString();
    return request(`/api/v1/projects${qs ? `?${qs}` : ''}`, { method: 'GET' });
  },
  createProject: (payload) => {
    const wsId = payload?.workspace_id || payload?.workspaceId;
    const qs = wsId ? `?workspace_id=${encodeURIComponent(wsId)}` : '';
    return request(`/api/v1/projects${qs}`, { method: 'POST', body: JSON.stringify(payload) });
  },
  getProject: (projectId) => request(`/api/v1/projects/${projectId}`, { method: 'GET' }),
  updateProject: (projectId, payload) =>
    request(`/api/v1/projects/${projectId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  archiveProject: (projectId) => request(`/api/v1/projects/${projectId}/archive`, { method: 'POST' }),
  restoreProject: (projectId) => request(`/api/v1/projects/${projectId}/restore`, { method: 'POST' }),

  // Tasks Endpoints
  getWorkspaceTasks: (params = {}) => {
    const searchParams = new URLSearchParams();
    if (params.workspaceId) searchParams.append('workspace_id', params.workspaceId);
    if (params.status) searchParams.append('status', params.status);
    if (params.priority) searchParams.append('priority', params.priority);
    if (params.search) searchParams.append('search', params.search);
    if (params.limit !== undefined) searchParams.append('limit', params.limit);
    if (params.offset !== undefined) searchParams.append('offset', params.offset);
    if (params.sort_by) searchParams.append('sort_by', params.sort_by);
    if (params.sort_order) searchParams.append('sort_order', params.sort_order);
    const qs = searchParams.toString();
    return request(`/api/v1/tasks${qs ? `?${qs}` : ''}`, { method: 'GET' });
  },
  getProjectTasks: (projectId, params = {}) => {
    const searchParams = new URLSearchParams();
    if (params.status) searchParams.append('status', params.status);
    if (params.priority) searchParams.append('priority', params.priority);
    if (params.search) searchParams.append('search', params.search);
    if (params.limit !== undefined) searchParams.append('limit', params.limit);
    if (params.offset !== undefined) searchParams.append('offset', params.offset);
    if (params.sort_by) searchParams.append('sort_by', params.sort_by);
    if (params.sort_order) searchParams.append('sort_order', params.sort_order);
    const qs = searchParams.toString();
    return request(`/api/v1/projects/${projectId}/tasks${qs ? `?${qs}` : ''}`, { method: 'GET' });
  },
  createTask: (projectId, payload) =>
    request(`/api/v1/projects/${projectId}/tasks`, { method: 'POST', body: JSON.stringify(payload) }),
  getTask: (taskId) => request(`/api/v1/tasks/${taskId}`, { method: 'GET' }),
  updateTask: (taskId, payload) =>
    request(`/api/v1/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  archiveTask: (taskId) => request(`/api/v1/tasks/${taskId}/archive`, { method: 'POST' }),
  restoreTask: (taskId) => request(`/api/v1/tasks/${taskId}/restore`, { method: 'POST' }),

  // Dashboard Endpoints
  getDashboardSummary: (workspaceId) =>
    request(`/api/v1/dashboard/summary?workspace_id=${encodeURIComponent(workspaceId)}`, { method: 'GET' }),
  getRecentActivity: (workspaceId, limit = 10) =>
    request(`/api/v1/dashboard/recent-activity?workspace_id=${encodeURIComponent(workspaceId)}&limit=${limit}`, {
      method: 'GET',
    }),

  // GitHub Integration Endpoints
  getGitHubStatus: (workspaceId) =>
    request(`/api/v1/integrations/github/status?workspace_id=${encodeURIComponent(workspaceId)}`, { method: 'GET' }),
  getGitHubInstallUrl: (workspaceId) =>
    request(`/api/v1/integrations/github/install?workspace_id=${encodeURIComponent(workspaceId)}`, { method: 'GET' }),
  getGitHubRepositories: (params = {}) => {
    const searchParams = new URLSearchParams();
    if (params.workspaceId) searchParams.append('workspace_id', params.workspaceId);
    if (params.search) searchParams.append('search', params.search);
    if (params.is_selected !== undefined) searchParams.append('is_selected', params.is_selected);
    if (params.limit !== undefined) searchParams.append('limit', params.limit);
    if (params.offset !== undefined) searchParams.append('offset', params.offset);
    const qs = searchParams.toString();
    return request(`/api/v1/integrations/github/repositories${qs ? `?${qs}` : ''}`, { method: 'GET' });
  },
  syncGitHubRepositories: (workspaceId) =>
    request(`/api/v1/integrations/github/repositories/sync?workspace_id=${encodeURIComponent(workspaceId)}`, {
      method: 'POST',
    }),
  toggleGitHubRepository: (repoId, isSelected) =>
    request(`/api/v1/integrations/github/repositories/${repoId}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_selected: isSelected }),
    }),
  disconnectGitHub: (workspaceId) =>
    request(`/api/v1/integrations/github/disconnect?workspace_id=${encodeURIComponent(workspaceId)}`, {
      method: 'POST',
    }),

  // Code RAG Endpoints
  triggerRepoIndexing: (repoId, workspaceId, payload = {}) =>
    request(`/api/v1/rag/repositories/${repoId}/index?workspace_id=${encodeURIComponent(workspaceId)}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getRepoIndexingStatus: (repoId, workspaceId) =>
    request(
      `/api/v1/rag/repositories/${repoId}/index/status?workspace_id=${encodeURIComponent(workspaceId)}`,
      { method: 'GET' }
    ),
  listRepoIndexingJobs: (repoId, workspaceId, limit = 10) =>
    request(
      `/api/v1/rag/repositories/${repoId}/index/jobs?workspace_id=${encodeURIComponent(workspaceId)}&limit=${limit}`,
      { method: 'GET' }
    ),
  retrieveCodeChunks: (repoId, workspaceId, payload) =>
    request(`/api/v1/rag/repositories/${repoId}/retrieve?workspace_id=${encodeURIComponent(workspaceId)}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  retrieveTaskContext: (taskId, topK = 5) =>
    request(`/api/v1/rag/tasks/${taskId}/retrieve-context?top_k=${topK}`, {
      method: 'GET',
    }),

  // LangGraph Planning Endpoints
  triggerTaskPlanning: (taskId, payload = {}) =>
    request(`/api/v1/tasks/${taskId}/plan`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getLatestTaskPlan: (taskId) =>
    request(`/api/v1/tasks/${taskId}/plan`, {
      method: 'GET',
    }),
  listTaskPlans: (taskId, limit = 10, offset = 0) =>
    request(`/api/v1/tasks/${taskId}/plans?limit=${limit}&offset=${offset}`, {
      method: 'GET',
    }),
  getPlanningRun: (runId, workspaceId) =>
    request(
      `/api/v1/planning/runs/${runId}?workspace_id=${encodeURIComponent(workspaceId)}`,
      { method: 'GET' }
    ),
  cancelPlanningRun: (runId, workspaceId) =>
    request(
      `/api/v1/planning/runs/${runId}/cancel?workspace_id=${encodeURIComponent(workspaceId)}`,
      { method: 'POST' }
    ),
  getImplementationPlan: (planId, workspaceId) =>
    request(
      `/api/v1/planning/plans/${planId}?workspace_id=${encodeURIComponent(workspaceId)}`,
      { method: 'GET' }
    ),

  // Isolated Execution & Patch Verification Endpoints (Phase 7)
  startTaskExecution: (taskId, payload = {}) =>
    request(`/api/v1/tasks/${taskId}/execution`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listTaskExecutions: (taskId, limit = 10, offset = 0) =>
    request(`/api/v1/tasks/${taskId}/executions?limit=${limit}&offset=${offset}`, {
      method: 'GET',
    }),
  getExecutionRun: (runId) =>
    request(`/api/v1/execution/runs/${runId}`, {
      method: 'GET',
    }),
  getExecutionPatch: (runId) =>
    request(`/api/v1/execution/runs/${runId}/patch`, {
      method: 'GET',
    }),
  getExecutionPreview: (runId) =>
    request(`/api/v1/execution/runs/${runId}/preview`, {
      method: 'GET',
    }),
  approvePatchAndExecute: (runId, payload = {}) =>
    request(`/api/v1/execution/runs/${runId}/approve`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  rejectPatchProposal: (runId, payload = {}) =>
    request(`/api/v1/execution/runs/${runId}/reject`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  cancelExecutionRun: (runId) =>
    request(`/api/v1/execution/runs/${runId}/cancel`, {
      method: 'POST',
    }),

  // Bounded AI Repair Endpoints (Phase 8)
  startExecutionRepair: (runId, payload = {}) =>
    request(`/api/v1/executions/${runId}/repair`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getExecutionRepair: (runId) =>
    request(`/api/v1/executions/${runId}/repair`, {
      method: 'GET',
    }),
  getRepairRun: (repairId) =>
    request(`/api/v1/repairs/${repairId}`, {
      method: 'GET',
    }),
  cancelRepairRun: (repairId) =>
    request(`/api/v1/repairs/${repairId}/cancel`, {
      method: 'POST',
    }),
  getRepairSummary: (repairId) =>
    request(`/api/v1/repairs/${repairId}/summary`, {
      method: 'GET',
    }),

  // Git Branch & Pull Request Publishing Endpoints (Phase 9)
  getPublishingPrecheck: (runId, workspaceId) => {
    const qs = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
    return request(`/api/v1/executions/${runId}/publish/precheck${qs}`, {
      method: 'GET',
    });
  },
  approvePublishing: (runId, patchHash, workspaceId) => {
    const qs = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
    const body = patchHash ? { patch_hash: patchHash } : {};
    return request(`/api/v1/executions/${runId}/publish/approve${qs}`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
  publishToGitHub: (runId, workspaceId, payload = {}) => {
    const qs = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
    return request(`/api/v1/executions/${runId}/publish${qs}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  getExecutionPublishing: (runId, workspaceId) => {
    const qs = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
    return request(`/api/v1/executions/${runId}/publish${qs}`, {
      method: 'GET',
    });
  },
  retryPublishing: (publishingId, workspaceId) => {
    const qs = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
    return request(`/api/v1/publishing/${publishingId}/retry${qs}`, {
      method: 'POST',
    });
  },

  // Observability, Metrics & Recovery Endpoints (Phase 10)
  getRunTrace: (runId, workspaceId) =>
    request(`/api/v1/observability/runs/${runId}/trace?workspace_id=${workspaceId}`, {
      method: 'GET',
    }),
  getWorkspaceMetrics: (workspaceId, timeWindowDays = 30) =>
    request(`/api/v1/observability/metrics?workspace_id=${workspaceId}&time_window_days=${timeWindowDays}`, {
      method: 'GET',
    }),
  listWorkspaceRuns: (workspaceId, params = {}) => {
    const query = new URLSearchParams({ workspace_id: workspaceId });
    if (params.status && params.status !== 'all') query.append('status', params.status);
    if (params.dateFrom) query.append('date_from', params.dateFrom);
    if (params.dateTo) query.append('date_to', params.dateTo);
    if (params.limit) query.append('limit', params.limit.toString());
    return request(`/api/v1/observability/runs?${query.toString()}`, {
      method: 'GET',
    });
  },
  recoverStaleRuns: (workspaceId, timeoutMinutes = 15) =>
    request(`/api/v1/observability/recover-stale?workspace_id=${workspaceId}&timeout_minutes=${timeoutMinutes}`, {
      method: 'POST',
    }),

  // SaaS Billing, Subscriptions & Metering Endpoints (Phase 11)
  getBillingPlans: () =>
    request('/api/v1/billing/plans', {
      method: 'GET',
    }),
  getSubscription: (workspaceId) =>
    request(`/api/v1/billing/subscription?workspace_id=${workspaceId}`, {
      method: 'GET',
    }),
  createCheckoutSession: (workspaceId, payload) =>
    request(`/api/v1/billing/checkout?workspace_id=${workspaceId}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  cancelSubscription: (workspaceId) =>
    request(`/api/v1/billing/cancel?workspace_id=${workspaceId}`, {
      method: 'POST',
    }),
  getUsageHistory: (workspaceId, limit = 50) =>
    request(`/api/v1/billing/usage?workspace_id=${workspaceId}&limit=${limit}`, {
      method: 'GET',
    }),
  simulateMockWebhook: (provider, payload, signature) =>
    request(`/api/v1/billing/webhooks/${provider}`, {
      method: 'POST',
      headers: {
        'X-Mock-Signature': signature,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    }),
};



