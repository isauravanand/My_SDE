import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CheckSquare,
  Plus,
  Search,
  Filter,
  Archive,
  RefreshCw,
  AlertCircle,
  X,
  ChevronLeft,
  ChevronRight,
  Eye,
  Edit2,
  Calendar,
  FolderGit2,
  User,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { api } from '../lib/api';
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

const PAGE_SIZE = 10;

export function TasksPage() {
  const queryClient = useQueryClient();
  const { activeWorkspace } = useAuth();
  const workspaceId = activeWorkspace?.id;

  // Filter & Pagination States
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [page, setPage] = useState(0);

  // Modals & Panels
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [detailTask, setDetailTask] = useState(null);
  const [editTask, setEditTask] = useState(null);

  // Create Task Form State
  const [newProjectId, setNewProjectId] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newStatus, setNewStatus] = useState('todo');
  const [newPriority, setNewPriority] = useState('medium');
  const [newType, setNewType] = useState('feature');
  const [newAssigneeId, setNewAssigneeId] = useState('');
  const [formError, setFormError] = useState('');

  // 1. Fetch Workspace Tasks Query
  const {
    data: tasksData,
    isLoading: isTasksLoading,
    isError: isTasksError,
    error: tasksError,
    refetch: refetchTasks,
  } = useQuery({
    queryKey: ['tasks', workspaceId, statusFilter, priorityFilter, search, page],
    queryFn: () =>
      api.getWorkspaceTasks({
        workspaceId,
        status: statusFilter || undefined,
        priority: priorityFilter || undefined,
        search: search.trim() || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    enabled: !!workspaceId,
  });

  // 2. Fetch Projects for Creation Dropdown & Name Resolution
  const { data: projects = [] } = useQuery({
    queryKey: ['projects', workspaceId, 'all-for-tasks'],
    queryFn: () => api.getProjects({ workspaceId }),
    enabled: !!workspaceId,
  });

  // 3. Fetch Workspace Members for Assignee Dropdown
  const { data: members = [] } = useQuery({
    queryKey: ['workspace-members', workspaceId],
    queryFn: () => api.getWorkspaceMembers(workspaceId),
    enabled: !!workspaceId,
  });

  const tasks = tasksData?.items || [];
  const totalTasks = tasksData?.total || 0;
  const totalPages = Math.ceil(totalTasks / PAGE_SIZE);

  const invalidateTaskData = async () => {
    await queryClient.invalidateQueries({ queryKey: ['tasks', workspaceId] });
    await queryClient.invalidateQueries({ queryKey: ['project-tasks'] });
    await queryClient.invalidateQueries({ queryKey: ['dashboard', 'summary', workspaceId] });
    await queryClient.invalidateQueries({ queryKey: ['activity', workspaceId] });
  };

  // Create Task Mutation
  const createMutation = useMutation({
    mutationFn: (payload) => api.createTask(newProjectId, payload),
    onSuccess: async () => {
      await invalidateTaskData();
      setCreateModalOpen(false);
      setNewTitle('');
      setNewDescription('');
      setNewStatus('todo');
      setNewPriority('medium');
      setNewType('feature');
      setNewAssigneeId('');
      setFormError('');
    },
    onError: (err) => {
      setFormError(err.message || 'Failed to create task');
    },
  });

  // Update Task Mutation
  const updateMutation = useMutation({
    mutationFn: ({ taskId, payload }) => api.updateTask(taskId, payload),
    onSuccess: async (updated) => {
      await invalidateTaskData();
      if (detailTask && detailTask.id === updated.id) {
        setDetailTask(updated);
      }
      setEditTask(null);
    },
    onError: (err) => {
      alert(`Update failed: ${err.message}`);
    },
  });

  // Archive Task Mutation
  const archiveMutation = useMutation({
    mutationFn: (taskId) => api.archiveTask(taskId),
    onSuccess: async (updated) => {
      await invalidateTaskData();
      if (detailTask && detailTask.id === updated.id) {
        setDetailTask(updated);
      }
    },
  });

  // Restore Task Mutation
  const restoreMutation = useMutation({
    mutationFn: (taskId) => api.restoreTask(taskId),
    onSuccess: async (updated) => {
      await invalidateTaskData();
      if (detailTask && detailTask.id === updated.id) {
        setDetailTask(updated);
      }
    },
  });

  const handleCreateSubmit = (e) => {
    e.preventDefault();
    setFormError('');
    if (!newProjectId) {
      setFormError('Please select a project');
      return;
    }
    if (!newTitle.trim()) {
      setFormError('Task title is required');
      return;
    }

    createMutation.mutate({
      title: newTitle.trim(),
      description: newDescription.trim() || null,
      status: newStatus,
      priority: newPriority,
      task_type: newType,
      assignee_id: newAssigneeId || null,
    });
  };

  const getProjectName = (projectId) => {
    const proj = projects.find((p) => p.id === projectId);
    return proj ? proj.name : 'Unknown Project';
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-content-primary">Tasks</h1>
          <p className="text-sm text-content-secondary mt-1">
            Track, assign, and review autonomous software engineering tasks across{' '}
            <span className="text-content-primary font-medium">{activeWorkspace?.name}</span>.
          </p>
        </div>
        <button
          onClick={() => {
            setFormError('');
            if (projects.length > 0 && !newProjectId) {
              setNewProjectId(projects.find((p) => p.status === 'active')?.id || projects[0].id);
            }
            setCreateModalOpen(true);
          }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors shadow-subtle shrink-0"
        >
          <Plus className="w-4 h-4" />
          New Task
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        {/* Search Input */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-content-muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder="Search tasks by title or description..."
            className="w-full pl-9 pr-3 py-2 text-xs rounded-md bg-background-card border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none transition-colors"
          />
          {search && (
            <button
              onClick={() => {
                setSearch('');
                setPage(0);
              }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-content-muted hover:text-content-primary"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Status Filter */}
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(0);
          }}
          className="py-2 px-3 text-xs rounded-md bg-background-card border border-border-subtle text-content-secondary focus:border-accent outline-none shrink-0"
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
          onChange={(e) => {
            setPriorityFilter(e.target.value);
            setPage(0);
          }}
          className="py-2 px-3 text-xs rounded-md bg-background-card border border-border-subtle text-content-secondary focus:border-accent outline-none shrink-0"
        >
          <option value="">All Priorities</option>
          {PRIORITY_OPTIONS.map((pr) => (
            <option key={pr} value={pr}>
              {pr}
            </option>
          ))}
        </select>
      </div>

      {/* Tasks Table / Content */}
      {isTasksLoading ? (
        <div className="rounded-lg bg-background-card border border-border-subtle p-6 space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-background-subtle rounded animate-pulse" />
          ))}
        </div>
      ) : isTasksError ? (
        <div className="p-5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{tasksError?.message || 'Failed to load tasks'}</span>
          </div>
          <button
            onClick={() => refetchTasks()}
            className="flex items-center gap-1 font-semibold hover:text-rose-300"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry
          </button>
        </div>
      ) : tasks.length === 0 ? (
        <div className="rounded-lg bg-background-card border border-border-subtle p-8">
          <EmptyState
            icon={CheckSquare}
            title={
              search || statusFilter || priorityFilter
                ? 'No matching tasks found'
                : 'No tasks in this workspace'
            }
            description={
              search || statusFilter || priorityFilter
                ? 'Try adjusting your search query or filters.'
                : 'Create tasks to track features, fixes, and engineering deliverables.'
            }
            action={
              !search && !statusFilter && !priorityFilter ? (
                <button
                  onClick={() => setCreateModalOpen(true)}
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
        <div className="rounded-lg bg-background-card border border-border-subtle overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-background-subtle border-b border-border-subtle text-content-muted uppercase tracking-wider font-mono text-[10px]">
                <tr>
                  <th className="py-3 px-4">Task</th>
                  <th className="py-3 px-3">Project</th>
                  <th className="py-3 px-3">Type</th>
                  <th className="py-3 px-3">Priority</th>
                  <th className="py-3 px-3">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {tasks.map((task) => (
                  <tr
                    key={task.id}
                    className="hover:bg-background-hover/50 transition-colors cursor-pointer"
                    onClick={() => setDetailTask(task)}
                  >
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-content-primary">
                          {task.title}
                        </span>
                        {task.archived_at && (
                          <span className="text-[9px] font-mono px-1 rounded bg-amber-950/60 text-amber-300 border border-amber-800/60">
                            Archived
                          </span>
                        )}
                      </div>
                      {task.description && (
                        <p className="text-[11px] text-content-secondary truncate max-w-md mt-0.5">
                          {task.description}
                        </p>
                      )}
                    </td>

                    <td className="py-3 px-3 text-content-secondary font-mono text-[11px] whitespace-nowrap">
                      {getProjectName(task.project_id)}
                    </td>

                    <td className="py-3 px-3 uppercase font-mono text-[10px] text-content-muted whitespace-nowrap">
                      {task.task_type}
                    </td>

                    <td className="py-3 px-3 whitespace-nowrap">
                      <span className={PRIORITY_BADGES[task.priority] || 'text-content-muted'}>
                        {task.priority}
                      </span>
                    </td>

                    <td className="py-3 px-3 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <select
                        value={task.status}
                        onChange={(e) =>
                          updateMutation.mutate({
                            taskId: task.id,
                            payload: { status: e.target.value },
                          })
                        }
                        className={`text-[11px] font-mono px-2 py-0.5 rounded border capitalize bg-transparent cursor-pointer outline-none ${
                          STATUS_BADGES[task.status] || 'text-content-muted'
                        }`}
                      >
                        {STATUS_OPTIONS.map((st) => (
                          <option key={st} value={st} className="bg-background-card text-content-primary">
                            {st.replace('_', ' ')}
                          </option>
                        ))}
                      </select>
                    </td>

                    <td className="py-3 px-4 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          onClick={() => setDetailTask(task)}
                          className="p-1 rounded text-content-muted hover:text-content-primary hover:bg-background-subtle transition-colors"
                          title="View details"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setEditTask(task)}
                          className="p-1 rounded text-content-muted hover:text-accent hover:bg-background-subtle transition-colors"
                          title="Edit task"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        {task.archived_at ? (
                          <button
                            onClick={() => restoreMutation.mutate(task.id)}
                            className="p-1 rounded text-sky-400 hover:text-sky-300 hover:bg-background-subtle transition-colors"
                            title="Restore task"
                          >
                            <RefreshCw className="w-3.5 h-3.5" />
                          </button>
                        ) : (
                          <button
                            onClick={() => archiveMutation.mutate(task.id)}
                            className="p-1 rounded text-content-muted hover:text-amber-400 hover:bg-background-subtle transition-colors"
                            title="Archive task"
                          >
                            <Archive className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          {totalPages > 1 && (
            <div className="p-3 bg-background-subtle border-t border-border-subtle flex items-center justify-between text-xs text-content-secondary">
              <span>
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalTasks)} of{' '}
                {totalTasks} tasks
              </span>
              <div className="flex items-center gap-2">
                <button
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                  className="p-1.5 rounded bg-background-card border border-border-subtle text-content-primary disabled:opacity-30 disabled:cursor-not-allowed hover:bg-background-hover transition-colors"
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                </button>
                <span className="font-mono text-xs text-content-primary">
                  {page + 1} / {totalPages}
                </span>
                <button
                  disabled={page + 1 >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="p-1.5 rounded bg-background-card border border-border-subtle text-content-primary disabled:opacity-30 disabled:cursor-not-allowed hover:bg-background-hover transition-colors"
                >
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Task Detail Modal */}
      {detailTask && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-lg p-6 rounded-lg bg-background-card border border-border-strong shadow-card text-left space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-background-subtle text-content-muted">
                  {detailTask.task_type}
                </span>
                <h3 className="text-base font-semibold text-content-primary mt-1.5">
                  {detailTask.title}
                </h3>
              </div>
              <button
                onClick={() => setDetailTask(null)}
                className="p-1 rounded-md text-content-secondary hover:text-content-primary hover:bg-background-subtle"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 p-3 bg-background-subtle rounded-md border border-border-subtle text-xs">
              <div>
                <span className="text-content-muted text-[11px] block">Project</span>
                <span className="font-medium text-content-primary">
                  {getProjectName(detailTask.project_id)}
                </span>
              </div>
              <div>
                <span className="text-content-muted text-[11px] block">Status</span>
                <span className="font-medium text-content-primary capitalize">
                  {detailTask.status.replace('_', ' ')}
                </span>
              </div>
              <div>
                <span className="text-content-muted text-[11px] block">Priority</span>
                <span className={`font-medium ${PRIORITY_BADGES[detailTask.priority]}`}>
                  {detailTask.priority}
                </span>
              </div>
              <div>
                <span className="text-content-muted text-[11px] block">Completed At</span>
                <span className="font-mono text-content-primary">
                  {detailTask.completed_at
                    ? new Date(detailTask.completed_at).toLocaleString()
                    : 'Not completed'}
                </span>
              </div>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-content-muted uppercase tracking-wider mb-1">
                Description
              </h4>
              <p className="text-xs text-content-secondary leading-relaxed bg-background-subtle p-3 rounded border border-border-subtle whitespace-pre-wrap">
                {detailTask.description || 'No description provided.'}
              </p>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-border-subtle text-xs text-content-muted">
              <span>Created {new Date(detailTask.created_at).toLocaleString()}</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    setEditTask(detailTask);
                    setDetailTask(null);
                  }}
                  className="px-3 py-1.5 rounded bg-background-subtle text-content-primary hover:bg-background-hover transition-colors font-medium"
                >
                  Edit
                </button>
                <button
                  onClick={() => setDetailTask(null)}
                  className="px-3 py-1.5 rounded bg-accent text-background font-semibold hover:bg-accent-hover transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit Task Modal */}
      {editTask && (
        <EditTaskModal
          task={editTask}
          members={members}
          onClose={() => setEditTask(null)}
          onSave={(payload) =>
            updateMutation.mutate({ taskId: editTask.id, payload })
          }
          isPending={updateMutation.isPending}
        />
      )}

      {/* Create Task Modal */}
      {createModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-lg p-6 rounded-lg bg-background-card border border-border-strong shadow-card text-left">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-content-primary">Create New Task</h3>
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
                  Parent Project *
                </label>
                <select
                  required
                  value={newProjectId}
                  onChange={(e) => setNewProjectId(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle text-content-primary focus:border-accent outline-none"
                >
                  <option value="">Select a project...</option>
                  {projects
                    .filter((p) => p.status === 'active')
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                </select>
                {projects.filter((p) => p.status === 'active').length === 0 && (
                  <p className="text-[11px] text-amber-400 mt-1">
                    No active projects in this workspace. Please create an active project first.
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1">
                  Title *
                </label>
                <input
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Implement webhook authentication"
                  className="w-full px-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1">
                  Description
                </label>
                <textarea
                  rows={3}
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
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
                    value={newStatus}
                    onChange={(e) => setNewStatus(e.target.value)}
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
                    value={newPriority}
                    onChange={(e) => setNewPriority(e.target.value)}
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
                    value={newType}
                    onChange={(e) => setNewType(e.target.value)}
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

              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1">
                  Assignee
                </label>
                <select
                  value={newAssigneeId}
                  onChange={(e) => setNewAssigneeId(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-md bg-background-subtle border border-border-subtle text-content-primary focus:border-accent outline-none"
                >
                  <option value="">Unassigned</option>
                  {members.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.user?.full_name || m.user?.email || m.user_id} ({m.role})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-border-subtle">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="px-3.5 py-1.5 rounded-md text-content-secondary hover:text-content-primary text-xs font-medium transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending || !newProjectId}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors disabled:opacity-50"
                >
                  {createMutation.isPending ? 'Creating...' : 'Create Task'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function EditTaskModal({ task, members, onClose, onSave, isPending }) {
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description || '');
  const [status, setStatus] = useState(task.status);
  const [priority, setPriority] = useState(task.priority);
  const [taskType, setTaskType] = useState(task.task_type);
  const [assigneeId, setAssigneeId] = useState(task.assignee_id || '');

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave({
      title: title.trim(),
      description: description.trim() || null,
      status,
      priority,
      task_type: taskType,
      assignee_id: assigneeId || null,
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-lg p-6 rounded-lg bg-background-card border border-border-strong shadow-card text-left">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-content-primary">Edit Task</h3>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-content-secondary hover:text-content-primary hover:bg-background-subtle"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-content-secondary mb-1">Title *</label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-content-secondary mb-1">
              Description
            </label>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary outline-none resize-none"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-content-secondary mb-1">Status</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded-md bg-background-subtle border border-border-subtle text-content-primary outline-none"
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
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded-md bg-background-subtle border border-border-subtle text-content-primary outline-none"
              >
                {PRIORITY_OPTIONS.map((pr) => (
                  <option key={pr} value={pr}>
                    {pr}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-content-secondary mb-1">Type</label>
              <select
                value={taskType}
                onChange={(e) => setTaskType(e.target.value)}
                className="w-full px-2.5 py-1.5 text-xs rounded-md bg-background-subtle border border-border-subtle text-content-primary outline-none"
              >
                {TYPE_OPTIONS.map((tp) => (
                  <option key={tp} value={tp}>
                    {tp}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-content-secondary mb-1">
              Assignee
            </label>
            <select
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value)}
              className="w-full px-2.5 py-1.5 text-xs rounded-md bg-background-subtle border border-border-subtle text-content-primary outline-none"
            >
              <option value="">Unassigned</option>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.user?.full_name || m.user?.email || m.user_id} ({m.role})
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-border-subtle">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-1.5 rounded-md text-content-secondary hover:text-content-primary text-xs font-medium"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover disabled:opacity-50"
            >
              {isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
