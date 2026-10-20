import React from 'react';
import { Bot } from 'lucide-react';
import { EmptyState } from '../components/common/EmptyState';

export function RunsPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-content-primary">Agent Runs</h1>
          <p className="text-sm text-content-secondary mt-1">
            Execution history, multi-step logs, test evidence dossiers, and delivery reviews.
          </p>
        </div>
      </div>

      <div className="rounded-lg bg-background-card border border-border-subtle p-6">
        <EmptyState
          icon={Bot}
          title="No agent runs dispatched"
          description="Every time an agent investigates a problem, generates diffs, and executes tests in a sandbox, a verifiable run dossier is recorded."
          action={
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-background-subtle border border-border-subtle text-xs text-content-muted">
              Agent execution pipeline arriving in Phase 3
            </span>
          }
        />
      </div>
    </div>
  );
}
