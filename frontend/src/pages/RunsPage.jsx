import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Bot,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Wrench,
  RefreshCw,
  ExternalLink,
  Search,
  Filter,
  ShieldCheck,
  AlertTriangle,
  FileSearch,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { api } from '../lib/api';
import { MetricCard } from '../features/dashboard/MetricCard';
import { EmptyState } from '../components/common/EmptyState';
import { LoadingSpinner } from '../components/common/LoadingSpinner';
import { RunTraceModal } from '../components/observability/RunTraceModal';

const STATUS_FILTERS = [
  { value: 'all', label: 'All Statuses' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
  { value: 'running', label: 'In Progress' },
  { value: 'timed_out', label: 'Timed Out' },
  { value: 'cancelled', label: 'Cancelled' },
];

const TIME_WINDOWS = [
  { value: 7, label: 'Last 7 Days' },
  { value: 30, label: 'Last 30 Days' },
  { value: 90, label: 'Last 90 Days' },
];

export function RunsPage() {
  const queryClient = useQueryClient();
  const { activeWorkspace } = useAuth();
  const workspaceId = activeWorkspace?.id;

  const [statusFilter, setStatusFilter] = useState('all');
  const [timeWindowDays, setTimeWindowDays] = useState(30);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [isTraceModalOpen, setIsTraceModalOpen] = useState(false);
  const [actionFeedback, setActionFeedback] = useState(null);

  // 1. Fetch Aggregate Workspace Metrics
  const {
    data: metrics,
    isLoading: isMetricsLoading,
    refetch: refetchMetrics,
  } = useQuery({
    queryKey: ['observability', 'metrics', workspaceId, timeWindowDays],
    queryFn: () => api.getWorkspaceMetrics(workspaceId, timeWindowDays),
    enabled: !!workspaceId,
    staleTime: 15000,
  });

  // 2. Fetch Workspace Runs List
  const {
    data: runs = [],
    isLoading: isRunsLoading,
    isRefetching: isRunsRefetching,
    refetch: refetchRuns,
  } = useQuery({
    queryKey: ['observability', 'runs', workspaceId, statusFilter],
    queryFn: () => api.listWorkspaceRuns(workspaceId, { status: statusFilter, limit: 50 }),
    enabled: !!workspaceId,
    staleTime: 15000,
  });

  // 3. Stale Run Recovery Mutation
  const recoverMutation = useMutation({
    mutationFn: () => api.recoverStaleRuns(workspaceId, 15),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['observability'] });
      setActionFeedback(
        `Recovered ${data.recovered_executions} executions, ${data.recovered_repairs} repairs, and ${data.recovered_publishing} publishing runs.`
      );
      setTimeout(() => setActionFeedback(null), 5000);
    },
    onError: (err) => {
      setActionFeedback(`Recovery check failed: ${err.message}`);
      setTimeout(() => setActionFeedback(null), 5000);
    },
  });

  const handleOpenTrace = (runId) => {
    setSelectedRunId(runId);
    setIsTraceModalOpen(true);
  };

  const handleCloseTrace = () => {
    setSelectedRunId(null);
    setIsTraceModalOpen(false);
  };

  const handleRefreshAll = () => {
    refetchMetrics();
    refetchRuns();
  };

  const terminalRunsCount =
    (metrics?.successful_runs ?? 0) +
    (metrics?.failed_runs ?? 0) +
    (metrics?.cancelled_runs ?? 0) +
    (metrics?.timed_out_runs ?? 0);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-content-primary flex items-center gap-2">
            <Activity className="w-5 h-5 text-accent" />
            Agent Runs & Observability
          </h1>
          <p className="text-sm text-content-secondary mt-1">
            End-to-end trace dossiers, stage timelines, verification diagnostics, and reliability metrics for{' '}
            <span className="text-content-primary font-medium">{activeWorkspace?.name || 'Workspace'}</span>.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleRefreshAll}
            disabled={isRunsRefetching}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md bg-background-subtle border border-border-subtle text-xs font-semibold text-content-secondary hover:text-content-primary hover:bg-background-hover transition-colors"
            title="Refresh metrics & runs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRunsRefetching ? 'animate-spin text-accent' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => recoverMutation.mutate()}
            disabled={recoverMutation.isPending || !workspaceId}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md bg-background-card border border-border-subtle text-xs font-semibold text-content-primary hover:bg-background-hover hover:border-border-strong transition-colors shadow-subtle disabled:opacity-50"
            title="Scan and mark abandoned or interrupted runs as timed out"
          >
            <Clock className={`w-3.5 h-3.5 text-accent ${recoverMutation.isPending ? 'animate-spin' : ''}`} />
            {recoverMutation.isPending ? 'Auditing Runs...' : 'Recover Stale Runs'}
          </button>
        </div>
      </div>

      {/* Action / Recovery Notification */}
      {actionFeedback && (
        <div className="p-3.5 rounded-lg bg-background-subtle border border-border-subtle flex items-center justify-between text-xs text-content-primary animate-fade-in">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-accent shrink-0" />
            <span>{actionFeedback}</span>
          </div>
          <button
            onClick={() => setActionFeedback(null)}
            className="text-content-muted hover:text-content-primary"
          >
            &times;
          </button>
        </div>
      )}

      {/* Aggregate Reliability & Performance Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <MetricCard
          title="Run Success Rate"
          value={
            metrics?.success_rate_percent !== null && metrics?.success_rate_percent !== undefined
              ? `${metrics.success_rate_percent}%`
              : 'N/A'
          }
          subtitle={`Denominator: ${metrics?.successful_runs ?? 0} of ${terminalRunsCount} terminal runs (${timeWindowDays}d)`}
          icon={CheckCircle2}
        />
        <MetricCard
          title="Total Runs"
          value={metrics?.total_runs ?? 0}
          subtitle={`Dispatched in last ${timeWindowDays} days`}
          icon={Bot}
        />
        <MetricCard
          title="Avg Duration"
          value={
            metrics?.average_durations_seconds?.execution
              ? `${metrics.average_durations_seconds.execution}s`
              : 'N/A'
          }
          subtitle="Average sandbox runtime"
          icon={Clock}
        />
        <MetricCard
          title="Failures & Timeouts"
          value={`${metrics?.failed_runs ?? 0} / ${metrics?.timed_out_runs ?? 0}`}
          subtitle={`${metrics?.failed_runs ?? 0} failed • ${metrics?.timed_out_runs ?? 0} timed out`}
          icon={XCircle}
        />
        <MetricCard
          title="Self-Healing Repairs"
          value={`${metrics?.repairs_succeeded ?? 0} / ${metrics?.total_repairs ?? 0}`}
          subtitle="Automated repair resolution rate"
          icon={Wrench}
        />
      </div>

      {/* Filter and Control Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-lg bg-background-card border border-border-subtle">
        <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
          <span className="text-xs font-medium text-content-muted flex items-center gap-1.5 shrink-0 pl-1">
            <Filter className="w-3.5 h-3.5 text-accent" />
            Status:
          </span>
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.value}
              onClick={() => setStatusFilter(filter.value)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors whitespace-nowrap ${
                statusFilter === filter.value
                  ? 'bg-accent text-background font-semibold'
                  : 'bg-background-subtle border border-border-subtle text-content-secondary hover:text-content-primary hover:bg-background-hover'
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs font-medium text-content-muted">Window:</span>
          <select
            value={timeWindowDays}
            onChange={(e) => setTimeWindowDays(Number(e.target.value))}
            className="text-xs bg-background-subtle border border-border-subtle rounded px-2.5 py-1 text-content-primary focus:outline-none focus:border-accent"
          >
            {TIME_WINDOWS.map((w) => (
              <option key={w.value} value={w.value}>
                {w.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Runs Table */}
      <div className="rounded-lg bg-background-card border border-border-subtle overflow-hidden">
        {isRunsLoading ? (
          <div className="py-20 flex flex-col items-center justify-center gap-3">
            <LoadingSpinner size="lg" />
            <p className="text-sm text-content-muted">Loading workspace run history...</p>
          </div>
        ) : runs.length === 0 ? (
          <div className="p-8">
            <EmptyState
              icon={Bot}
              title={statusFilter === 'all' ? 'No agent runs dispatched yet' : `No ${statusFilter} runs found`}
              description="Agent runs record full lifecycle transitions, verification evidence, and GitHub delivery outcomes."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-background-subtle/80 border-b border-border-subtle text-[11px] font-semibold uppercase tracking-wider text-content-muted">
                <tr>
                  <th className="py-3 px-4">Task & Run</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Duration</th>
                  <th className="py-3 px-4">Verification</th>
                  <th className="py-3 px-4">Repairs</th>
                  <th className="py-3 px-4">Pull Request</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle/60">
                {runs.map((run) => {
                  const isSuccess = run.status === 'completed' || run.status === 'succeeded';
                  const isFail = run.status === 'failed';
                  const isTimedOut = run.status === 'timed_out';
                  const isRunning = run.status === 'running' || run.status === 'pending';

                  return (
                    <tr
                      key={run.id}
                      className="hover:bg-background-hover/50 transition-colors group"
                    >
                      {/* Task & Run Info */}
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-content-primary truncate max-w-xs" title={run.task_title}>
                          {run.task_title}
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-[11px] text-content-muted">
                          <span className="font-mono text-content-secondary truncate max-w-[120px]">
                            {run.id}
                          </span>
                          <span>•</span>
                          <span className="uppercase text-[10px] font-medium bg-background-subtle px-1.5 py-0.5 rounded border border-border-subtle">
                            {run.task_type}
                          </span>
                        </div>
                      </td>

                      {/* Status */}
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${
                            isSuccess
                              ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60'
                              : isFail
                              ? 'bg-rose-950/60 text-rose-300 border-rose-800/60'
                              : isTimedOut
                              ? 'bg-amber-950/60 text-amber-300 border-amber-800/60'
                              : isRunning
                              ? 'bg-blue-950/60 text-blue-300 border-blue-800/60'
                              : 'bg-zinc-800 text-zinc-400 border-zinc-700'
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              isSuccess
                                ? 'bg-emerald-400'
                                : isFail
                                ? 'bg-rose-400'
                                : isTimedOut
                                ? 'bg-amber-400'
                                : isRunning
                                ? 'bg-blue-400 animate-pulse'
                                : 'bg-zinc-400'
                            }`}
                          />
                          {run.status}
                        </span>
                      </td>

                      {/* Duration */}
                      <td className="py-3.5 px-4 whitespace-nowrap font-mono text-content-secondary">
                        {run.duration_seconds !== null ? `${run.duration_seconds}s` : '—'}
                      </td>

                      {/* Verification Status */}
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {run.verification_passed === true ? (
                          <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Passed
                          </span>
                        ) : run.verification_passed === false ? (
                          <span className="inline-flex items-center gap-1 text-rose-400 font-medium">
                            <XCircle className="w-3.5 h-3.5" />
                            Failed
                          </span>
                        ) : (
                          <span className="text-content-muted">N/A</span>
                        )}
                      </td>

                      {/* Repairs Count */}
                      <td className="py-3.5 px-4 whitespace-nowrap font-mono">
                        {run.repair_attempts > 0 ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-background-subtle border border-border-subtle text-amber-300">
                            <Wrench className="w-3 h-3" />
                            {run.repair_attempts}
                          </span>
                        ) : (
                          <span className="text-content-muted">0</span>
                        )}
                      </td>

                      {/* Pull Request Link */}
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {run.pr_url ? (
                          <a
                            href={run.pr_url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-accent hover:underline font-medium"
                          >
                            PR #{run.pr_number}
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        ) : (
                          <span className="text-content-muted">None</span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right whitespace-nowrap">
                        <button
                          onClick={() => handleOpenTrace(run.id)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-background-subtle border border-border-subtle text-content-primary hover:bg-background-hover hover:border-accent text-xs font-semibold transition-colors"
                        >
                          <FileSearch className="w-3.5 h-3.5 text-accent" />
                          Inspect Trace
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* End-to-End Run Trace Modal */}
      {selectedRunId && (
        <RunTraceModal
          runId={selectedRunId}
          workspaceId={workspaceId}
          isOpen={isTraceModalOpen}
          onClose={handleCloseTrace}
        />
      )}
    </div>
  );
}
