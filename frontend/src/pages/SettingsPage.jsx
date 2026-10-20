import React from 'react';
import { Settings, Server, Shield, Layers, ExternalLink } from 'lucide-react';
import { api } from '../lib/api';
import { useHealth } from '../hooks/useHealth';

export function SettingsPage() {
  const { health, readiness, isConnected, isDbReady } = useHealth();
  const apiBaseUrl = api.getBaseUrl();

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-xl font-bold tracking-tight text-content-primary">Settings</h1>
        <p className="text-sm text-content-secondary mt-1">
          System configuration, API endpoints, and environment status.
        </p>
      </div>

      {/* Backend Connection Card */}
      <div className="rounded-lg bg-background-card border border-border-subtle p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-background-subtle border border-border-subtle text-accent">
            <Server className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-content-primary">Backend Connection</h2>
            <p className="text-xs text-content-secondary">
              Active API gateway and diagnostics probe.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
          <div className="p-3 rounded bg-background-subtle border border-border-subtle">
            <span className="text-xs text-content-muted block mb-1">API Base URL</span>
            <span className="font-mono text-xs text-content-primary">{apiBaseUrl}</span>
          </div>
          <div className="p-3 rounded bg-background-subtle border border-border-subtle">
            <span className="text-xs text-content-muted block mb-1">Process Liveness</span>
            <span className="font-mono text-xs text-emerald-400">
              {isConnected ? 'OK (200 /health)' : 'OFFLINE'}
            </span>
          </div>
          <div className="p-3 rounded bg-background-subtle border border-border-subtle">
            <span className="text-xs text-content-muted block mb-1">PostgreSQL Connectivity</span>
            <span
              className={`font-mono text-xs ${
                isDbReady ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {isDbReady
                ? `READY (${readiness?.database?.latency_ms || 0}ms)`
                : 'DISCONNECTED'}
            </span>
          </div>
          <div className="p-3 rounded bg-background-subtle border border-border-subtle">
            <span className="text-xs text-content-muted block mb-1">Environment</span>
            <span className="font-mono text-xs text-content-primary uppercase">
              {health?.environment || 'development'}
            </span>
          </div>
        </div>
      </div>

      {/* Security Architecture Card */}
      <div className="rounded-lg bg-background-card border border-border-subtle p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-background-subtle border border-border-subtle text-accent">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-content-primary">Security & Isolation</h2>
            <p className="text-xs text-content-secondary">
              Execution boundaries and credential safeguards.
            </p>
          </div>
        </div>

        <ul className="text-xs text-content-secondary space-y-2 list-disc list-inside pt-1">
          <li>Zero in-process execution: Untrusted repository scripts execute only inside ephemeral containers.</li>
          <li>Log Sanitization: All logs and traces pass through automated credential redaction filters.</li>
          <li>Least Privilege: GitHub App requires scoped contents and PR permissions without organization administration rights.</li>
        </ul>
      </div>

      {/* Documentation Card */}
      <div className="rounded-lg bg-background-card border border-border-subtle p-6 space-y-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-md bg-background-subtle border border-border-subtle text-accent">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-content-primary">Architecture Documentation</h2>
            <p className="text-xs text-content-secondary">
              Review specifications and database designs in the local repository.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 text-xs font-mono">
          <span className="p-2 rounded bg-background-subtle border border-border-subtle text-content-primary text-center">docs/PRD.md</span>
          <span className="p-2 rounded bg-background-subtle border border-border-subtle text-content-primary text-center">docs/ARCHITECTURE.md</span>
          <span className="p-2 rounded bg-background-subtle border border-border-subtle text-content-primary text-center">docs/DATABASE_DESIGN.md</span>
          <span className="p-2 rounded bg-background-subtle border border-border-subtle text-content-primary text-center">docs/SECURITY.md</span>
        </div>
      </div>
    </div>
  );
}
