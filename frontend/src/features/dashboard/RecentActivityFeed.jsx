import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, FolderGit2, CheckCircle2, Clock, AlertCircle, PlusCircle, Archive, RefreshCw } from 'lucide-react';
import { api } from '../../lib/api';
import { EmptyState } from '../../components/common/EmptyState';

function getEventIcon(eventType) {
  switch (eventType) {
    case 'project_created':
      return <FolderGit2 className="w-4 h-4 text-emerald-400" />;
    case 'project_archived':
      return <Archive className="w-4 h-4 text-amber-400" />;
    case 'project_restored':
      return <RefreshCw className="w-4 h-4 text-sky-400" />;
    case 'task_created':
      return <PlusCircle className="w-4 h-4 text-accent" />;
    case 'task_completed':
      return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
    case 'task_status_changed':
      return <Clock className="w-4 h-4 text-indigo-400" />;
    case 'task_archived':
      return <Archive className="w-4 h-4 text-amber-400" />;
    default:
      return <Activity className="w-4 h-4 text-accent/80" />;
  }
}

function formatRelativeTime(dateString) {
  if (!dateString) return '';
  const date = new Date(dateString);
  const now = new Date();
  const diffInSeconds = Math.floor((now - date) / 1000);

  if (diffInSeconds < 60) return 'just now';
  const diffInMinutes = Math.floor(diffInSeconds / 60);
  if (diffInMinutes < 60) return `${diffInMinutes}m ago`;
  const diffInHours = Math.floor(diffInMinutes / 60);
  if (diffInHours < 24) return `${diffInHours}h ago`;
  const diffInDays = Math.floor(diffInHours / 24);
  if (diffInDays < 30) return `${diffInDays}d ago`;
  return date.toLocaleDateString();
}

function getEventDescription(event) {
  const meta = event.metadata || {};
  switch (event.event_type) {
    case 'project_created':
      return `Created project "${meta.name || 'Untitled'}"`;
    case 'project_archived':
      return `Archived project "${meta.name || 'Untitled'}"`;
    case 'project_restored':
      return `Restored project "${meta.name || 'Untitled'}"`;
    case 'task_created':
      return `Created task "${meta.title || 'Untitled'}"`;
    case 'task_status_changed':
      return `Changed task status from ${meta.old_status || 'unknown'} to ${meta.new_status || 'unknown'}`;
    case 'task_completed':
      return `Completed task "${meta.title || 'Untitled'}"`;
    case 'task_reopened':
      return `Reopened task "${meta.title || 'Untitled'}"`;
    case 'task_assigned':
      return `Updated assignment for task "${meta.title || 'Untitled'}"`;
    case 'task_archived':
      return `Archived task "${meta.title || 'Untitled'}"`;
    case 'task_restored':
      return `Restored task "${meta.title || 'Untitled'}"`;
    default:
      return event.event_type.replace(/_/g, ' ');
  }
}

export function RecentActivityFeed({ workspaceId }) {
  const {
    data: activities = [],
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['activity', workspaceId],
    queryFn: () => api.getRecentActivity(workspaceId, 10),
    enabled: !!workspaceId,
    staleTime: 10000,
  });

  return (
    <div className="rounded-lg bg-background-card border border-border-subtle p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-content-primary">Recent Activity</h2>
          <p className="text-xs text-content-secondary mt-0.5">
            Audit trail of project updates and task lifecycle events.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3 py-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex items-center gap-3 animate-pulse">
              <div className="w-8 h-8 rounded-full bg-background-subtle shrink-0" />
              <div className="flex-1 space-y-1">
                <div className="h-3 bg-background-subtle rounded w-3/4" />
                <div className="h-2 bg-background-subtle rounded w-1/4" />
              </div>
            </div>
          ))}
        </div>
      ) : isError ? (
        <div className="p-4 rounded-md bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center justify-between">
          <span className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            Failed to load recent activity.
          </span>
          <button
            onClick={() => refetch()}
            className="underline font-semibold hover:text-rose-300"
          >
            Retry
          </button>
        </div>
      ) : activities.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No activity recorded"
          description="Projects and tasks created, edited, or archived will appear here in chronological order."
        />
      ) : (
        <div className="space-y-3 divide-y divide-border-subtle">
          {activities.map((act) => (
            <div key={act.id} className="pt-3 first:pt-0 flex items-start gap-3">
              <div className="p-1.5 rounded-md bg-background-subtle border border-border-subtle shrink-0 mt-0.5">
                {getEventIcon(act.event_type)}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-content-primary font-medium leading-snug">
                  {getEventDescription(act)}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[11px] text-content-muted font-mono">
                    {formatRelativeTime(act.created_at)}
                  </span>
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 bg-background-subtle rounded text-content-muted">
                    {act.resource_type}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
