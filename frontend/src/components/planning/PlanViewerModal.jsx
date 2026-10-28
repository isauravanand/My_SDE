import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../lib/api';

export default function PlanViewerModal({ task, workspaceId, repository, onClose }) {
  const queryClient = useQueryClient();
  const [selectedPlanId, setSelectedPlanId] = useState(null);
  const [activeTab, setActiveTab] = useState('steps'); // 'steps', 'overview', 'evidence', 'history'
  const [expandedStepId, setExpandedStepId] = useState(null);

  // 1. Fetch latest plan or specific plan if selected
  const {
    data: planResponse,
    isLoading: isPlanLoading,
    isError: isPlanError,
    error: planError,
    refetch: refetchPlan,
  } = useQuery({
    queryKey: ['task-plan', task?.id, selectedPlanId],
    queryFn: async () => {
      if (selectedPlanId) {
        return await api.getImplementationPlan(selectedPlanId, workspaceId);
      }
      return await api.getLatestTaskPlan(task?.id);
    },
    enabled: Boolean(task?.id),
    staleTime: 10000,
  });

  // 2. Fetch plan history
  const { data: planHistory = [] } = useQuery({
    queryKey: ['task-plans-history', task?.id],
    queryFn: () => api.listTaskPlans(task?.id, 10, 0),
    enabled: Boolean(task?.id),
    staleTime: 15000,
  });

  // 3. Trigger new planning run mutation
  const triggerPlanMutation = useMutation({
    mutationFn: (forceNew = true) => api.triggerTaskPlanning(task.id, { force_new: forceNew }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ['task-plan', task?.id] });
      queryClient.invalidateQueries({ queryKey: ['task-plans-history', task?.id] });
      // Poll planning run status until completed or terminal
      startPollingRun(run.id);
    },
  });

  const [activeRun, setActiveRun] = useState(null);

  const startPollingRun = (runId) => {
    setActiveRun({ id: runId, status: 'running' });
    const interval = setInterval(async () => {
      try {
        const runDetail = await api.getPlanningRun(runId, workspaceId);
        setActiveRun(runDetail);
        if (['completed', 'failed', 'cancelled', 'needs_context'].includes(runDetail.status)) {
          clearInterval(interval);
          queryClient.invalidateQueries({ queryKey: ['task-plan', task?.id] });
          queryClient.invalidateQueries({ queryKey: ['task-plans-history', task?.id] });
        }
      } catch (err) {
        clearInterval(interval);
      }
    }, 2000);
  };

  const plan = planResponse?.plan_data;

  const getChangeTypeColor = (type) => {
    switch (type) {
      case 'create':
        return 'bg-blue-900/40 text-blue-300 border-blue-700/60';
      case 'modify':
        return 'bg-amber-900/40 text-amber-300 border-amber-700/60';
      case 'delete':
        return 'bg-rose-900/40 text-rose-300 border-rose-700/60';
      case 'test':
        return 'bg-purple-900/40 text-purple-300 border-purple-700/60';
      case 'configuration':
        return 'bg-cyan-900/40 text-cyan-300 border-cyan-700/60';
      default:
        return 'bg-zinc-800 text-zinc-300 border-zinc-700';
    }
  };

  const getLocationBadge = (status) => {
    switch (status) {
      case 'verified_existing':
        return <span className="px-2 py-0.5 rounded text-xs font-medium bg-[#CCFF00]/10 text-[#CCFF00] border border-[#CCFF00]/30">Verified Code</span>;
      case 'proposed_new':
        return <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/30">Proposed New</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-xs font-medium bg-zinc-700/30 text-zinc-400 border border-zinc-600">Hypothetical</span>;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-zinc-950 border border-zinc-800 rounded-xl shadow-2xl overflow-hidden text-zinc-100">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800/80 bg-zinc-900/40">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-[#CCFF00]/10 border border-[#CCFF00]/30 flex items-center justify-center text-[#CCFF00] font-bold text-sm">
              AI
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-lg font-semibold text-white">Implementation Plan</h2>
                <span className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono">
                  {plan?.schema_version || 'mysde.plan.v1'}
                </span>
              </div>
              <p className="text-xs text-zinc-400 truncate max-w-lg">{task?.title}</p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => triggerPlanMutation.mutate(true)}
              disabled={triggerPlanMutation.isPending || activeRun?.status === 'running'}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-[#CCFF00] text-black hover:bg-[#b8e600] disabled:opacity-50 transition-colors flex items-center space-x-1.5 shadow-sm"
            >
              {triggerPlanMutation.isPending || activeRun?.status === 'running' ? (
                <>
                  <span className="animate-spin w-3 h-3 border-2 border-black border-t-transparent rounded-full" />
                  <span>Planning...</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <span>{plan ? 'Regenerate Plan' : 'Generate Plan'}</span>
                </>
              )}
            </button>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Status / Active Run Banner */}
        {activeRun && activeRun.status === 'running' && (
          <div className="px-6 py-2.5 bg-zinc-900/90 border-b border-zinc-800 flex items-center justify-between text-xs text-zinc-300">
            <div className="flex items-center space-x-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#CCFF00] opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[#CCFF00]"></span>
              </span>
              <span>LangGraph orchestration running: retrieving context and synthesizing steps...</span>
            </div>
            <button
              onClick={async () => {
                await api.cancelPlanningRun(activeRun.id, workspaceId);
                setActiveRun(null);
                refetchPlan();
              }}
              className="text-rose-400 hover:text-rose-300 hover:underline"
            >
              Cancel
            </button>
          </div>
        )}

        {activeRun?.status === 'needs_context' && (
          <div className="px-6 py-3 bg-amber-950/40 border-b border-amber-800/60 text-xs text-amber-200 flex items-start space-x-2">
            <svg className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <p className="font-semibold text-amber-300">Prerequisites Required</p>
              <p>{activeRun.error_summary || 'Task requirements or repository indexing is missing.'}</p>
            </div>
          </div>
        )}

        {activeRun?.status === 'failed' && (
          <div className="px-6 py-3 bg-rose-950/40 border-b border-rose-800/60 text-xs text-rose-200 flex items-start space-x-2">
            <svg className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="font-semibold text-rose-300">Planning Execution Failed</p>
              <p>{activeRun.error_summary || 'An unexpected error occurred during workflow execution.'}</p>
            </div>
          </div>
        )}

        {/* Metadata bar */}
        {plan && (
          <div className="px-6 py-2 bg-zinc-900/60 border-b border-zinc-800/60 flex items-center justify-between text-xs text-zinc-400">
            <div className="flex items-center space-x-4">
              {plan.base_commit_sha && (
                <div className="flex items-center space-x-1.5">
                  <span className="text-zinc-500">Commit:</span>
                  <span className="font-mono text-zinc-300">{plan.base_commit_sha.slice(0, 7)}</span>
                </div>
              )}
              <div className="flex items-center space-x-1.5">
                <span className="text-zinc-500">Steps:</span>
                <span className="text-zinc-300">{plan.implementation_steps?.length || 0}</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <span className="text-zinc-500">Evidence Chunks:</span>
                <span className="text-zinc-300">{plan.evidence?.length || 0}</span>
              </div>
            </div>

            {/* Plan History Selector */}
            {planHistory.length > 1 && (
              <div className="flex items-center space-x-1.5">
                <span className="text-zinc-500">History:</span>
                <select
                  value={selectedPlanId || planResponse?.id || ''}
                  onChange={(e) => setSelectedPlanId(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 rounded px-2 py-0.5 text-xs text-zinc-200 focus:outline-none focus:border-[#CCFF00]"
                >
                  {planHistory.map((p, idx) => (
                    <option key={p.id} value={p.id}>
                      {idx === 0 ? 'Latest Plan' : `Plan ${idx + 1}`} ({new Date(p.created_at).toLocaleTimeString()})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}

        {/* Tab Navigation */}
        {plan && (
          <div className="flex border-b border-zinc-800 px-6 bg-zinc-950">
            <button
              onClick={() => setActiveTab('steps')}
              className={`py-2.5 px-3 text-xs font-medium border-b-2 transition-colors ${
                activeTab === 'steps'
                  ? 'border-[#CCFF00] text-[#CCFF00]'
                  : 'border-transparent text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Steps ({plan.implementation_steps?.length || 0})
            </button>
            <button
              onClick={() => setActiveTab('overview')}
              className={`py-2.5 px-3 text-xs font-medium border-b-2 transition-colors ${
                activeTab === 'overview'
                  ? 'border-[#CCFF00] text-[#CCFF00]'
                  : 'border-transparent text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Strategy & Scope
            </button>
            <button
              onClick={() => setActiveTab('evidence')}
              className={`py-2.5 px-3 text-xs font-medium border-b-2 transition-colors ${
                activeTab === 'evidence'
                  ? 'border-[#CCFF00] text-[#CCFF00]'
                  : 'border-transparent text-zinc-400 hover:text-zinc-200'
              }`}
            >
              Citations & Evidence ({plan.evidence?.length || 0})
            </button>
          </div>
        )}

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isPlanLoading ? (
            <div className="py-20 flex flex-col items-center justify-center text-zinc-400 space-y-3">
              <div className="w-8 h-8 border-2 border-[#CCFF00] border-t-transparent rounded-full animate-spin" />
              <p className="text-sm">Loading implementation plan...</p>
            </div>
          ) : !plan ? (
            <div className="py-20 flex flex-col items-center justify-center text-center space-y-4">
              <div className="w-12 h-12 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
              </div>
              <div className="max-w-md">
                <h3 className="text-base font-medium text-white mb-1">No Implementation Plan Yet</h3>
                <p className="text-xs text-zinc-400 mb-4">
                  Trigger an autonomous LangGraph planning run to retrieve repository context and synthesize an actionable, evidence-grounded implementation plan.
                </p>
                <button
                  onClick={() => triggerPlanMutation.mutate(false)}
                  disabled={triggerPlanMutation.isPending}
                  className="px-4 py-2 text-xs font-medium rounded-lg bg-[#CCFF00] text-black hover:bg-[#b8e600] transition-colors"
                >
                  Generate Plan Now
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* TAB 1: STEPS */}
              {activeTab === 'steps' && (
                <div className="space-y-4">
                  {/* Summary Callout */}
                  <div className="p-4 rounded-lg bg-zinc-900/60 border border-zinc-800 text-xs space-y-2">
                    <span className="font-semibold text-zinc-200 uppercase tracking-wider text-[10px]">Executive Summary</span>
                    <p className="text-zinc-300 leading-relaxed">{plan.summary}</p>
                  </div>

                  {/* Steps List */}
                  <div className="space-y-3">
                    {plan.implementation_steps?.map((step) => {
                      const isExpanded = expandedStepId === step.step_id;
                      return (
                        <div
                          key={step.step_id}
                          className="border border-zinc-800 bg-zinc-900/40 rounded-lg overflow-hidden transition-all"
                        >
                          <div
                            onClick={() => setExpandedStepId(isExpanded ? null : step.step_id)}
                            className="p-4 flex items-center justify-between cursor-pointer hover:bg-zinc-800/40 transition-colors"
                          >
                            <div className="flex items-center space-x-3">
                              <span className="w-6 h-6 rounded-full bg-zinc-800 text-zinc-300 text-xs font-mono font-bold flex items-center justify-center shrink-0">
                                {step.order}
                              </span>
                              <div>
                                <div className="flex items-center space-x-2">
                                  <h4 className="text-sm font-medium text-white">{step.title}</h4>
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getChangeTypeColor(step.change_type)}`}>
                                    {step.change_type}
                                  </span>
                                  {getLocationBadge(step.location_status)}
                                </div>
                                <p className="text-xs text-zinc-400 line-clamp-1 mt-0.5">{step.description}</p>
                              </div>
                            </div>

                            <svg
                              className={`w-4 h-4 text-zinc-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                            </svg>
                          </div>

                          {isExpanded && (
                            <div className="px-4 pb-4 pt-2 border-t border-zinc-800/60 space-y-3 text-xs">
                              <div>
                                <span className="text-[10px] uppercase font-semibold text-zinc-500">Details & Rationale</span>
                                <p className="text-zinc-300 mt-0.5 leading-relaxed">{step.description}</p>
                                <p className="text-zinc-400 italic mt-1">{step.rationale}</p>
                              </div>

                              {step.relevant_files?.length > 0 && (
                                <div>
                                  <span className="text-[10px] uppercase font-semibold text-zinc-500">Relevant Files</span>
                                  <div className="flex flex-wrap gap-1.5 mt-1">
                                    {step.relevant_files.map((file, i) => (
                                      <span key={i} className="px-2 py-0.5 rounded bg-zinc-800 font-mono text-[11px] text-zinc-300">
                                        {file}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {step.evidence_refs?.length > 0 && (
                                <div>
                                  <span className="text-[10px] uppercase font-semibold text-zinc-500">Cited Code Evidence</span>
                                  <div className="flex flex-wrap gap-1.5 mt-1">
                                    {step.evidence_refs.map((evId) => (
                                      <span
                                        key={evId}
                                        onClick={() => setActiveTab('evidence')}
                                        className="px-2 py-0.5 rounded bg-[#CCFF00]/10 text-[#CCFF00] border border-[#CCFF00]/20 font-mono text-[11px] cursor-pointer hover:underline"
                                      >
                                        {evId}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              <div>
                                <span className="text-[10px] uppercase font-semibold text-zinc-500">Verification Instructions</span>
                                <div className="mt-1 p-2 rounded bg-zinc-950 border border-zinc-800 font-mono text-zinc-300 text-[11px]">
                                  {step.verification_instructions}
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* TAB 2: OVERVIEW & STRATEGY */}
              {activeTab === 'overview' && (
                <div className="space-y-6 text-xs">
                  <div>
                    <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Task Understanding</h4>
                    <div className="p-4 rounded-lg bg-zinc-900/50 border border-zinc-800 text-zinc-300 leading-relaxed">
                      {plan.task_understanding}
                    </div>
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Affected Components</h4>
                    <div className="flex flex-wrap gap-2">
                      {plan.affected_components?.map((c, i) => (
                        <span key={i} className="px-2.5 py-1 rounded-md bg-zinc-800 text-zinc-200 border border-zinc-700 font-mono">
                          {c}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Key Assumptions</h4>
                      <ul className="list-disc list-inside space-y-1 text-zinc-300 p-3 rounded-lg bg-zinc-900/30 border border-zinc-800">
                        {plan.assumptions?.length ? plan.assumptions.map((a, i) => <li key={i}>{a}</li>) : <li className="text-zinc-500">None declared</li>}
                      </ul>
                    </div>

                    <div>
                      <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Unknowns & Hypotheses</h4>
                      <ul className="list-disc list-inside space-y-1 text-zinc-300 p-3 rounded-lg bg-zinc-900/30 border border-zinc-800">
                        {plan.unknowns?.length ? plan.unknowns.map((u, i) => <li key={i}>{u}</li>) : <li className="text-zinc-500">None identified</li>}
                      </ul>
                    </div>
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Testing Strategy</h4>
                    <div className="p-4 rounded-lg bg-zinc-900/50 border border-zinc-800 text-zinc-300 leading-relaxed">
                      {plan.testing_strategy}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Risks & Trade-offs</h4>
                      <ul className="list-disc list-inside space-y-1 text-zinc-300 p-3 rounded-lg bg-zinc-900/30 border border-zinc-800">
                        {plan.risks?.length ? plan.risks.map((r, i) => <li key={i}>{r}</li>) : <li className="text-zinc-500">None declared</li>}
                      </ul>
                    </div>

                    <div>
                      <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Security Considerations</h4>
                      <ul className="list-disc list-inside space-y-1 text-zinc-300 p-3 rounded-lg bg-zinc-900/30 border border-zinc-800">
                        {plan.security_considerations?.length ? plan.security_considerations.map((s, i) => <li key={i}>{s}</li>) : <li className="text-zinc-500">None declared</li>}
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: EVIDENCE & CITATIONS */}
              {activeTab === 'evidence' && (
                <div className="space-y-4">
                  <div className="p-3 rounded-lg bg-zinc-900/40 border border-zinc-800 text-xs text-zinc-400">
                    All repository-specific claims are grounded in the Code RAG chunks below from commit <span className="font-mono text-zinc-200">{plan.base_commit_sha?.slice(0, 7) || 'HEAD'}</span>.
                  </div>

                  {plan.evidence?.length === 0 ? (
                    <div className="py-12 text-center text-zinc-500 text-xs">
                      No repository code chunks were retrieved for this plan.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {plan.evidence?.map((ev) => {
                        const repoFullName = repository?.full_name;
                        const githubUrl = repoFullName && ev.commit_sha
                          ? `https://github.com/${repoFullName}/blob/${ev.commit_sha}/${ev.file_path}#L${ev.start_line}-L${ev.end_line}`
                          : null;

                        return (
                          <div key={ev.evidence_id} className="p-4 rounded-lg bg-zinc-900/50 border border-zinc-800 space-y-2 text-xs">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center space-x-2">
                                <span className="px-2 py-0.5 rounded bg-[#CCFF00]/10 text-[#CCFF00] font-mono text-xs font-bold border border-[#CCFF00]/30">
                                  {ev.evidence_id}
                                </span>
                                <span className="font-mono text-white">{ev.file_path}</span>
                                <span className="text-zinc-500">Lines {ev.start_line}-{ev.end_line}</span>
                              </div>

                              {githubUrl && (
                                <a
                                  href={githubUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-xs text-[#CCFF00] hover:underline flex items-center space-x-1"
                                >
                                  <span>View on GitHub</span>
                                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                  </svg>
                                </a>
                              )}
                            </div>

                            {ev.relevance_summary && (
                              <p className="text-zinc-400 text-[11px]">{ev.relevance_summary}</p>
                            )}

                            <pre className="p-2.5 rounded bg-zinc-950 border border-zinc-800/80 font-mono text-[11px] text-zinc-300 overflow-x-auto">
                              {ev.excerpt}
                            </pre>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
