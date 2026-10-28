import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  X,
  Clock,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ExternalLink,
  Bot,
  Terminal,
  GitPullRequest,
  Wrench,
  ShieldAlert,
  Cpu,
  Layers,
  Copy,
  Check,
} from 'lucide-react';
import { api } from '../../lib/api';
import { LoadingSpinner } from '../common/LoadingSpinner';

const STATUS_CONFIG = {
  completed: {
    bg: 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60',
    icon: CheckCircle2,
    dot: 'bg-emerald-400',
  },
  succeeded: {
    bg: 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60',
    icon: CheckCircle2,
    dot: 'bg-emerald-400',
  },
  failed: {
    bg: 'bg-rose-950/60 text-rose-300 border-rose-800/60',
    icon: XCircle,
    dot: 'bg-rose-400',
  },
  timed_out: {
    bg: 'bg-amber-950/60 text-amber-300 border-amber-800/60',
    icon: Clock,
    dot: 'bg-amber-400',
  },
  running: {
    bg: 'bg-blue-950/60 text-blue-300 border-blue-800/60',
    icon: Clock,
    dot: 'bg-blue-400 animate-pulse',
  },
  pending: {
    bg: 'bg-zinc-800 text-zinc-400 border-zinc-700',
    icon: Clock,
    dot: 'bg-zinc-400',
  },
  cancelled: {
    bg: 'bg-zinc-800 text-zinc-400 border-zinc-700',
    icon: XCircle,
    dot: 'bg-zinc-400',
  },
};

const STAGE_ICONS = {
  planning: Layers,
  execution: Terminal,
  verification: ShieldAlert,
  repair: Wrench,
  publishing: GitPullRequest,
};

