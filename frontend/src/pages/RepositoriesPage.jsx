import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  GitBranch,
  RefreshCw,
  Search,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Lock,
  Globe,
  Unplug,
  X,
  HelpCircle,
  Building2,
  User,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { api, ApiError } from '../lib/api';
import { EmptyState } from '../components/common/EmptyState';

export function RepositoriesPage() {
  const queryClient = useQueryClient();
  const { activeWorkspace } = useAuth();
  const workspaceId = activeWorkspace?.id;

  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('all'); // 'all' | 'selected' | 'private' | 'public'
  const [disconnectModalOpen, setDisconnectModalOpen] = useState(false);
  const [setupGuideOpen, setSetupGuideOpen] = useState(false);
  const [actionError, setActionError] = useState('');

  // 1. Query GitHub Integration Status
  const {
    data: status,
    isLoading: isStatusLoading,
    isError: isStatusError,
    refetch: refetchStatus,
  } = useQuery({
    queryKey: ['github-status', workspaceId],
    queryFn: () => api.getGitHubStatus(workspaceId),
    enabled: !!workspaceId,
    staleTime: 10000,
  });

  // 2. Query Synchronized Repositories
  const {
    data: reposData,
    isLoading: isReposLoading,
    isError: isReposError,
    refetch: refetchRepos,
  } = useQuery({
    queryKey: ['github-repositories', workspaceId, search, filterType],
    queryFn: () =>
      api.getGitHubRepositories({
        workspaceId,
        search: search.trim() || undefined,
        is_selected: filterType === 'selected' ? true : undefined,
      }),
    enabled: !!workspaceId && !!status?.is_connected,
  });

  const repositories = (reposData?.items || []).filter((repo) => {
    if (filterType === 'private') return repo.is_private;
    if (filterType === 'public') return !repo.is_private;
    return true;
  });

  // 3. Initiate Install Mutation
  const installMutation = useMutation({
    mutationFn: () => api.getGitHubInstallUrl(workspaceId),
    onSuccess: (data) => {
      if (data.install_url) {
        window.location.href = data.install_url;
      }
    },
    onError: (err) => {
      setActionError(err.message || 'Failed to initiate GitHub installation');
    },
  });

  // 4. Sync Repositories Mutation
  const syncMutation = useMutation({
    mutationFn: () => api.syncGitHubRepositories(workspaceId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['github-status', workspaceId] });
      await queryClient.invalidateQueries({ queryKey: ['github-repositories', workspaceId] });
      setActionError('');
    },
    onError: (err) => {
      setActionError(err.message || 'Failed to sync repositories');
    },
  });

  // 5. Toggle Selection Mutation
  const toggleMutation = useMutation({
    mutationFn: ({ repoId, isSelected }) => api.toggleGitHubRepository(repoId, isSelected),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['github-repositories', workspaceId] });
      await queryClient.invalidateQueries({ queryKey: ['github-status', workspaceId] });
    },
    onError: (err) => {
      setActionError(err.message || 'Failed to update repository selection');
    },
  });

  // 6. Disconnect Mutation
  const disconnectMutation = useMutation({
    mutationFn: () => api.disconnectGitHub(workspaceId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['github-status', workspaceId] });
      await queryClient.invalidateQueries({ queryKey: ['github-repositories', workspaceId] });
      setDisconnectModalOpen(false);
      setActionError('');
    },
    onError: (err) => {
      setActionError(err.message || 'Failed to disconnect integration');
    },
  });

  const isConfigured = status?.is_configured;
  const isConnected = status?.is_connected;

  return (
    <div className="space-y-6">
      {/* Top Banner / Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-content-primary">Repositories</h1>
          <p className="text-sm text-content-secondary mt-1">
            Connected GitHub repositories with read, branch, and automated pull request permissions in{' '}
            <span className="text-content-primary font-medium">{activeWorkspace?.name}</span>.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setSetupGuideOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md bg-background-card border border-border-subtle text-content-secondary hover:text-content-primary text-xs font-medium transition-colors"
          >
            <HelpCircle className="w-3.5 h-3.5 text-accent" />
            Setup Guide
          </button>

          {isConnected ? (
            <>
              <button
                onClick={() => syncMutation.mutate()}
                disabled={syncMutation.isPending}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md bg-background-subtle border border-border-subtle text-content-primary text-xs font-semibold hover:bg-background-hover transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
                {syncMutation.isPending ? 'Syncing...' : 'Sync Repositories'}
              </button>

              <button
                onClick={() => setDisconnectModalOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-semibold hover:bg-rose-500/20 transition-colors"
              >
                <Unplug className="w-3.5 h-3.5" />
                Disconnect
              </button>
            </>
          ) : isConfigured ? (
            <button
              onClick={() => installMutation.mutate()}
              disabled={installMutation.isPending}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors shadow-subtle disabled:opacity-50"
            >
              <GitBranch className="w-4 h-4" />
              {installMutation.isPending ? 'Connecting...' : 'Connect GitHub App'}
            </button>
          ) : null}
        </div>
      </div>

      {/* Global Action Error Banner */}
      {actionError && (
        <div className="p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{actionError}</span>
          </div>
          <button onClick={() => setActionError('')} className="text-rose-400 hover:text-rose-300">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Unconfigured State Warning Banner */}
      {!isStatusLoading && !isConfigured && (
        <div className="p-4 rounded-lg bg-background-card border border-amber-500/30 text-amber-300 text-xs space-y-2">
          <div className="flex items-center gap-2 font-semibold text-sm">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            GitHub App Not Configured in Environment
          </div>
          <p className="text-content-secondary leading-relaxed">
            The backend does not have GitHub App credentials set (<code className="text-amber-300 font-mono">GITHUB_APP_ID</code>,{' '}
            <code className="text-amber-300 font-mono">GITHUB_APP_CLIENT_ID</code>,{' '}
            <code className="text-amber-300 font-mono">GITHUB_APP_PRIVATE_KEY_PATH</code>). Local development functions normally, but live repository synchronization requires configuring your GitHub App.
          </p>
          <button
            onClick={() => setSetupGuideOpen(true)}
            className="inline-flex items-center gap-1 font-semibold underline text-accent hover:text-accent-hover mt-1"
          >
            View GitHub App Setup Instructions →
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {isStatusLoading ? (
        <div className="p-6 rounded-lg bg-background-card border border-border-subtle animate-pulse space-y-4">
          <div className="h-6 bg-background-subtle rounded w-1/3" />
          <div className="h-10 bg-background-subtle rounded" />
          <div className="h-40 bg-background-subtle rounded" />
        </div>
      ) : isStatusError ? (
        <div className="p-5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>Failed to load GitHub integration status.</span>
          </div>
          <button onClick={() => refetchStatus()} className="font-semibold underline">
            Retry
          </button>
        </div>
      ) : !isConnected ? (
        /* Disconnected State */
        <div className="rounded-lg bg-background-card border border-border-subtle p-8">
          <EmptyState
            icon={GitBranch}
            title="No GitHub repositories connected"
            description="Install the MySDE GitHub App on your GitHub account or organization. Once connected, your repositories will appear here for project association and automated task execution."
            action={
              isConfigured ? (
                <button
                  onClick={() => installMutation.mutate()}
                  disabled={installMutation.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors shadow-subtle"
                >
                  <GitBranch className="w-4 h-4" />
                  {installMutation.isPending ? 'Redirecting...' : 'Install MySDE GitHub App'}
                </button>
              ) : (
                <button
                  onClick={() => setSetupGuideOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-background-subtle border border-border-subtle text-xs font-semibold text-content-primary hover:bg-background-hover transition-colors"
                >
                  Configure GitHub App
                </button>
              )
            }
          />
        </div>
      ) : (
        /* Connected State with Account Header & Repositories */
        <div className="space-y-6">
          {/* Account Card */}
          <div className="p-5 rounded-lg bg-background-card border border-border-subtle flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3.5">
              {status.account_avatar_url ? (
                <img
                  src={status.account_avatar_url}
                  alt={status.account_login}
                  className="w-10 h-10 rounded-full border border-border-subtle"
                />
              ) : (
                <div className="w-10 h-10 rounded-full bg-background-subtle border border-border-subtle flex items-center justify-center text-accent">
                  {status.account_type === 'Organization' ? (
                    <Building2 className="w-5 h-5" />
                  ) : (
                    <User className="w-5 h-5" />
                  )}
                </div>
              )}
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-content-primary">
                    {status.account_login}
                  </h3>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/60 text-emerald-300">
                    Active
                  </span>
                </div>
                <p className="text-xs text-content-muted mt-0.5">
                  GitHub {status.account_type} • Installation ID #{status.installation_id}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-6 text-xs text-content-secondary font-mono border-t sm:border-t-0 pt-3 sm:pt-0 border-border-subtle">
              <div>
                <span className="block text-[11px] text-content-muted uppercase">Selected</span>
                <span className="text-content-primary font-semibold text-sm">
                  {status.selected_repositories} / {status.total_repositories}
                </span>
              </div>
              <div>
                <span className="block text-[11px] text-content-muted uppercase">Last Synced</span>
                <span className="text-content-primary text-xs">
                  {status.last_synced_at
                    ? new Date(status.last_synced_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    : 'Just now'}
                </span>
              </div>
            </div>
          </div>

          {/* Search & Filter Toolbar */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-content-muted absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search repositories by name or organization..."
                className="w-full pl-9 pr-3 py-2 text-xs rounded-md bg-background-card border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none transition-colors"
              />
              {search && (
                <button
                  onClick={() => setSearch('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-content-muted hover:text-content-primary"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="flex items-center bg-background-card border border-border-subtle rounded-md p-0.5 shrink-0">
              {[
                { id: 'all', label: 'All' },
                { id: 'selected', label: 'Selected' },
                { id: 'private', label: 'Private' },
                { id: 'public', label: 'Public' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setFilterType(tab.id)}
                  className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                    filterType === tab.id
                      ? 'bg-accent text-background font-semibold'
                      : 'text-content-secondary hover:text-content-primary'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Repository List Table */}
          {isReposLoading ? (
            <div className="rounded-lg bg-background-card border border-border-subtle p-6 space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-12 bg-background-subtle rounded animate-pulse" />
              ))}
            </div>
          ) : repositories.length === 0 ? (
            <div className="rounded-lg bg-background-card border border-border-subtle p-8">
              <EmptyState
                icon={GitBranch}
                title="No repositories match your criteria"
                description={
                  search
                    ? `No repositories matched "${search}". Try adjusting your search term.`
                    : 'Click "Sync Repositories" to pull fresh repositories from GitHub.'
                }
              />
            </div>
          ) : (
            <div className="rounded-lg bg-background-card border border-border-subtle overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-background-subtle border-b border-border-subtle text-content-muted uppercase tracking-wider font-mono text-[10px]">
                  <tr>
                    <th className="py-3 px-4 w-12 text-center">Active</th>
                    <th className="py-3 px-4">Repository</th>
                    <th className="py-3 px-3">Default Branch</th>
                    <th className="py-3 px-3">Visibility</th>
                    <th className="py-3 px-4 text-right">GitHub Link</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {repositories.map((repo) => (
                    <tr
                      key={repo.id}
                      className={`hover:bg-background-hover/50 transition-colors ${
                        repo.is_selected ? 'bg-accent/5' : ''
                      }`}
                    >
                      <td className="py-3 px-4 text-center">
                        <input
                          type="checkbox"
                          checked={repo.is_selected}
                          onChange={(e) =>
                            toggleMutation.mutate({
                              repoId: repo.id,
                              isSelected: e.target.checked,
                            })
                          }
                          className="w-4 h-4 rounded border-border-subtle text-accent focus:ring-accent bg-background-subtle cursor-pointer"
                        />
                      </td>

                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-content-primary">
                            {repo.full_name}
                          </span>
                          {repo.is_archived && (
                            <span className="text-[9px] font-mono px-1 rounded bg-amber-950/60 text-amber-300 border border-amber-800/60">
                              Archived
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="py-3 px-3 font-mono text-[11px] text-content-secondary">
                        <span className="px-1.5 py-0.5 rounded bg-background-subtle border border-border-subtle">
                          {repo.default_branch}
                        </span>
                      </td>

                      <td className="py-3 px-3">
                        <span
                          className={`inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded border capitalize ${
                            repo.is_private
                              ? 'bg-zinc-800 text-zinc-300 border-zinc-700'
                              : 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60'
                          }`}
                        >
                          {repo.is_private ? (
                            <Lock className="w-3 h-3" />
                          ) : (
                            <Globe className="w-3 h-3" />
                          )}
                          {repo.is_private ? 'Private' : 'Public'}
                        </span>
                      </td>

                      <td className="py-3 px-4 text-right">
                        <a
                          href={`https://github.com/${repo.full_name}`}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-content-muted hover:text-accent transition-colors"
                        >
                          View
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Disconnect Confirmation Modal */}
      {disconnectModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-md p-6 rounded-lg bg-background-card border border-border-strong shadow-card text-left space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-content-primary">
                Disconnect GitHub App?
              </h3>
              <button
                onClick={() => setDisconnectModalOpen(false)}
                className="p-1 rounded text-content-secondary hover:text-content-primary"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-content-secondary leading-relaxed">
              Disconnecting will unbind the GitHub App installation from this workspace. Existing MySDE projects and tasks will not be deleted, but repository synchronization will pause until reconnected.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border-subtle">
              <button
                type="button"
                onClick={() => setDisconnectModalOpen(false)}
                className="px-3.5 py-1.5 rounded-md text-content-secondary hover:text-content-primary text-xs font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => disconnectMutation.mutate()}
                disabled={disconnectMutation.isPending}
                className="px-4 py-2 rounded-md bg-rose-600 text-white text-xs font-semibold hover:bg-rose-500 transition-colors disabled:opacity-50"
              >
                {disconnectMutation.isPending ? 'Disconnecting...' : 'Yes, Disconnect'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* GitHub App Setup Guide Modal */}
      {setupGuideOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-lg p-6 rounded-lg bg-background-card border border-border-strong shadow-card text-left space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-content-primary">
                GitHub App Setup Guide
              </h3>
              <button
                onClick={() => setSetupGuideOpen(false)}
                className="p-1 rounded text-content-secondary hover:text-content-primary"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs text-content-secondary leading-relaxed">
              <p>
                To enable live repository synchronization and automated PR publishing, register a GitHub App in your GitHub Developer Settings:
              </p>

              <ol className="list-decimal pl-5 space-y-1.5 font-mono text-[11px] text-content-primary">
                <li>Go to GitHub → Settings → Developer Settings → GitHub Apps → New GitHub App.</li>
                <li>Set <strong>Callback URL</strong> to: <code className="text-accent bg-background-subtle px-1 py-0.5 rounded">http://localhost:8000/api/v1/integrations/github/callback</code></li>
                <li>Set <strong>Webhook URL</strong> to your local forwarding URL (e.g. via Smee.io or ngrok): <code className="text-accent bg-background-subtle px-1 py-0.5 rounded">http://localhost:8000/api/v1/integrations/github/webhook</code></li>
                <li>Set a <strong>Webhook Secret</strong> and copy it to <code className="text-accent">GITHUB_WEBHOOK_SECRET</code>.</li>
                <li>Under <strong>Repository Permissions</strong>, grant:
                  <ul className="list-disc pl-4 mt-1 font-sans text-xs text-content-secondary">
                    <li><strong>Contents:</strong> Read & Write</li>
                    <li><strong>Pull Requests:</strong> Read & Write</li>
                    <li><strong>Issues:</strong> Read & Write</li>
                    <li><strong>Metadata:</strong> Read-only (mandatory)</li>
                  </ul>
                </li>
                <li>Under <strong>Subscribe to events</strong>, check: <em>Installation</em>, <em>Installation repositories</em>, <em>Issues</em>, <em>Pull request</em>.</li>
                <li>Generate and download a <strong>Private Key</strong> (.pem), and save it in your backend folder.</li>
                <li>Update your <code className="text-accent">backend/.env</code> with:
                  <pre className="mt-1 p-2 rounded bg-background-subtle border border-border-subtle text-[10px] overflow-x-auto">
{`GITHUB_APP_ID=your_app_id
GITHUB_APP_SLUG=your_app_slug
GITHUB_APP_CLIENT_ID=your_client_id
GITHUB_APP_CLIENT_SECRET=your_client_secret
GITHUB_APP_PRIVATE_KEY_PATH=./github-app-private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret
GITHUB_CALLBACK_URL=http://localhost:8000/api/v1/integrations/github/callback`}
                  </pre>
                </li>
              </ol>
            </div>

            <div className="flex justify-end pt-2 border-t border-border-subtle">
              <button
                onClick={() => setSetupGuideOpen(false)}
                className="px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors"
              >
                Got It
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
