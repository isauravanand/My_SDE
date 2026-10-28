import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  X,
  Database,
  Search,
  RefreshCw,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  FileCode,
  Layers,
  Sparkles,
  ShieldAlert,
} from 'lucide-react';
import { api } from '../../lib/api';

const STATUS_BADGES = {
  completed: 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60',
  partially_completed: 'bg-amber-950/60 text-amber-300 border-amber-800/60',
  running: 'bg-sky-950/60 text-sky-300 border-sky-800/60 animate-pulse',
  queued: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  failed: 'bg-rose-950/60 text-rose-300 border-rose-800/60',
};

export function CodeRagModal({ repo, workspaceId, onClose }) {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [targetBranch, setTargetBranch] = useState(repo.default_branch || 'main');
  const [forceReindex, setForceReindex] = useState(false);
  const [actionError, setActionError] = useState('');

  // 1. Fetch latest indexing status
  const {
    data: indexStatus,
    isLoading: isStatusLoading,
    refetch: refetchStatus,
  } = useQuery({
    queryKey: ['rag-index-status', repo.id, workspaceId],
    queryFn: () => api.getRepoIndexingStatus(repo.id, workspaceId),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.status === 'queued' || data?.status === 'running' ? 3000 : false;
    },
  });

  // 2. Trigger Indexing Mutation
  const indexMutation = useMutation({
    mutationFn: () =>
      api.triggerRepoIndexing(repo.id, workspaceId, {
        target_ref: targetBranch.trim() || undefined,
        force_reindex: forceReindex,
      }),
    onSuccess: async () => {
      setActionError('');
      await queryClient.invalidateQueries({ queryKey: ['rag-index-status', repo.id, workspaceId] });
      await refetchStatus();
    },
    onError: (err) => {
      setActionError(err.message || 'Failed to trigger indexing');
    },
  });

  // 3. Retrieval Query
  const {
    data: retrievalResults,
    isLoading: isSearching,
    isError: isSearchError,
    error: searchError,
    refetch: triggerSearch,
  } = useQuery({
    queryKey: ['rag-retrieve', repo.id, workspaceId, searchQuery],
    queryFn: () =>
      api.retrieveCodeChunks(repo.id, workspaceId, {
        query: searchQuery.trim(),
        top_k: 5,
      }),
    enabled: !!searchQuery.trim() && !!indexStatus && indexStatus.status === 'completed',
  });

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      triggerSearch();
    }
  };

  const isIndexed = indexStatus && (indexStatus.status === 'completed' || indexStatus.status === 'partially_completed');

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-3xl max-h-[90vh] flex flex-col rounded-lg bg-background-card border border-border-strong shadow-card text-left overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border-subtle bg-background-subtle/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded bg-accent/10 border border-accent/20 text-accent">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-content-primary">{repo.full_name}</h3>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-background-subtle border border-border-subtle text-content-muted">
                  Code RAG
                </span>
              </div>
              <p className="text-xs text-content-muted mt-0.5">
                Index repository source code and inspect retrieved chunks with similarity citations.
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

        {/* Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {actionError && (
            <div className="p-3 rounded bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{actionError}</span>
            </div>
          )}

          {/* Indexing Status Banner */}
          <div className="p-4 rounded-lg bg-background-subtle border border-border-subtle space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-content-secondary">Indexing Status:</span>
                {isStatusLoading ? (
                  <span className="text-xs text-content-muted font-mono animate-pulse">Checking...</span>
                ) : indexStatus ? (
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded border uppercase font-semibold ${
                      STATUS_BADGES[indexStatus.status] || 'bg-zinc-800 text-zinc-300 border-zinc-700'
                    }`}
                  >
                    {indexStatus.status.replace('_', ' ')}
                  </span>
                ) : (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700 uppercase">
                    Not Indexed
                  </span>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={targetBranch}
                    onChange={(e) => setTargetBranch(e.target.value)}
                    placeholder="Branch / Ref"
                    className="w-24 px-2 py-1 text-xs font-mono rounded bg-background-card border border-border-subtle text-content-primary outline-none focus:border-accent"
                  />
                  <label className="flex items-center gap-1 text-[11px] text-content-muted cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={forceReindex}
                      onChange={(e) => setForceReindex(e.target.checked)}
                      className="w-3.5 h-3.5 rounded border-border-subtle text-accent bg-background-card"
                    />
                    Force
                  </label>
                </div>

                <button
                  onClick={() => indexMutation.mutate()}
                  disabled={indexMutation.isPending || indexStatus?.status === 'running'}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent text-background text-xs font-semibold hover:bg-accent-hover transition-colors disabled:opacity-50"
                >
                  <RefreshCw
                    className={`w-3.5 h-3.5 ${
                      indexMutation.isPending || indexStatus?.status === 'running' ? 'animate-spin' : ''
                    }`}
                  />
                  {indexStatus?.status === 'running'
                    ? 'Indexing...'
                    : isIndexed
                    ? 'Re-index'
                    : 'Index Repository'}
                </button>
              </div>
            </div>

            {/* Stats Overview */}
            {indexStatus && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-3 border-t border-border-subtle/60 text-xs">
                <div>
                  <span className="text-[10px] text-content-muted block uppercase font-mono">Commit SHA</span>
                  <span className="font-mono text-content-primary text-[11px] truncate block" title={indexStatus.commit_sha}>
                    {indexStatus.commit_sha ? indexStatus.commit_sha.slice(0, 8) : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-content-muted block uppercase font-mono">Files Indexed</span>
                  <span className="font-mono text-content-primary text-[11px]">
                    {indexStatus.files_accepted} / {indexStatus.files_discovered}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-content-muted block uppercase font-mono">Code Chunks</span>
                  <span className="font-mono text-content-primary text-[11px]">
                    {indexStatus.chunks_count} chunks
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-content-muted block uppercase font-mono">Model</span>
                  <span className="font-mono text-content-primary text-[11px] truncate block" title={indexStatus.embedding_model}>
                    {indexStatus.embedding_model} ({indexStatus.embedding_dimensions}d)
                  </span>
                </div>
              </div>
            )}

            {/* Exclusions Breakdown */}
            {indexStatus?.exclusions_summary && (
              <div className="pt-2 text-[11px] text-content-muted flex items-center gap-4 flex-wrap">
                <span className="font-medium text-content-secondary flex items-center gap-1">
                  <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
                  Excluded:
                </span>
                <span>Secrets: {indexStatus.exclusions_summary.secret_file || 0}</span>
                <span>Binaries: {indexStatus.exclusions_summary.binary_or_compiled || 0}</span>
                <span>Lockfiles: {indexStatus.exclusions_summary.lockfile_or_minified || 0}</span>
                <span>Directories: {indexStatus.exclusions_summary.directory_excluded || 0}</span>
                <span>Oversized: {indexStatus.exclusions_summary.file_too_large || 0}</span>
              </div>
            )}
          </div>

          {/* Code Retrieval Sandbox */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-content-muted flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-accent" />
                Code Retrieval Preview
              </h4>
              <span className="text-[11px] text-content-muted">Top 5 semantic citations</span>
            </div>

            <form onSubmit={handleSearchSubmit} className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-content-muted" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="e.g. Where is user authentication password checked? or query database"
                  className="w-full pl-9 pr-3 py-2 text-xs rounded-md bg-background-subtle border border-border-subtle focus:border-accent text-content-primary placeholder-content-muted outline-none transition-colors"
                />
              </div>
              <button
                type="submit"
                disabled={!searchQuery.trim() || !isIndexed || isSearching}
                className="px-4 py-2 rounded-md bg-background-subtle border border-border-subtle text-content-primary text-xs font-medium hover:border-accent transition-colors disabled:opacity-40"
              >
                {isSearching ? 'Searching...' : 'Search'}
              </button>
            </form>

            {!isIndexed ? (
              <div className="p-6 rounded-lg bg-background-subtle border border-border-subtle text-center text-xs text-content-muted space-y-1">
                <FileCode className="w-8 h-8 text-content-muted mx-auto mb-2 opacity-50" />
                <p className="font-medium text-content-secondary">Repository is not indexed yet</p>
                <p>Click &ldquo;Index Repository&rdquo; above to parse files, extract symbols, and generate vector embeddings.</p>
              </div>
            ) : isSearching ? (
              <div className="p-6 text-center text-xs text-content-muted space-y-2">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto text-accent" />
                <p>Searching code chunks with cosine similarity...</p>
              </div>
            ) : isSearchError ? (
              <div className="p-4 rounded bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                {searchError?.message || 'Search failed'}
              </div>
            ) : retrievalResults ? (
              retrievalResults.results.length === 0 ? (
                <div className="p-6 rounded-lg bg-background-subtle border border-border-subtle text-center text-xs text-content-muted">
                  No relevant code chunks found for &ldquo;{searchQuery}&rdquo;.
                </div>
              ) : (
                <div className="space-y-3">
                  {retrievalResults.results.map((chunk) => (
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
                            {Math.round(chunk.score * 100)}% match
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

                      {/* Code Snippet Box */}
                      <pre className="p-3 rounded bg-black/60 border border-border-subtle/80 font-mono text-[11px] text-zinc-300 overflow-x-auto leading-relaxed max-h-48">
                        <code>{chunk.chunk_content}</code>
                      </pre>
                    </div>
                  ))}
                </div>
              )
            ) : null}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border-subtle bg-background-subtle/50 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md bg-background-subtle border border-border-subtle text-content-primary text-xs font-semibold hover:bg-background-hover transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