export function RunTraceModal({ runId, workspaceId, isOpen, onClose }) {
  const [copied, setCopied] = useState(false);

  const {
    data: trace,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['observability', 'trace', runId, workspaceId],
    queryFn: () => api.getRunTrace(runId, workspaceId),
    enabled: isOpen && !!runId && !!workspaceId,
  });

  if (!isOpen) return null;

  const handleCopyId = () => {
    if (runId) {
      navigator.clipboard.writeText(runId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const statusStyle = STATUS_CONFIG[trace?.status] || STATUS_CONFIG.pending;
  const StatusIcon = statusStyle.icon;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-background-card border border-border-subtle rounded-xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle bg-background-subtle/50">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-accent/10 border border-accent/20 text-accent">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-content-primary">
                  {trace?.task_title || 'Agent Run Trace'}
                </h2>
                {trace?.task_type && (
                  <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-background-subtle border border-border-subtle text-content-secondary uppercase">
                    {trace.task_type}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-0.5 text-xs text-content-muted">
                <span>Run ID:</span>
                <span className="font-mono text-content-secondary">{runId}</span>
                <button
                  onClick={handleCopyId}
                  className="hover:text-content-primary transition-colors p-0.5"
                  title="Copy Run ID"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {trace && (
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${statusStyle.bg}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot}`} />
                {trace.status}
              </span>
            )}
            <button
              onClick={onClose}
              className="p-1.5 text-content-muted hover:text-content-primary hover:bg-background-hover rounded-md transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isLoading && (
            <div className="py-16 flex flex-col items-center justify-center gap-3">
              <LoadingSpinner size="lg" />
              <p className="text-sm text-content-muted">Assembling run trace dossier...</p>
            </div>
          )}

          {isError && (
            <div className="p-4 rounded-lg bg-rose-950/30 border border-rose-800/50 flex items-start gap-3 text-rose-300">
              <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold">Failed to load run trace</h4>
                <p className="text-xs text-rose-300/80 mt-1">
                  {error?.message || 'Run details could not be retrieved. Please verify your permissions.'}
                </p>
              </div>
            </div>
          )}

          {trace && (
            <>
              {/* Sanitized Error Alert */}
              {trace.safe_error_summary && (
                <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800/60 flex items-start gap-3 text-rose-200">
                  <AlertTriangle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wider text-rose-400">
                        Sanitized Failure Reason
                      </span>
                    </div>
                    <p className="text-xs font-mono mt-1 text-rose-200 break-words leading-relaxed">
                      {trace.safe_error_summary}
                    </p>
                  </div>
                </div>
              )}

              {/* Execution Summary Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-lg bg-background-subtle border border-border-subtle">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-content-muted">
                    Total Duration
                  </span>
                  <div className="text-base font-semibold font-mono text-content-primary mt-1">
                    {trace.duration_seconds !== null ? `${trace.duration_seconds}s` : 'In progress'}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-background-subtle border border-border-subtle">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-content-muted">
                    Sandbox Image
                  </span>
                  <div className="text-xs font-mono text-content-secondary mt-1 truncate" title={trace.sandbox_image}>
                    {trace.sandbox_image || 'default'}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-background-subtle border border-border-subtle">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-content-muted">
                    Model Provider
                  </span>
                  <div className="text-xs font-mono text-content-secondary mt-1">
                    {Object.values(trace.model_usage || {})[0]?.model_name || 'Unavailable'}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-background-subtle border border-border-subtle">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-content-muted">
                    Token Usage / Cost
                  </span>
                  <div className="text-xs font-mono text-content-secondary mt-1">
                    {Object.values(trace.model_usage || {})[0]?.prompt_tokens === 'unavailable'
                      ? 'Unavailable'
                      : `${Object.values(trace.model_usage || {})[0]?.prompt_tokens || 0} tok`}
                  </div>
                </div>
              </div>

              {/* Stage Lifecycle Timeline */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-content-secondary flex items-center gap-2">
                    <Clock className="w-4 h-4 text-accent" />
                    Lifecycle Timeline & Stages
                  </h3>
                  <span className="text-[11px] text-content-muted">
                    {trace.timeline?.length || 0} stage transitions recorded
                  </span>
                </div>

                <div className="relative pl-6 space-y-4 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-border-subtle">
                  {trace.timeline && trace.timeline.length > 0 ? (
                    trace.timeline.map((evt, idx) => {
                      const StageIcon = STAGE_ICONS[evt.stage] || Bot;
                      const evtStatus = STATUS_CONFIG[evt.status] || STATUS_CONFIG.pending;

                      return (
                        <div key={idx} className="relative group">
                          {/* Timeline Node */}
                          <div
                            className={`absolute -left-6 top-1.5 w-5 h-5 rounded-full border flex items-center justify-center bg-background ${evtStatus.bg}`}
                          >
                            <span className={`w-2 h-2 rounded-full ${evtStatus.dot}`} />
                          </div>

                          {/* Event Card */}
                          <div className="p-3.5 rounded-lg bg-background-subtle/80 border border-border-subtle hover:border-border-strong transition-colors">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-1.5">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-bold uppercase tracking-wider text-content-primary">
                                  {evt.stage}
                                </span>
                                <span className="text-xs text-content-muted">•</span>
                                <span className="text-xs font-medium text-content-secondary">
                                  {evt.event}
                                </span>
                              </div>
                              <div className="flex items-center gap-3 text-[11px] font-mono text-content-muted">
                                {evt.duration_seconds !== null && (
                                  <span className="text-accent font-semibold">
                                    {evt.duration_seconds}s
                                  </span>
                                )}
                                <span>{new Date(evt.timestamp).toLocaleTimeString()}</span>
                              </div>
                            </div>

                            {/* Details Pill/Data */}
                            {evt.details && Object.keys(evt.details).length > 0 && (
                              <div className="mt-2 pt-2 border-t border-border-subtle/60 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                                {Object.entries(evt.details).map(([key, val]) => (
                                  <div key={key} className="flex items-center gap-1.5 text-content-muted">
                                    <span className="capitalize font-medium">{key.replace(/_/g, ' ')}:</span>
                                    <span className="font-mono text-content-secondary truncate">
                                      {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-xs text-content-muted py-3">
                      No discrete lifecycle events captured for this run.
                    </div>
                  )}
                </div>
              </div>

              {/* Artifacts & Verification Outcomes */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Verification Summary */}
                <div className="p-4 rounded-lg bg-background-subtle border border-border-subtle space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-content-secondary flex items-center gap-1.5">
                      <ShieldAlert className="w-4 h-4 text-accent" />
                      Verification Diagnostics
                    </h4>
                    {trace.verification ? (
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                          trace.verification.all_passed
                            ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/60'
                            : 'bg-rose-950/60 text-rose-300 border border-rose-800/60'
                        }`}
                      >
                        {trace.verification.all_passed ? 'Checks Passed' : 'Checks Failed'}
                      </span>
                    ) : (
                      <span className="text-[11px] text-content-muted">Not Verified</span>
                    )}
                  </div>
                  {trace.verification ? (
                    <div className="space-y-1.5 text-xs text-content-secondary">
                      <div className="flex justify-between">
                        <span>Exit Code:</span>
                        <span className="font-mono">{trace.verification.exit_code ?? 0}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Output Status:</span>
                        <span className="font-mono text-content-primary">
                          {trace.verification.has_output ? 'Recorded in dossier' : 'Clean'}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-content-muted">
                      No automated sandbox verification suite ran during this execution.
                    </p>
                  )}
                </div>

                {/* Pull Request & Publishing */}
                <div className="p-4 rounded-lg bg-background-subtle border border-border-subtle space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-content-secondary flex items-center gap-1.5">
                      <GitPullRequest className="w-4 h-4 text-accent" />
                      GitHub Delivery
                    </h4>
                    {trace.publishing?.status && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase bg-background-card border border-border-subtle text-content-primary">
                        {trace.publishing.status}
                      </span>
                    )}
                  </div>
                  {trace.publishing?.pr_url ? (
                    <div className="space-y-2 text-xs">
                      <a
                        href={trace.publishing.pr_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 text-accent hover:underline font-medium"
                      >
                        PR #{trace.publishing.pr_number}: Open on GitHub
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                      <div className="text-[11px] text-content-muted font-mono truncate">
                        Branch: {trace.publishing.branch_name}
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-content-muted">
                      {trace.publishing?.status === 'in_progress'
                        ? 'Publishing branch and pull request...'
                        : 'No pull request published for this run yet.'}
                    </p>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-border-subtle bg-background-subtle/40 text-xs text-content-muted">
          <span>Security Notice: Credentials and private keys are automatically redacted.</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-md bg-background-card border border-border-subtle text-content-primary hover:bg-background-hover transition-colors font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
