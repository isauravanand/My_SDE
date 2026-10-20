import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  FolderGit2,
  GitBranch,
  Plus,
  Search,
  Archive,
  RefreshCw,
  AlertCircle,
  X,
  ArrowRight,
  CheckCircle2,
  ListTodo,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { api, ApiError } from '../lib/api';
import { EmptyState } from '../components/common/EmptyState';

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const { activeWorkspace } = useAuth();
  const workspaceId = activeWorkspace?.id;

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all'); // 'all' | 'active' | 'archived'
  const [createModalOpen, setCreateModalOpen] = useState(false);

  // New Project Form State
  const [projectName, setProjectName] = useState('');
  const [projectSlug, setProjectSlug] = useState('');
  const [projectDescription, setProjectDescription] = useState('');
  const [selectedRepoId, setSelectedRepoId] = useState('');
  const [formError, setFormError] = useState('');

  // Fetch Connected Repositories for Selection
  const { data: reposData } = useQuery({
    queryKey: ['github-repositories', workspaceId, 'for-projects'],
    queryFn: () => api.getGitHubRepositories({ workspaceId }),
    enabled: !!workspaceId,
  });
  const connectedRepos = reposData?.items || [];

  // Fetch Projects Query
  const {
    data: projects = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['projects', workspaceId, statusFilter, search],
    queryFn: () =>
      api.getProjects({
        workspaceId,
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search.trim() || undefined,
      }),
    enabled: !!workspaceId,
  });

  // Invalidate relevant queries after mutations
  const invalidateProjectData = async () => {
    await queryClient.invalidateQueries({ queryKey: ['projects', workspaceId] });
    await queryClient.invalidateQueries({ queryKey: ['dashboard', 'summary', workspaceId] });
    await queryClient.invalidateQueries({ queryKey: ['activity', workspaceId] });
  };

  // Create Project Mutation
  const createMutation = useMutation({
    mutationFn: (payload) => api.createProject(payload),
    onSuccess: async () => {
      await invalidateProjectData();
      setCreateModalOpen(false);
      setProjectName('');
      setProjectSlug('');
      setProjectDescription('');
      setSelectedRepoId('');
      setFormError('');
    },
    onError: (err) => {
      setFormError(err.message || 'Failed to create project');
    },
  });

  // Archive Project Mutation
  const archiveMutation = useMutation({
    mutationFn: (projectId) => api.archiveProject(projectId),
    onSuccess: invalidateProjectData,
  });

  // Restore Project Mutation
  const restoreMutation = useMutation({
    mutationFn: (projectId) => api.restoreProject(projectId),
    onSuccess: invalidateProjectData,
  });

  const handleNameChange = (e) => {
    const val = e.target.value;
    setProjectName(val);
    // Auto-generate slug if slug wasn't manually typed or is based on old name
    const generatedSlug = val
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '');
    setProjectSlug(generatedSlug);
  };

  const handleCreateSubmit = (e) => {
    e.preventDefault();
    setFormError('');
    if (!projectName.trim()) {
      setFormError('Project name is required');
      return;
    }
    if (!projectSlug.trim()) {
      setFormError('Project slug is required');
      return;
    }

    createMutation.mutate({
      workspace_id: workspaceId,
      name: projectName.trim(),
      slug: projectSlug.trim().toLowerCase(),
      description: projectDescription.trim() || null,
      repository_id: selectedRepoId || null,
    });
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-content-primary">Projects</h1>
          <p className="text-sm text-content-secondary mt-1">
            Manage projects, associate repositories, and configure runtime environments in{' '}
            <span className="text-content-primary font-medium">{activeWorkspace?.name}</span>.
          </p>
        </div>
        <button
          onClick={() => {
            setFormError('');
            setSelectedRepoId('');
            setCreateModalOpen(true);
          }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors shadow-subtle shrink-0"
        >
          <Plus className="w-4 h-4" />
          New Project
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-content-muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search projects by name or description..."
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

        {/* Status Filter Tabs */}
        <div className="flex items-center bg-background-card border border-border-subtle rounded-md p-0.5 shrink-0">
          {[
            { id: 'all', label: 'All' },
            { id: 'active', label: 'Active' },
            { id: 'archived', label: 'Archived' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                statusFilter === tab.id
                  ? 'bg-accent text-background font-semibold'
                  : 'text-content-secondary hover:text-content-primary'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Projects Grid or States */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="p-5 rounded-lg bg-background-card border border-border-subtle animate-pulse space-y-3"
            >
              <div className="h-4 bg-background-subtle rounded w-3/4" />
              <div className="h-3 bg-background-subtle rounded w-full" />
              <div className="h-3 bg-background-subtle rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : isError ? (
        <div className="p-5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error?.message || 'Failed to load projects'}</span>
          </div>
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1 font-semibold hover:text-rose-300"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry
          </button>
        </div>
      ) : projects.length === 0 ? (
        <div className="rounded-lg bg-background-card border border-border-subtle p-8">
          <EmptyState
            icon={FolderGit2}
            title={
              search
                ? 'No matching projects found'
                : statusFilter === 'archived'
                ? 'No archived projects'
                : 'No projects in this workspace'
            }
            description={
              search
                ? `No projects matched "${search}". Try adjusting your search term.`
                : 'Create projects to organize codebases, tasks, and automated engineering pipelines.'
            }
            action={
              !search && statusFilter !== 'archived' ? (
                <button
                  onClick={() => {
                    setSelectedRepoId('');
                    setCreateModalOpen(true);
                  }}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Create Project
                </button>
              ) : null
            }
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => {
            const isArchived = project.status === 'archived';
            const linkedRepo = connectedRepos.find((r) => r.id === project.repository_id);
            return (
              <div
                key={project.id}
                className={`flex flex-col justify-between p-5 rounded-lg bg-background-card border transition-all ${
                  isArchived
                    ? 'border-border-subtle opacity-70'
                    : 'border-border-subtle hover:border-border-strong'
                }`}
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <Link
                      to={`/projects/${project.id}`}
                      className="text-sm font-semibold text-content-primary hover:text-accent transition-colors truncate"
                    >
                      {project.name}
                    </Link>
                    <span
                      className={`text-[10px] font-mono px-2 py-0.5 rounded capitalize shrink-0 ${
                        isArchived
                          ? 'bg-amber-950/60 text-amber-300 border border-amber-800/60'
                          : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/60'
                      }`}
                    >
                      {project.status}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 mb-2 text-xs font-mono text-content-muted">
                    <span>slug: {project.slug}</span>
                    {linkedRepo && (
                      <span className="inline-flex items-center gap-1 text-[10px] text-accent font-medium px-1.5 py-0.5 rounded bg-accent/10 border border-accent/20 truncate max-w-[150px]">
                        <GitBranch className="w-2.5 h-2.5 shrink-0" />
                        {linkedRepo.name}
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-content-secondary line-clamp-2 leading-relaxed mb-4">
                    {project.description || 'No description provided.'}
                  </p>
                </div>

                <div className="pt-3 border-t border-border-subtle flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5 text-content-muted">
                    <ListTodo className="w-3.5 h-3.5 text-accent" />
                    <span>{project.task_count ?? 0} tasks</span>
                  </div>

                  <div className="flex items-center gap-2">
                    {isArchived ? (
                      <button
                        onClick={() => restoreMutation.mutate(project.id)}
                        disabled={restoreMutation.isPending}
                        className="inline-flex items-center gap-1 text-[11px] font-medium text-sky-400 hover:text-sky-300 p-1 transition-colors"
                        title="Restore project"
                      >
                        <RefreshCw className="w-3 h-3" />
                        Restore
                      </button>
                    ) : (
                      <button
                        onClick={() => archiveMutation.mutate(project.id)}
                        disabled={archiveMutation.isPending}
                        className="inline-flex items-center gap-1 text-[11px] font-medium text-content-muted hover:text-amber-400 p-1 transition-colors"
                        title="Archive project"
                      >
                        <Archive className="w-3 h-3" />
                        Archive
                      </button>
                    )}

                    <Link
                      to={`/projects/${project.id}`}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-content-primary hover:text-accent p-1 transition-colors"
                    >
                      View
                      <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Project Modal */}
      {createModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-md p-6 rounded-lg bg-background-card border border-border-strong shadow-card text-left">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-content-primary">Create New Project</h3>
              <button
                onClick={() => setCreateModalOpen(false)}
                className="p-1 rounded-md text-content-secondary hover:text-content-primary hover:bg-background-subtle"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {formError && (
              <div className="p-3 mb-4 rounded bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1">
                  Project Name *
                </label>
                <input
                  type="text"
                  required
                  value={projectName}
                  onChange={handleNameChange}
                  placeholder="e.g. Core API Service"
                  className="w-full px-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1">
                  Slug (unique within workspace) *
                </label>
                <input
                  type="text"
                  required
                  value={projectSlug}
                  onChange={(e) => setProjectSlug(e.target.value.toLowerCase())}
                  placeholder="e.g. core-api-service"
                  className="w-full px-3 py-2 text-xs font-mono rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1">
                  Connected GitHub Repository (optional)
                </label>
                <select
                  value={selectedRepoId}
                  onChange={(e) => setSelectedRepoId(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary outline-none transition-colors"
                >
                  <option value="">No repository connected</option>
                  {connectedRepos.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.full_name} ({r.default_branch})
                    </option>
                  ))}
                </select>
                {connectedRepos.length === 0 && (
                  <p className="text-[11px] text-content-muted mt-1">
                    Connect your GitHub App on the Repositories page to link repositories.
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1">
                  Description
                </label>
                <textarea
                  rows={3}
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  placeholder="Brief summary of what this project encompasses..."
                  className="w-full px-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none transition-colors resize-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-border-subtle">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="px-3.5 py-1.5 rounded-md text-content-secondary hover:text-content-primary text-xs font-medium transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors disabled:opacity-50"
                >
                  {createMutation.isPending ? 'Creating...' : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
