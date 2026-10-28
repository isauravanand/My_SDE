import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Play,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Terminal,
  FileCode,
  ShieldCheck,
  ShieldAlert,
  Trash2,
  X,
  RefreshCw,
  GitCommit,
  Check,
  Ban,
  Boxes,
  Wrench,
  Sparkles,
  RotateCcw,
  FileDiff,
  HelpCircle,
  GitPullRequest,
  ExternalLink,
  Send,
} from 'lucide-react';
import { api } from '../../lib/api';

const STATUS_BADGES = {
  queued: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  preparing: 'bg-blue-950/60 text-blue-300 border-blue-800/60',
  awaiting_patch_approval: 'bg-amber-950/60 text-amber-300 border-amber-800/60 animate-pulse',
  applying_patch: 'bg-indigo-950/60 text-indigo-300 border-indigo-800/60',
  running_checks: 'bg-purple-950/60 text-purple-300 border-purple-800/60',
  completed: 'bg-[#CCFF00]/10 text-[#CCFF00] border-[#CCFF00]/40',
  failed: 'bg-rose-950/60 text-rose-300 border-rose-800/60',
  cancel_requested: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  cancelled: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  timed_out: 'bg-amber-950/60 text-amber-400 border-amber-700/60',
  cleanup_failed: 'bg-red-950/80 text-red-300 border-red-700',
  analyzing: 'bg-blue-950/60 text-blue-300 border-blue-800/60',
  repairing: 'bg-indigo-950/60 text-indigo-300 border-indigo-800/60',
  budget_exhausted: 'bg-amber-950/60 text-amber-300 border-amber-800/60',
  non_repairable: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  pending_approval: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  approved: 'bg-blue-950/60 text-blue-300 border-blue-800/60',
  pushing_branch: 'bg-indigo-950/60 text-indigo-300 border-indigo-800/60',
  creating_pr: 'bg-purple-950/60 text-purple-300 border-purple-800/60 animate-pulse',
  stale_base_conflict: 'bg-amber-950/60 text-amber-300 border-amber-800/60',
};

