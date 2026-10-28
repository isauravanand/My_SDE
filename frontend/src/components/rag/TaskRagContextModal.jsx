import React from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  X,
  FileCode,
  Sparkles,
  ExternalLink,
  AlertCircle,
  RefreshCw,
  GitBranch,
  ShieldCheck,
} from 'lucide-react';
import { api } from '../../lib/api';

export function TaskRagContextModal({ task, onClose }) {
  const {
    data: ragData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['task-rag-context', task.id],
    queryFn: () => api.retrieveTaskContext(task.id, 5),
    staleTime: 60000,
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-3xl max-h-[88vh] flex flex-col rounded-lg bg-background-card border border-border-strong shadow-card text-left overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border-subtle bg-background-subtle/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded bg-accent/10 border border-accent/20 text-accent">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-content-primary">Relevant Code Context</h3>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-background-subtle border border-border-subtle text-content-muted">
                  Task RAG
                </span>
              </div>
              <p className="text-xs text-content-muted mt-0.5 truncate max-w-lg">
                Task: &ldquo;{task.title}&rdquo;
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-content-secondary hover:text-content-primary hover:bg-background-subtle transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Informational Scope Boundary Callout */}
          <div className="p-3 rounded-lg bg-background-subtle border border-border-subtle text-xs text-content-secondary flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-accent shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-content-primary">Human-in-the-Loop Retrieval Preview</p>
              <p className="text-[11px] text-content-muted mt-0.5">
                These code sections have been retrieved from the connected repository based on your task specification. No automated code changes, branches, or PRs will be created in this phase.
              </p>
            </div>
          </div>

          {isLoading ? (
            <div className="p-8 text-center text-xs text-content-muted space-y-2">
              <RefreshCw className="w-5 h-5 animate-spin mx-auto text-accent" />
              <p>Searching repository code chunks for relevant context...</p>
            </div>
          ) : isError ? (
            <div className="p-4 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error?.message || 'Failed to retrieve task context'}</span>
              </div>
              <button onClick={() => refetch()} className="font-semibold underline">
                Retry
              </button>
            </div>
          ) : !ragData?.is_indexed ? (
            <div className="p-8 rounded-lg bg-background-subtle border border-border-subtle text-center text-xs text-content-muted space-y-2">
              <GitBranch className="w-8 h-8 text-content-muted mx-auto mb-1 opacity-50" />
              <p className="font-semibold text-content-primary">Repository not indexed</p>
              <p className="max-w-md mx-auto text-[11px]">
                {ragData?.message ||
                  'The connected repository has not been indexed yet. Open Repositories settings and click "Index Repository" to enable Code RAG.'}
              </p>
            </div>
          ) : ragData.results.length === 0 ? (
            <div className="p-8 rounded-lg bg-background-subtle border border-border-subtle text-center text-xs text-content-muted">
              No matching code sections found for this task description.
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs text-content-muted">
                <span>Repository: <strong className="text-content-primary font-mono">{ragData.repository_name}</strong></span>
                <span className="font-mono text-[11px]">Commit: {ragData.commit_sha ? ragData.commit_sha.slice(0, 8) : '—'}</span>
              </div>

              {ragData.results.map((chunk) => (
                <div
                  key={chunk.chunk_id}
                  className="rounded-lg bg-background-subtle border border-border-subtle p-3.5 space-y-2"
                >
                  <div className="flex items-center justify-between text-xs gap-2">
                    <div className="flex items-center gap-2 truncate">
                      <FileCode className="w-3.5 h-3.5 text-accent shrink-0" />
                      <span className="font-mono font-semibold text-content-primary truncate">
                        {chunk.file_path}
                      </span>
                      <span className="font-mono text-[11px] text-content-muted">
                        #L{chunk.start_line}–L{chunk.end_line}
                      </span>
                      {chunk.symbol_name && (
                        <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-accent/10 text-accent border border-accent/20">
                          {chunk.symbol_name}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-[11px] font-mono text-emerald-400 font-medium">
                        {Math.round(chunk.score * 100)}% relevance
                      </span>
                      <a
                        href={chunk.github_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] text-content-muted hover:text-accent transition-colors"
                      >
                        GitHub <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  </div>

                  <pre className="p-3 rounded bg-black/60 border border-border-subtle/80 font-mono text-[11px] text-zinc-300 overflow-x-auto leading-relaxed max-h-48">
                    <code>{chunk.chunk_content}</code>
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border-subtle bg-background-subtle/50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
