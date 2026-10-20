import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckSquare, Plus, AlertCircle, ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../../lib/api';
import { EmptyState } from '../../components/common/EmptyState';

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

export function RecentTasksList({ workspaceId, onNewTask }) {
  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['tasks', workspaceId, 'recent'],
    queryFn: () => api.getWorkspaceTasks({ workspaceId, limit: 5 }),
    enabled: !!workspaceId,
    staleTime: 10000,
  });

  const tasks = data?.items || [];

  return (
    <div className="rounded-lg bg-background-card border border-border-subtle p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-content-primary">Recent Tasks</h2>
          <p className="text-xs text-content-secondary mt-0.5">
            Active and completed software engineering tasks.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/tasks"
            className="text-xs text-content-secondary hover:text-accent flex items-center gap-1 transition-colors"
          >
            View all
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
          {onNewTask && (
            <button
              onClick={onNewTask}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              New Task
            </button>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3 py-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex items-center justify-between py-2 border-b border-border-subtle animate-pulse">
              <div className="space-y-1.5 flex-1">
                <div className="h-3.5 bg-background-subtle rounded w-2/3" />
                <div className="h-2.5 bg-background-subtle rounded w-1/3" />
              </div>
              <div className="h-5 w-16 bg-background-subtle rounded" />
            </div>
          ))}
        </div>
      ) : isError ? (
        <div className="p-4 rounded-md bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center justify-between">
          <span className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            Failed to load tasks.
          </span>
          <button
            onClick={() => refetch()}
            className="underline font-semibold hover:text-rose-300"
          >
            Retry
          </button>
        </div>
      ) : tasks.length === 0 ? (
        <EmptyState
          icon={CheckSquare}
          title="No tasks in this workspace"
          description="Create your first task or organize them by project to start tracking engineering progress."
          action={
            onNewTask ? (
              <button
                onClick={onNewTask}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-background-subtle border border-border-subtle text-content-primary text-xs font-medium hover:bg-background-hover transition-colors"
              >
                Create your first task
              </button>
            ) : null
          }
        />
      ) : (
        <div className="divide-y divide-border-subtle">
          {tasks.map((task) => (
            <div
              key={task.id}
              className="py-2.5 first:pt-0 last:pb-0 flex items-center justify-between gap-3 hover:bg-background-hover/40 px-2 rounded -mx-2 transition-colors"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-content-primary truncate">
                    {task.title}
                  </span>
                  {task.archived_at && (
                    <span className="text-[10px] uppercase font-mono px-1 rounded bg-amber-950/60 text-amber-300 border border-amber-800/60">
                      Archived
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1 text-[11px] text-content-muted">
                  <span className="font-mono">{task.task_type}</span>
                  <span>•</span>
                  <span className={PRIORITY_BADGES[task.priority] || 'text-content-muted'}>
                    {task.priority}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span
                  className={`text-[11px] font-mono px-2 py-0.5 rounded border capitalize ${
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
  );
}
