import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FolderGit2, CheckSquare, Clock, CheckCircle2, Plus, AlertCircle, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { api } from '../lib/api';
import { MetricCard } from '../features/dashboard/MetricCard';
import { RecentTasksList } from '../features/dashboard/RecentTasksList';
import { RecentActivityFeed } from '../features/dashboard/RecentActivityFeed';
import { HealthStatusBanner } from '../features/dashboard/HealthStatusBanner';

export function DashboardPage() {
  const navigate = useNavigate();
  const { activeWorkspace } = useAuth();
  const workspaceId = activeWorkspace?.id;

  const {
    data: summary,
    isLoading: isSummaryLoading,
    isError: isSummaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['dashboard', 'summary', workspaceId],
    queryFn: () => api.getDashboardSummary(workspaceId),
    enabled: !!workspaceId,
    staleTime: 10000,
  });

  return (
    <div className="space-y-6">
      {/* Top Banner / Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-content-primary">
            Workspace Overview
          </h1>
          <p className="text-sm text-content-secondary mt-1">
            Real-time project and engineering task metrics for{' '}
            <span className="text-content-primary font-medium">{activeWorkspace?.name || 'Workspace'}</span>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/projects')}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-md bg-background-subtle border border-border-subtle text-content-primary text-xs font-semibold hover:bg-background-hover transition-colors"
          >
            <FolderGit2 className="w-4 h-4 text-accent" />
            Projects
          </button>
          <button
            onClick={() => navigate('/tasks')}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors shadow-subtle"
          >
            <Plus className="w-4 h-4" />
            New Task
          </button>
        </div>
      </div>

      {/* Diagnostics / Health Status Banner */}
      <HealthStatusBanner />

      {/* Error state for Summary */}
      {isSummaryError && (
        <div className="p-4 rounded-md bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            Failed to load dashboard statistics for this workspace.
          </div>
          <button
            onClick={() => refetchSummary()}
            className="flex items-center gap-1 font-semibold hover:text-rose-300 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Retry
          </button>
        </div>
      )}

      {/* Metric Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Active Projects"
          value={isSummaryLoading ? '...' : (summary?.total_projects ?? 0)}
          subtitle="Non-archived workspace projects"
          icon={FolderGit2}
        />
        <MetricCard
          title="Open Tasks"
          value={isSummaryLoading ? '...' : (summary?.open_tasks ?? 0)}
          subtitle="Backlog, todo, or review"
          icon={CheckSquare}
        />
        <MetricCard
          title="In Progress"
          value={isSummaryLoading ? '...' : (summary?.in_progress_tasks ?? 0)}
          subtitle="Actively being developed"
          icon={Clock}
        />
        <MetricCard
          title="Completed Tasks"
          value={isSummaryLoading ? '...' : (summary?.completed_tasks ?? 0)}
          subtitle="Successfully delivered & verified"
          icon={CheckCircle2}
        />
      </div>

      {/* Task & Activity Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RecentTasksList
          workspaceId={workspaceId}
          onNewTask={() => navigate('/tasks')}
        />
        <RecentActivityFeed workspaceId={workspaceId} />
      </div>
    </div>
  );
}