export default function ExecutionModal({ task, plan, onClose }) {
  const queryClient = useQueryClient();
  const [activeRunId, setActiveRunId] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [selectedChecks, setSelectedChecks] = useState(['syntax_check']);
  const [publishError, setPublishError] = useState('');

  // 1. Fetch runs for this task
  const {
    data: runsList = [],
    isLoading: isRunsLoading,
    refetch: refetchRuns,
  } = useQuery({
    queryKey: ['task-executions', task?.id],
    queryFn: () => api.listTaskExecutions(task?.id, 10, 0),
    enabled: Boolean(task?.id),
    staleTime: 5000,
  });

  // Automatically select the most recent run if none selected
  useEffect(() => {
    if (!activeRunId && runsList.length > 0) {
      setActiveRunId(runsList[0].id);
    }
  }, [runsList, activeRunId]);

  // 2. Fetch active run details
  const {
    data: activeRun,
    isLoading: isRunDetailLoading,
    refetch: refetchActiveRun,
  } = useQuery({
    queryKey: ['execution-run', activeRunId],
    queryFn: () => api.getExecutionRun(activeRunId),
    enabled: Boolean(activeRunId),
    refetchInterval: (query) => {
      const run = query.state.data;
      if (run && ['preparing', 'awaiting_patch_approval', 'applying_patch', 'running_checks'].includes(run.status)) {
        return 2000;
      }
      return false;
    },
  });

  // 3. Start execution mutation
  const startExecutionMutation = useMutation({
    mutationFn: () => api.startTaskExecution(task.id, { plan_id: plan?.id }),
    onSuccess: (newRun) => {
      setActiveRunId(newRun.id);
      queryClient.invalidateQueries({ queryKey: ['task-executions', task?.id] });
    },
  });

  // 4. Approve patch mutation
  const approveMutation = useMutation({
    mutationFn: () =>
      api.approvePatchAndExecute(activeRunId, {
        run_checks: true,
        verification_commands: selectedChecks,
      }),
    onSuccess: () => {
      refetchActiveRun();
      refetchRuns();
    },
  });

  // 5. Reject patch mutation
  const rejectMutation = useMutation({
    mutationFn: () => api.rejectPatchProposal(activeRunId, { reason: rejectReason }),
    onSuccess: () => {
      setShowRejectInput(false);
      refetchActiveRun();
      refetchRuns();
    },
  });

  // 6. Cancel run mutation
  const cancelMutation = useMutation({
    mutationFn: () => api.cancelExecutionRun(activeRunId),
    onSuccess: () => {
      refetchActiveRun();
      refetchRuns();
    },
  });

  // 7. Bounded AI Repair query (Phase 8)
  const {
    data: repairData,
    isLoading: isRepairLoading,
    refetch: refetchRepair,
  } = useQuery({
    queryKey: ['execution-repair', activeRunId],
    queryFn: () => api.getExecutionRepair(activeRunId),
    enabled: Boolean(activeRunId),
    refetchInterval: (query) => {
      const rep = query.state.data;
      if (rep && ['queued', 'analyzing', 'repairing', 'running_checks'].includes(rep.status)) {
        return 2000;
      }
      return false;
    },
  });

  // 8. Start repair mutation
  const startRepairMutation = useMutation({
    mutationFn: () =>
      api.startExecutionRepair(activeRunId, {
        verification_commands: selectedChecks,
      }),
    onSuccess: () => {
      refetchRepair();
      refetchActiveRun();
      refetchRuns();
    },
  });

  // 9. Cancel repair mutation
  const cancelRepairMutation = useMutation({
    mutationFn: () => api.cancelRepairRun(repairData?.id),
    onSuccess: () => {
      refetchRepair();
      refetchActiveRun();
    },
  });

  // 10. Publishing Precheck Query (Phase 9)
  const {
    data: precheckData,
    isLoading: isPrecheckLoading,
    refetch: refetchPrecheck,
  } = useQuery({
    queryKey: ['publishing-precheck', activeRunId, task?.workspace_id],
    queryFn: () => api.getPublishingPrecheck(activeRunId, task?.workspace_id),
    enabled: Boolean(activeRunId && (activeRun?.status === 'completed' || activeRun?.status === 'repaired')),
  });

  // 11. Publishing Status Query (Phase 9)
  const {
    data: publishingData,
    isLoading: isPublishingLoading,
    refetch: refetchPublishing,
  } = useQuery({
    queryKey: ['publishing-run', activeRunId, task?.workspace_id],
    queryFn: () => api.getExecutionPublishing(activeRunId, task?.workspace_id),
    enabled: Boolean(activeRunId),
    refetchInterval: (query) => {
      const pub = query.state.data;
      if (pub && ['preparing', 'pushing_branch', 'creating_pr'].includes(pub.status)) {
        return 2000;
      }
      return false;
    },
  });

  // 12. Approve Publishing Mutation
  const approvePublishingMutation = useMutation({
    mutationFn: () => {
      setPublishError('');
      const patchHash = precheckData?.current_patch_hash || activeRun?.patches?.[0]?.patch_hash;
      const wsId = task?.workspace_id || activeRun?.workspace_id;
      return api.approvePublishing(activeRunId, patchHash, wsId);
    },
    onSuccess: () => {
      setPublishError('');
      refetchPublishing();
      refetchPrecheck();
      refetchActiveRun();
    },
    onError: (err) => {
      setPublishError(err.message || 'Failed to approve patch for publishing.');
    },
  });

  // 13. Publish to GitHub Mutation
  const publishToGitHubMutation = useMutation({
    mutationFn: () => {
      setPublishError('');
      const wsId = task?.workspace_id || activeRun?.workspace_id;
      return api.publishToGitHub(activeRunId, wsId, {});
    },
    onSuccess: () => {
      setPublishError('');
      refetchPublishing();
      refetchPrecheck();
      refetchActiveRun();
      queryClient.invalidateQueries({ queryKey: ['task', task?.id] });
    },
    onError: (err) => {
      setPublishError(err.message || 'Failed to publish Pull Request to GitHub.');
    },
  });

  // 14. Retry Publishing Mutation
  const retryPublishingMutation = useMutation({
    mutationFn: () => {
      setPublishError('');
      const wsId = task?.workspace_id || activeRun?.workspace_id;
      return api.retryPublishing(publishingData?.id, wsId);
    },
    onSuccess: () => {
      setPublishError('');
      refetchPublishing();
      refetchPrecheck();
      refetchActiveRun();
    },
    onError: (err) => {
      setPublishError(err.message || 'Failed to retry publishing.');
    },
  });

  const patch = activeRun?.patches?.[0];
  const checks = activeRun?.verification_results || [];

  const toggleCheck = (checkKey) => {
    setSelectedChecks((prev) =>
      prev.includes(checkKey) ? prev.filter((k) => k !== checkKey) : [...prev, checkKey]
    );
  };

  const renderDiffLine = (line, idx) => {
    if (line.startsWith('diff --git') || line.startsWith('index ')) {
      return (
        <div key={idx} className="bg-zinc-900/80 text-zinc-300 font-bold px-2 py-0.5 border-y border-zinc-800">
          {line}
        </div>
      );
    }
    if (line.startsWith('@@')) {
      return (
        <div key={idx} className="bg-sky-950/40 text-sky-400 px-2 py-0.5 font-mono text-xs">
          {line}
        </div>
      );
    }
    if (line.startsWith('+') && !line.startsWith('+++')) {
      return (
        <div key={idx} className="bg-emerald-950/50 text-emerald-300 px-2 py-0.5 font-mono text-xs flex">
          <span className="w-5 select-none text-emerald-600 font-bold">+</span>
          <span className="flex-1 whitespace-pre">{line.slice(1)}</span>
        </div>
      );
    }
    if (line.startsWith('-') && !line.startsWith('---')) {
      return (
        <div key={idx} className="bg-rose-950/50 text-rose-300 px-2 py-0.5 font-mono text-xs flex">
          <span className="w-5 select-none text-rose-600 font-bold">-</span>
          <span className="flex-1 whitespace-pre">{line.slice(1)}</span>
        </div>
      );
    }
    return (
      <div key={idx} className="text-zinc-400 px-2 py-0.5 font-mono text-xs flex">
        <span className="w-5 select-none text-zinc-600"> </span>
        <span className="flex-1 whitespace-pre">{line.startsWith(' ') ? line.slice(1) : line}</span>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md">
      <div className="relative w-full max-w-5xl max-h-[92vh] flex flex-col bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden text-zinc-100">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800/80 bg-zinc-900/40">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-[#CCFF00]/10 border border-[#CCFF00]/30 text-[#CCFF00]">
              <Play className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white flex items-center space-x-2">
                <span>Isolated Code Execution & Verification</span>
              </h2>
              <p className="text-xs text-zinc-400">
                Task: <span className="text-zinc-200 font-medium">{task?.title}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {activeRun && (
              <span
                className={`px-2.5 py-1 rounded-full text-xs font-mono uppercase tracking-wider font-semibold border ${
                  STATUS_BADGES[activeRun.status] || 'bg-zinc-800 text-zinc-300'
                }`}
              >
                {activeRun.status.replace(/_/g, ' ')}
              </span>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* Metadata & Status Bar */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 p-3.5 rounded-xl bg-zinc-900/30 border border-zinc-800/80 text-xs">
            <div>
              <span className="text-zinc-500 block mb-0.5">Base Commit SHA</span>
              <span className="font-mono text-zinc-200 flex items-center space-x-1">
                <GitCommit className="w-3.5 h-3.5 text-zinc-400" />
                <span>{activeRun?.base_commit_sha?.slice(0, 10) || plan?.base_commit_sha?.slice(0, 10) || 'HEAD'}</span>
              </span>
            </div>
            <div>
              <span className="text-zinc-500 block mb-0.5">Sandbox Runtime</span>
              <span className="text-zinc-200 flex items-center space-x-1">
                <Boxes className="w-3.5 h-3.5 text-sky-400" />
                <span>{activeRun?.sandbox_provider || 'Docker Container'}</span>
              </span>
            </div>
            <div>
              <span className="text-zinc-500 block mb-0.5">Cleanup Status</span>
              <span
                className={`font-semibold flex items-center space-x-1 ${
                  activeRun?.cleanup_status === 'cleaned'
                    ? 'text-emerald-400'
                    : activeRun?.cleanup_status === 'cleanup_failed'
                    ? 'text-rose-400'
                    : 'text-zinc-400'
                }`}
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{activeRun?.cleanup_status || 'Pending'}</span>
              </span>
            </div>
            <div className="flex items-center justify-end">
              {!activeRun && (
                <button
                  onClick={() => startExecutionMutation.mutate()}
                  disabled={startExecutionMutation.isPending}
                  className="px-4 py-2 rounded-lg bg-[#CCFF00] hover:bg-[#b8e600] text-black font-semibold text-xs transition flex items-center space-x-1.5 shadow-lg shadow-[#CCFF00]/10"
                >
                  {startExecutionMutation.isPending ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Preparing...</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5" />
                      <span>Prepare Changes</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {/* Mutation Error Banner if Prepare Changes Fails */}
          {startExecutionMutation.error && (
            <div className="p-3.5 rounded-lg bg-rose-950/40 border border-rose-800/80 text-rose-300 text-xs flex items-start space-x-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block">Failed to Prepare Changes</span>
                <span>{startExecutionMutation.error.message || 'An error occurred while preparing changes.'}</span>
              </div>
            </div>
          )}

          {/* Safe Error Banner if Failed */}
          {activeRun?.safe_error_summary && (
            <div className="p-3.5 rounded-lg bg-rose-950/40 border border-rose-800/80 text-rose-300 text-xs flex items-start space-x-2">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block">Execution Warning</span>
                <span>{activeRun.safe_error_summary}</span>
              </div>
            </div>
          )}

          {/* Active Run Lifecycle Views */}
          {activeRun && (
            <div className="space-y-6">
              
              {/* State 1: Preparing */}
              {activeRun.status === 'preparing' && (
                <div className="py-12 text-center space-y-3">
                  <RefreshCw className="w-8 h-8 animate-spin text-[#CCFF00] mx-auto" />
                  <h3 className="text-sm font-semibold text-white">Preparing Repository Snapshot & Patch Proposal</h3>
                  <p className="text-xs text-zinc-400 max-w-md mx-auto">
                    Retrieving exact snapshot at commit <span className="font-mono text-zinc-200">{activeRun.base_commit_sha?.slice(0, 7)}</span> and validating patch proposals against security policies.
                  </p>
                </div>
              )}

              {/* State 2: Awaiting Patch Approval */}
              {activeRun.status === 'awaiting_patch_approval' && patch && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3.5 rounded-lg bg-amber-950/30 border border-amber-800/50">
                    <div className="flex items-center space-x-2">
                      <ShieldCheck className="w-5 h-5 text-amber-400" />
                      <div>
                        <h4 className="text-xs font-semibold text-amber-200">Patch Proposal Ready for Review</h4>
                        <p className="text-[11px] text-zinc-400">
                          Review the proposed changes below. Human approval is strictly required before any code can be applied in the sandbox.
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => setShowRejectInput(!showRejectInput)}
                        className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs transition"
                      >
                        Reject
                      </button>
                      <button
                        onClick={() => approveMutation.mutate()}
                        disabled={approveMutation.isPending}
                        className="px-4 py-1.5 rounded-lg bg-[#CCFF00] hover:bg-[#b8e600] text-black font-semibold text-xs transition flex items-center space-x-1"
                      >
                        {approveMutation.isPending ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Check className="w-3.5 h-3.5" />
                        )}
                        <span>Approve & Run Checks</span>
                      </button>
                    </div>
                  </div>

                  {showRejectInput && (
                    <div className="p-3.5 rounded-lg bg-zinc-900 border border-zinc-800 space-y-2">
                      <label className="text-xs text-zinc-300 font-medium block">Reason for Rejection</label>
                      <input
                        type="text"
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                        placeholder="e.g. Inappropriate files touched, needs revision..."
                        className="w-full px-3 py-1.5 rounded bg-zinc-950 border border-zinc-700 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-[#CCFF00]"
                      />
                      <div className="flex justify-end space-x-2">
                        <button
                          onClick={() => setShowRejectInput(false)}
                          className="px-2.5 py-1 text-xs text-zinc-400 hover:text-white"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => rejectMutation.mutate()}
                          disabled={rejectMutation.isPending}
                          className="px-3 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold"
                        >
                          Confirm Rejection
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Verification Commands Selection */}
                  <div className="p-3.5 rounded-lg bg-zinc-900/40 border border-zinc-800 space-y-2">
                    <span className="text-xs font-semibold text-white block">Permitted Verification Checks</span>
                    <div className="flex flex-wrap gap-2 text-xs">
                      {['syntax_check', 'pytest', 'ruff_check'].map((cmd) => (
                        <label
                          key={cmd}
                          className={`flex items-center space-x-1.5 px-2.5 py-1 rounded cursor-pointer border transition ${
                            selectedChecks.includes(cmd)
                              ? 'bg-[#CCFF00]/10 border-[#CCFF00]/40 text-[#CCFF00]'
                              : 'bg-zinc-800/40 border-zinc-700 text-zinc-400'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={selectedChecks.includes(cmd)}
                            onChange={() => toggleCheck(cmd)}
                            className="hidden"
                          />
                          <span>{cmd}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Diff Viewer */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs text-zinc-400 px-1">
                      <span className="font-semibold text-white flex items-center space-x-1.5">
                        <FileCode className="w-4 h-4 text-[#CCFF00]" />
                        <span>Proposed Patch ({patch.changed_files_count} file(s))</span>
                      </span>
                      <div className="space-x-3 font-mono">
                        <span className="text-emerald-400">+{patch.additions_count}</span>
                        <span className="text-rose-400">-{patch.deletions_count}</span>
                      </div>
                    </div>

                    <div className="rounded-xl border border-zinc-800 bg-zinc-950 overflow-hidden max-h-[350px] overflow-y-auto">
                      <div className="p-2 divide-y divide-zinc-900">
                        {patch.raw_diff.split('\n').map((line, idx) => renderDiffLine(line, idx))}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* State 3: Execution in Progress */}
              {['applying_patch', 'running_checks'].includes(activeRun.status) && (
                <div className="py-12 text-center space-y-4">
                  <RefreshCw className="w-8 h-8 animate-spin text-[#CCFF00] mx-auto" />
                  <h3 className="text-sm font-semibold text-white">
                    {activeRun.status === 'applying_patch' ? 'Applying Patch in Sandbox...' : 'Running Permitted Verification Checks...'}
                  </h3>
                  <p className="text-xs text-zinc-400 max-w-md mx-auto">
                    The patch has been verified and applied inside the container sandbox. Running authorized verification checks without network access.
                  </p>
                  <button
                    onClick={() => cancelMutation.mutate()}
                    className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs transition"
                  >
                    Cancel Execution
                  </button>
                </div>
              )}

              {/* State 4: Completed / Terminal Verification Results */}
              {['completed', 'failed', 'timed_out', 'cancelled'].includes(activeRun.status) && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 flex items-center space-x-1.5">
                      <Terminal className="w-4 h-4 text-[#CCFF00]" />
                      <span>Verification Results & Evidence</span>
                    </h3>
                    <span className="text-xs text-zinc-500 font-mono">
                      Completed at {new Date(activeRun.completed_at || activeRun.updated_at).toLocaleTimeString()}
                    </span>
                  </div>

                  {checks.length === 0 ? (
                    <div className="py-8 text-center text-zinc-500 text-xs rounded-lg border border-zinc-800/80 bg-zinc-900/20">
                      No verification checks were executed for this run.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {checks.map((check) => (
                        <div
                          key={check.id}
                          className="p-4 rounded-xl bg-zinc-900/40 border border-zinc-800 space-y-2.5 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center space-x-2">
                              {check.status === 'passed' ? (
                                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                              ) : check.status === 'timed_out' ? (
                                <Clock className="w-4 h-4 text-amber-400" />
                              ) : (
                                <XCircle className="w-4 h-4 text-rose-400" />
                              )}
                              <span className="font-mono text-white font-semibold">{check.command_name}</span>
                              <span className="text-zinc-500 font-mono">
                                (Exit code: {check.exit_code}, {check.duration_seconds}s)
                              </span>
                            </div>

                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-mono uppercase font-semibold ${
                                check.status === 'passed'
                                  ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/50'
                                  : check.status === 'timed_out'
                                  ? 'bg-amber-950/60 text-amber-300 border border-amber-800/50'
                                  : 'bg-rose-950/60 text-rose-300 border border-rose-800/50'
                              }`}
                            >
                              {check.status}
                            </span>
                          </div>

                          {check.stdout_excerpt && (
                            <div>
                              <span className="text-[10px] text-zinc-500 block mb-1">Standard Output</span>
                              <pre className="p-2.5 rounded bg-zinc-950 border border-zinc-800/80 font-mono text-[11px] text-zinc-300 overflow-x-auto whitespace-pre-wrap">
                                {check.stdout_excerpt}
                              </pre>
                            </div>
                          )}

                          {check.stderr_excerpt && (
                            <div>
                              <span className="text-[10px] text-rose-400 block mb-1">Standard Error</span>
                              <pre className="p-2.5 rounded bg-zinc-950 border border-rose-950/80 font-mono text-[11px] text-rose-300 overflow-x-auto whitespace-pre-wrap">
                                {check.stderr_excerpt}
                              </pre>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Bounded AI Repair Loop Section (Phase 8) */}
                  {(activeRun.status === 'failed' || checks.some((c) => c.status !== 'passed')) && (
                    <div className="pt-4 border-t border-zinc-800/80 space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <Wrench className="w-4 h-4 text-[#CCFF00]" />
                          <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
                            Bounded AI Repair Workflow
                          </h4>
                        </div>
                        {repairData && (
                          <span className={`px-2 py-0.5 rounded text-[11px] font-mono uppercase font-semibold border ${STATUS_BADGES[repairData.status] || STATUS_BADGES.queued}`}>
                            {repairData.status} ({repairData.consumed_attempts}/{repairData.max_attempts} attempts)
                          </span>
                        )}
                      </div>

                      {/* No Repair Run Yet: Prompt to Start */}
                      {!repairData && (
                        <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-3">
                          <div className="flex items-start justify-between">
                            <div className="space-y-1">
                              <div className="flex items-center space-x-2">
                                <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase font-semibold bg-rose-950/80 text-rose-300 border border-rose-800/60">
                                  {checks.some((c) => c.status === 'timed_out') ? 'Timeout Detected' : 'Test Failure Detected'}
                                </span>
                                <span className="text-xs text-zinc-300 font-medium">
                                  Corrective repair can be attempted within sandbox boundaries
                                </span>
                              </div>
                              <p className="text-[11px] text-zinc-400">
                                The AI agent will diagnose root cause from actual verification excerpts, propose a validated patch, apply it in the isolated sandbox, and rerun checks (max 3 bounded attempts).
                              </p>
                            </div>
                            <button
                              onClick={() => startRepairMutation.mutate()}
                              disabled={startRepairMutation.isPending}
                              className="px-3 py-1.5 rounded-lg bg-[#CCFF00] hover:bg-[#b8e600] text-black font-semibold text-xs transition inline-flex items-center space-x-1.5 whitespace-nowrap shadow-sm shadow-[#CCFF00]/10"
                            >
                              <Sparkles className="w-3.5 h-3.5" />
                              <span>{startRepairMutation.isPending ? 'Initiating Repair...' : 'Attempt Bounded Repair'}</span>
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Active / Completed Repair Run Display */}
                      {repairData && (
                        <div className="space-y-3">
                          {/* Active In-Progress Spinner */}
                          {['queued', 'analyzing', 'repairing', 'running_checks'].includes(repairData.status) && (
                            <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-800/40 flex items-center justify-between">
                              <div className="flex items-center space-x-3">
                                <RefreshCw className="w-5 h-5 animate-spin text-[#CCFF00]" />
                                <div>
                                  <span className="text-xs font-semibold text-white block">
                                    {repairData.status === 'analyzing'
                                      ? 'Analyzing failure evidence & diagnosing root cause...'
                                      : repairData.status === 'repairing'
                                      ? 'Applying corrective repair patch in sandbox...'
                                      : 'Rerunning permitted verification checks...'}
                                  </span>
                                  <span className="text-[11px] text-zinc-400">
                                    Server-enforced budget: {repairData.consumed_attempts} of {repairData.max_attempts} attempts used.
                                  </span>
                                </div>
                              </div>
                              <button
                                onClick={() => cancelRepairMutation.mutate()}
                                disabled={cancelRepairMutation.isPending}
                                className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs transition"
                              >
                                Cancel Repair
                              </button>
                            </div>
                          )}

                          {/* Final Outcome Banner */}
                          {repairData.status === 'completed' && (
                            <div className="p-3.5 rounded-xl bg-emerald-950/40 border border-emerald-800/50 flex items-center space-x-2.5 text-xs text-emerald-300">
                              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                              <span>
                                Repair Succeeded: All verification checks passed in the sandbox working copy on attempt {repairData.consumed_attempts}.
                              </span>
                            </div>
                          )}

                          {repairData.status === 'budget_exhausted' && (
                            <div className="p-3.5 rounded-xl bg-amber-950/40 border border-amber-800/50 flex items-center space-x-2.5 text-xs text-amber-300">
                              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                              <span>
                                Repair Budget Exhausted: Maximum allowable attempts ({repairData.max_attempts}) reached without resolving all verification failures.
                              </span>
                            </div>
                          )}

                          {repairData.status === 'non_repairable' && (
                            <div className="p-3.5 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center space-x-2.5 text-xs text-zinc-400">
                              <HelpCircle className="w-4 h-4 text-zinc-500 shrink-0" />
                              <span>
                                {repairData.safe_error_summary || 'Failure diagnosed as non-repairable by automated code changes.'}
                              </span>
                            </div>
                          )}

                          {/* Attempts History List */}
                          {repairData.attempts && repairData.attempts.length > 0 && (
                            <div className="space-y-3 pt-2">
                              <span className="text-xs font-semibold text-zinc-400 block uppercase tracking-wider">
                                Repair Attempts History ({repairData.attempts.length})
                              </span>
                              {repairData.attempts.map((att) => (
                                <div
                                  key={att.id}
                                  className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800/90 space-y-2 text-xs"
                                >
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center space-x-2">
                                      <span className="font-mono font-bold text-white">
                                        Attempt #{att.attempt_number}
                                      </span>
                                      <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-zinc-900 text-zinc-300 border border-zinc-800">
                                        {att.failure_classification?.category || 'failure'}
                                      </span>
                                    </div>
                                    <span
                                      className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase font-semibold ${
                                        att.proposal_status === 'applied'
                                          ? 'text-emerald-400 bg-emerald-950/50'
                                          : att.proposal_status === 'valid'
                                          ? 'text-blue-400 bg-blue-950/50'
                                          : 'text-rose-400 bg-rose-950/50'
                                      }`}
                                    >
                                      Proposal: {att.proposal_status}
                                    </span>
                                  </div>

                                  {att.root_cause_hypothesis && (
                                    <div className="p-2 rounded bg-zinc-900/60 border border-zinc-800/60 text-[11px] text-zinc-300">
                                      <span className="text-zinc-500 font-semibold block mb-0.5">Root Cause Hypothesis</span>
                                      {att.root_cause_hypothesis}
                                    </div>
                                  )}

                                  {att.proposed_change_summary && (
                                    <div className="text-[11px] text-zinc-400">
                                      <span className="text-zinc-500 font-semibold">Change: </span>
                                      {att.proposed_change_summary}
                                    </div>
                                  )}

                                  {att.verification_results_summary && att.verification_results_summary.length > 0 && (
                                    <div className="flex items-center space-x-2 pt-1 font-mono text-[11px]">
                                      <span className="text-zinc-500">Checks:</span>
                                      {att.verification_results_summary.map((res, i) => (
                                        <span
                                          key={i}
                                          className={`px-1.5 py-0.5 rounded ${
                                            res.status === 'passed'
                                              ? 'bg-emerald-950/60 text-emerald-400'
                                              : 'bg-rose-950/60 text-rose-400'
                                          }`}
                                        >
                                          {res.command_name}: {res.status} ({res.exit_code})
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {patch && (
                    <div className="pt-2">
                      <span className="text-xs font-semibold text-white block mb-2">Final Applied Patch Diff</span>
                      <div className="rounded-xl border border-zinc-800 bg-zinc-950 overflow-hidden max-h-[250px] overflow-y-auto">
                        <div className="p-2 divide-y divide-zinc-900">
                          {patch.raw_diff.split('\n').map((line, idx) => renderDiffLine(line, idx))}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Phase 9: Git Publishing & GitHub Pull Request Card */}
                  {(activeRun.status === 'completed' || activeRun.status === 'repaired') && (
                    <div className="pt-4 border-t border-zinc-800/80 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <GitPullRequest className="w-4 h-4 text-[#CCFF00]" />
                          <span className="text-xs font-semibold text-white uppercase tracking-wider">
                            GitHub Pull Request Publishing (Phase 9)
                          </span>
                        </div>
                        {publishingData?.status && (
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase font-semibold border ${
                              STATUS_BADGES[publishingData.status] || 'bg-zinc-800 text-zinc-300'
                            }`}
                          >
                            {publishingData.status.replace('_', ' ')}
                          </span>
                        )}
                      </div>

                      {/* Case 1: Pull Request successfully published */}
                      {publishingData?.status === 'completed' && publishingData?.pr_url && (
                        <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-500/40 space-y-3">
                          <div className="flex items-start justify-between">
                            <div className="space-y-1">
                              <div className="flex items-center space-x-2">
                                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                <span className="text-sm font-semibold text-white">
                                  Pull Request Published!
                                </span>
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-900/60 text-emerald-300 border border-emerald-700">
                                  #{publishingData.pr_number} ({publishingData.pr_state})
                                </span>
                              </div>
                              <p className="text-xs text-zinc-300">{publishingData.pr_title}</p>
                            </div>
                            <a
                              href={publishingData.pr_url}
                              target="_blank"
                              rel="noreferrer"
                              className="px-3 py-1.5 rounded-lg bg-[#CCFF00] hover:bg-[#b8e600] text-black font-semibold text-xs transition inline-flex items-center space-x-1"
                            >
                              <span>View on GitHub</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>

                          <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-zinc-400 bg-zinc-950/80 p-2.5 rounded-lg border border-zinc-800">
                            <div>
                              <span className="text-zinc-500 block">Branch:</span>
                              <span className="text-white truncate block">{publishingData.head_branch}</span>
                            </div>
                            <div>
                              <span className="text-zinc-500 block">Commit SHA:</span>
                              <span className="text-zinc-300">{publishingData.head_commit_sha?.slice(0, 8)}</span>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Case 2: In progress */}
                      {['preparing', 'pushing_branch', 'creating_pr'].includes(publishingData?.status) && (
                        <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-700/50 space-y-2 text-center py-6">
                          <RefreshCw className="w-6 h-6 text-indigo-400 animate-spin mx-auto" />
                          <h4 className="text-xs font-semibold text-white capitalize">
                            {publishingData.status.replace('_', ' ')}...
                          </h4>
                          <p className="text-[11px] text-zinc-400">
                            Creating task branch and opening verified Pull Request on GitHub.
                          </p>
                        </div>
                      )}

                      {/* Case 3: Failed / Stale base conflict */}
                      {(publishingData?.status === 'failed' || publishingData?.status === 'stale_base_conflict') && (
                        <div className="p-3.5 rounded-xl bg-rose-950/30 border border-rose-800/60 space-y-2 text-xs">
                          <div className="flex items-center space-x-2 text-rose-300 font-semibold">
                            <AlertTriangle className="w-4 h-4 text-rose-400" />
                            <span>Publishing Error: {publishingData.status.replace('_', ' ')}</span>
                          </div>
                          {publishingData.safe_error_summary && (
                            <p className="text-[11px] text-zinc-300 bg-zinc-950/80 p-2 rounded border border-zinc-800 font-mono">
                              {publishingData.safe_error_summary}
                            </p>
                          )}
                          <div className="flex justify-end pt-1">
                            <button
                              onClick={() => retryPublishingMutation.mutate()}
                              disabled={retryPublishingMutation.isPending}
                              className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white font-semibold text-xs transition inline-flex items-center space-x-1.5"
                            >
                              <RotateCcw className="w-3 h-3" />
                              <span>Retry Publishing</span>
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Case 4: Not yet published or pending approval */}
                      {(!publishingData || ['pending_approval', 'approved'].includes(publishingData.status)) && (
                        <div className="p-3.5 rounded-xl bg-zinc-950 border border-zinc-800 space-y-3">
                          {/* Precheck items */}
                          <div className="space-y-1.5 text-xs">
                            <div className="flex items-center justify-between text-zinc-300">
                              <span className="flex items-center space-x-1.5">
                                <CheckCircle2 className={`w-3.5 h-3.5 ${precheckData?.verification_passed ? 'text-emerald-400' : 'text-zinc-600'}`} />
                                <span>Verification Checks Passed</span>
                              </span>
                              <span className="font-mono text-[11px] text-zinc-400">
                                {precheckData?.passed_checks_count || 0} passed, {precheckData?.failed_checks_count || 0} failed
                              </span>
                            </div>

                            <div className="flex items-center justify-between text-zinc-300">
                              <span className="flex items-center space-x-1.5">
                                <CheckCircle2 className={`w-3.5 h-3.5 ${!precheckData?.is_base_stale ? 'text-emerald-400' : 'text-amber-400'}`} />
                                <span>Base Branch Freshness</span>
                              </span>
                              <span className="font-mono text-[11px] text-zinc-400">
                                {precheckData?.remote_base_sha ? `${precheckData.remote_base_sha.slice(0, 8)} (${precheckData.default_branch})` : 'checked'}
                              </span>
                            </div>

                            <div className="flex items-center justify-between text-zinc-300">
                              <span className="flex items-center space-x-1.5">
                                <CheckCircle2 className={`w-3.5 h-3.5 ${precheckData?.is_approved ? 'text-emerald-400' : 'text-zinc-600'}`} />
                                <span>Explicit User Approval</span>
                              </span>
                              <span className="font-mono text-[11px]">
                                {precheckData?.is_approved ? (
                                  <span className="text-emerald-400">Approved</span>
                                ) : (
                                  <span className="text-amber-400">Approval Required</span>
                                )}
                              </span>
                            </div>
                          </div>

                          {/* Blockers list */}
                          {precheckData?.blockers && precheckData.blockers.length > 0 && (
                            <div className="p-2 rounded bg-zinc-900/60 border border-zinc-800/60 text-[11px] text-amber-300/90 space-y-1">
                              {precheckData.blockers.map((b, i) => (
                                <div key={i} className="flex items-center space-x-1.5">
                                  <AlertTriangle className="w-3 h-3 flex-shrink-0 text-amber-400" />
                                  <span>{b}</span>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Error Banner */}
                          {publishError && (
                            <div className="p-2.5 rounded-lg bg-rose-950/60 border border-rose-800/80 text-xs text-rose-300 flex items-center space-x-2">
                              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                              <span>{publishError}</span>
                            </div>
                          )}

                          {/* Action Buttons */}
                          <div className="flex items-center justify-between pt-1">
                            <span className="text-[11px] text-zinc-500">
                              {precheckData?.repository_full_name ? `Target: ${precheckData.repository_full_name}` : 'GitHub repository connected'}
                            </span>
                            <div className="flex items-center space-x-2">
                              {!precheckData?.is_approved && (
                                <button
                                  onClick={() => approvePublishingMutation.mutate()}
                                  disabled={approvePublishingMutation.isPending || !precheckData?.verification_passed}
                                  className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-white font-semibold text-xs transition inline-flex items-center space-x-1.5"
                                >
                                  <Check className="w-3 h-3 text-emerald-400" />
                                  <span>{approvePublishingMutation.isPending ? 'Approving...' : 'Approve for Publishing'}</span>
                                </button>
                              )}

                              {precheckData?.is_approved && (
                                <button
                                  onClick={() => publishToGitHubMutation.mutate()}
                                  disabled={publishToGitHubMutation.isPending || !precheckData?.can_publish}
                                  className="px-4 py-1.5 rounded-lg bg-[#CCFF00] hover:bg-[#b8e600] disabled:opacity-50 text-black font-semibold text-xs transition inline-flex items-center space-x-1.5"
                                >
                                  <Send className="w-3 h-3" />
                                  <span>{publishToGitHubMutation.isPending ? 'Publishing...' : 'Publish Pull Request'}</span>
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Empty state: No active runs */}
          {!activeRun && runsList.length === 0 && (
            <div className="py-16 text-center space-y-3">
              <ShieldCheck className="w-10 h-10 text-zinc-600 mx-auto" />
              <h3 className="text-sm font-semibold text-white">No Execution Runs Yet</h3>
              <p className="text-xs text-zinc-400 max-w-sm mx-auto">
                Prepare an isolated working copy to generate a verified patch and run automated checks.
              </p>
              <button
                onClick={() => startExecutionMutation.mutate()}
                disabled={startExecutionMutation.isPending}
                className="px-4 py-2 rounded-lg bg-[#CCFF00] hover:bg-[#b8e600] text-black font-semibold text-xs transition inline-flex items-center space-x-1.5"
              >
                <Play className="w-3.5 h-3.5" />
                <span>Prepare Changes</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
