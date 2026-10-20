import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  FolderGit2,
  Plus,
  Search,
  Archive,
  RefreshCw,
  AlertCircle,
  X,
  CheckCircle2,
  Clock,
  ListTodo,
  Calendar,
  GitBranch,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { api, ApiError } from '../lib/api';
import { EmptyState } from '../components/common/EmptyState';

const STATUS_OPTIONS = ['backlog', 'todo', 'in_progress', 'in_review', 'done', 'cancelled'];
const PRIORITY_OPTIONS = ['low', 'medium', 'high', 'critical'];
const TYPE_OPTIONS = ['feature', 'bug', 'improvement', 'chore'];

const STATUS_BADGES = {
  backlog: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  todo: 'bg-blue-950/60 text-blue-300 border-blue-800/60',
  in_progress: 'bg-amber-950/60 text-amber-300 border-amber-800/60',
  in_review: 'bg-purple-950/60 text-purple-300 border-purple-800/60',
  done: 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60',
  cancelled: 'bg-rose-950/60 text-rose-300 border-rose-800/60',
};

const PRIORITY_BADGES = {
  low: 'text-zinc-400',
  medium: 'text-sky-400',
  high: 'text-amber-400 font-semibold',
  critical: 'text-rose-400 font-bold',
};

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { activeWorkspace } = useAuth();
  const workspaceId = activeWorkspace?.id;

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [createTaskModalOpen, setCreateTaskModalOpen] = useState(false);

  // New Task form state
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDescription, setTaskDescription] = useState('');
  const [taskStatus, setTaskStatus] = useState('todo');
  const [taskPriority, setTaskPriority] = useState('medium');
  const [taskType, setTaskType] = useState('feature');
  const [formError, setFormError] = useState('');

  // 1. Fetch Project Query
  const {
    data: project,
    isLoading: isProjectLoading,
    isError: isProjectError,
    error: projectError,
  } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.getProject(projectId),
    enabled: !!projectId,
  });

  // 1b. Fetch Connected Repositories
  const { data: reposData } = useQuery({
    queryKey: ['github-repositories', workspaceId, 'for-project-detail'],
    queryFn: () => api.getGitHubRepositories({ workspaceId }),
    enabled: !!workspaceId,
  });
  const connectedRepos = reposData?.items || [];
  const linkedRepo = connectedRepos.find((r) => r.id === project?.repository_id);

  // 2. Fetch Project Tasks Query
  const {
    data: tasksData,
    isLoading: isTasksLoading,
    isError: isTasksError,
    refetch: refetchTasks,
  } = useQuery({
    queryKey: ['project-tasks', projectId, statusFilter, priorityFilter, search],
    queryFn: () =>
      api.getProjectTasks(projectId, {
        status: statusFilter || undefined,
        priority: priorityFilter || undefined,
        search: search.trim() || undefined,
      }),
    enabled: !!projectId,
  });

  const tasks = tasksData?.items || [];
  const isArchived = project?.status === 'archived';

  // Invalidate queries helper
  const invalidateAll = async () => {
    await queryClient.invalidateQueries({ queryKey: ['project', projectId] });
    await queryClient.invalidateQueries({ queryKey: ['project-tasks', projectId] });
    await queryClient.invalidateQueries({ queryKey: ['projects', workspaceId] });
    await queryClient.invalidateQueries({ queryKey: ['tasks', workspaceId] });
    await queryClient.invalidateQueries({ queryKey: ['dashboard', 'summary', workspaceId] });
    await queryClient.invalidateQueries({ queryKey: ['activity', workspaceId] });
  };

  // Create Task Mutation
  const createTaskMutation = useMutation({
    mutationFn: (payload) => api.createTask(projectId, payload),
    onSuccess: async () => {
      await invalidateAll();
      setCreateTaskModalOpen(false);
      setTaskTitle('');
      setTaskDescription('');
      setTaskStatus('todo');
      setTaskPriority('medium');
      setTaskType('feature');
      setFormError('');
    },
    onError: (err) => {
      setFormError(err.message || 'Failed to create task');
    },
  });

  // Archive Project Mutation
  const archiveProjectMutation = useMutation({
    mutationFn: () => api.archiveProject(projectId),
    onSuccess: invalidateAll,
  });

  // Restore Project Mutation
  const restoreProjectMutation = useMutation({
    mutationFn: () => api.restoreProject(projectId),
    onSuccess: invalidateAll,
  });

  const handleCreateTaskSubmit = (e) => {
    e.preventDefault();
    setFormError('');
    if (!taskTitle.trim()) {
      setFormError('Task title is required');
      return;
    }
    createTaskMutation.mutate({
      title: taskTitle.trim(),
      description: taskDescription.trim() || null,
      status: taskStatus,
      priority: taskPriority,
      task_type: taskType,
    });
  };

  if (isProjectLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-6 bg-background-card rounded w-1/4" />
        <div className="h-32 bg-background-card rounded" />
      </div>
    );
  }

  if (isProjectError || !project) {
    return (
      <div className="p-6 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <AlertCircle className="w-5 h-5 shrink-0" />
          Project not found or access denied.
        </div>
        <p className="text-xs text-rose-300">
          {projectError?.message || 'The requested project could not be loaded.'}
        </p>
        <Link
          to="/projects"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-background-subtle text-content-primary text-xs font-semibold hover:bg-background-hover transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Projects
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Navigation & Actions */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate('/projects')}
          className="inline-flex items-center gap-1.5 text-xs text-content-secondary hover:text-content-primary transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Projects
        </button>

        <div className="flex items-center gap-2">
          {isArchived ? (
            <button
              onClick={() => restoreProjectMutation.mutate()}
              disabled={restoreProjectMutation.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-sky-950/60 border border-sky-800/60 text-sky-300 text-xs font-semibold hover:bg-sky-900/60 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Restore Project
            </button>
          ) : (
            <button
              onClick={() => archiveProjectMutation.mutate()}
              disabled={archiveProjectMutation.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-background-card border border-border-subtle text-content-secondary hover:text-amber-400 text-xs font-semibold transition-colors"
            >
              <Archive className="w-3.5 h-3.5" />
              Archive Project
            </button>
          )}

          {!isArchived && (
            <button
              onClick={() => {
                setFormError('');
                setCreateTaskModalOpen(true);
              }}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors shadow-subtle"
            >
              <Plus className="w-4 h-4" />
              New Task
            </button>
          )}
        </div>
      </div>

      {/* Project Overview Card */}
      <div className="p-6 rounded-lg bg-background-card border border-border-subtle">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold tracking-tight text-content-primary">
                {project.name}
              </h1>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded capitalize ${
                  isArchived
                    ? 'bg-amber-950/60 text-amber-300 border border-amber-800/60'
                    : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/60'
                }`}
              >
                {project.status}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1 text-xs font-mono text-content-muted">
              <span>slug: {project.slug}</span>
              {linkedRepo && (
                <a
                  href={`https://github.com/${linkedRepo.full_name}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] text-accent font-medium px-2 py-0.5 rounded bg-accent/10 border border-accent/20 hover:bg-accent/20 transition-colors"
                >
                  <GitBranch className="w-3 h-3" />
                  {linkedRepo.full_name}
                </a>
              )}
            </div>
            {project.description && (
              <p className="text-xs text-content-secondary mt-3 leading-relaxed max-w-2xl">
                {project.description}
              </p>
            )}
          </div>

          <div className="flex sm:flex-col items-center sm:items-end gap-2 text-xs text-content-muted font-mono shrink-0">
            <span className="flex items-center gap-1.5">
              <ListTodo className="w-3.5 h-3.5 text-accent" />
              {project.task_count ?? 0} tasks
            </span>
            <span className="flex items-center gap-1.5 text-[11px]">
              <Calendar className="w-3 h-3" />
              Created {new Date(project.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>

        {isArchived && (
          <div className="mt-4 p-3 rounded bg-amber-950/40 border border-amber-800/40 text-amber-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            This project is archived. To add new tasks, restore the project first.
          </div>
        )}
      </div>

      {/* Project Tasks Section */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-content-primary">
            Project Tasks ({tasksData?.total ?? 0})
          </h2>

          <div className="flex flex-wrap items-center gap-2">
            {/* Search */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-content-muted absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter tasks..."
                className="pl-8 pr-2.5 py-1 text-xs rounded bg-background-card border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none"
              />
            </div>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="py-1 px-2 text-xs rounded bg-background-card border border-border-subtle text-content-secondary focus:border-accent outline-none"
            >
              <option value="">All Statuses</option>
              {STATUS_OPTIONS.map((st) => (
                <option key={st} value={st}>
                  {st.replace('_', ' ')}
                </option>
              ))}
            </select>

            {/* Priority Filter */}
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value)}
              className="py-1 px-2 text-xs rounded bg-background-card border border-border-subtle text-content-secondary focus:border-accent outline-none"
            >
              <option value="">All Priorities</option>
              {PRIORITY_OPTIONS.map((pr) => (
                <option key={pr} value={pr}>
                  {pr}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Tasks List */}
        {isTasksLoading ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="h-14 rounded-lg bg-background-card border border-border-subtle animate-pulse"
              />
            ))}
          </div>
        ) : tasks.length === 0 ? (
          <div className="rounded-lg bg-background-card border border-border-subtle p-8">
            <EmptyState
              icon={CheckCircle2}
              title={
                search || statusFilter || priorityFilter
                  ? 'No tasks match your filters'
                  : 'No tasks in this project'
              }
              description={
                search || statusFilter || priorityFilter
                  ? 'Try clearing or relaxing your search and filter criteria.'
                  : 'Add engineering tasks to break down features, bugs, or refactoring.'
              }
              action={
                !isArchived && !search && !statusFilter && !priorityFilter ? (
                  <button
                    onClick={() => setCreateTaskModalOpen(true)}
                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Create Task
                  </button>
                ) : null
              }
            />
          </div>
        ) : (
          <div className="rounded-lg bg-background-card border border-border-subtle divide-y divide-border-subtle overflow-hidden">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="p-4 flex items-center justify-between gap-4 hover:bg-background-hover/40 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-content-primary truncate">
                      {task.title}
                    </span>
                    {task.archived_at && (
                      <span className="text-[10px] font-mono px-1 rounded bg-amber-950/60 text-amber-300 border border-amber-800/60">
                        Archived
                      </span>
                    )}
                  </div>
                  {task.description && (
                    <p className="text-[11px] text-content-secondary truncate mt-0.5 max-w-xl">
                      {task.description}
                    </p>
                  )}
                  <div className="flex items-center gap-2 mt-1 text-[11px] text-content-muted">
                    <span className="font-mono text-content-secondary uppercase text-[10px]">
                      {task.task_type}
                    </span>
                    <span>•</span>
                    <span className={PRIORITY_BADGES[task.priority] || 'text-content-muted'}>
                      {task.priority}
                    </span>
                    <span>•</span>
                    <span>Created {new Date(task.created_at).toLocaleDateString()}</span>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <span
                    className={`text-[11px] font-mono px-2.5 py-0.5 rounded border capitalize ${
                      STATUS_BADGES[task.status] || 'bg-background-subtle text-content-muted'
                    }`}
                  >
                    {task.status.replace('_', ' ')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Task Modal */}
      {createTaskModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-lg p-6 rounded-lg bg-background-card border border-border-strong shadow-card text-left">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-content-primary">
                Create Task in {project.name}
              </h3>
              <button
                onClick={() => setCreateTaskModalOpen(false)}
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

            <form onSubmit={handleCreateTaskSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1">
                  Title *
                </label>
                <input
                  type="text"
                  required
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder="e.g. Implement webhook signature verification"
                  className="w-full px-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1">
                  Description
                </label>
                <textarea
                  rows={3}
                  value={taskDescription}
                  onChange={(e) => setTaskDescription(e.target.value)}
                  placeholder="Specification, acceptance criteria, or relevant context..."
                  className="w-full px-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none transition-colors resize-none"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-content-secondary mb-1">
                    Status
                  </label>
                  <select
                    value={taskStatus}
                    onChange={(e) => setTaskStatus(e.target.value)}
                    className="w-full px-2.5 py-1.5 text-xs rounded-md bg-background-subtle border border-border-subtle text-content-primary focus:border-accent outline-none"
                  >
                    {STATUS_OPTIONS.map((st) => (
                      <option key={st} value={st}>
                        {st.replace('_', ' ')}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-content-secondary mb-1">
                    Priority
                  </label>
                  <select
                    value={taskPriority}
                    onChange={(e) => setTaskPriority(e.target.value)}
                    className="w-full px-2.5 py-1.5 text-xs rounded-md bg-background-subtle border border-border-subtle text-content-primary focus:border-accent outline-none"
                  >
                    {PRIORITY_OPTIONS.map((pr) => (
                      <option key={pr} value={pr}>
                        {pr}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-content-secondary mb-1">
                    Type
                  </label>
                  <select
                    value={taskType}
                    onChange={(e) => setTaskType(e.target.value)}
                    className="w-full px-2.5 py-1.5 text-xs rounded-md bg-background-subtle border border-border-subtle text-content-primary focus:border-accent outline-none"
                  >
                    {TYPE_OPTIONS.map((tp) => (
                      <option key={tp} value={tp}>
                        {tp}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-border-subtle">
                <button
                  type="button"
                  onClick={() => setCreateTaskModalOpen(false)}
                  className="px-3.5 py-1.5 rounded-md text-content-secondary hover:text-content-primary text-xs font-medium transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createTaskMutation.isPending}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors disabled:opacity-50"
                >
                  {createTaskMutation.isPending ? 'Creating...' : 'Create Task'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
