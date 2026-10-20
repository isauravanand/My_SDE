import React from 'react';
import { Server, Database, RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useHealth } from '../../hooks/useHealth';
import { api } from '../../lib/api';

export function HealthStatusBanner() {
  const { health, readiness, isConnected, isDbReady, isLoading, error, refetch } = useHealth();
  const baseUrl = api.getBaseUrl();

  return (
    <div className="p-4 rounded-lg bg-background-card border border-border-subtle mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* Left: Overall Status Details */}
        <div className="flex items-start gap-3">
          <div className="mt-0.5">
            {isConnected && isDbReady ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            ) : (
              <AlertCircle className="w-5 h-5 text-amber-400" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-medium text-content-primary">
                Environment Foundation Status
              </h3>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-background-subtle border border-border-subtle text-content-secondary">
                {baseUrl}
              </span>
            </div>
            <p className="text-xs text-content-secondary mt-0.5">
              {isConnected
                ? `FastAPI process operational (v${health?.version || '0.1.0'} on ${health?.environment || 'development'})`
                : 'Backend API is unreachable. Start the server using `uv run uvicorn app.main:app`.'}
            </p>
          </div>
        </div>

        {/* Right: Live Diagnostics Chips & Refresh */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs">
            {/* API Status Chip */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-mono text-[11px] ${
                isConnected
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
              }`}
            >
              <Server className="w-3 h-3" />
              API: {isConnected ? 'OK' : 'DOWN'}
            </span>

            {/* DB Status Chip */}
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-mono text-[11px] ${
                isDbReady
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
              }`}
            >
              <Database className="w-3 h-3" />
              DB:{' '}
              {isDbReady
                ? `READY (${readiness?.database?.latency_ms || 0}ms)`
                : 'DISCONNECTED'}
            </span>
          </div>

          <button
            onClick={() => refetch()}
            disabled={isLoading}
            className="p-1.5 rounded-md bg-background-subtle border border-border-subtle text-content-secondary hover:text-content-primary hover:bg-background-hover disabled:opacity-50 transition-colors"
            title="Refresh system diagnostics"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Warning message if DB is disconnected */}
      {isConnected && !isDbReady && (
        <div className="mt-3 pt-3 border-t border-border-subtle text-xs text-amber-300/90 flex items-center gap-2">
          <span>Note: PostgreSQL service probe returned disconnected. Ensure PostgreSQL is active on port 5432 and run migrations via <code>uv run alembic upgrade head</code>.</span>
        </div>
      )}
    </div>
  );
}
