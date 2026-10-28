import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderGit2,
  CheckSquare,
  GitBranch,
  Bot,
  CreditCard,
  Settings,
  Terminal,
  X,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { StatusBadge } from '../common/StatusBadge';
import { useHealth } from '../../hooks/useHealth';

const NAV_ITEMS = [
  { name: 'Dashboard', path: '/', icon: LayoutDashboard },
  { name: 'Projects', path: '/projects', icon: FolderGit2 },
  { name: 'Tasks', path: '/tasks', icon: CheckSquare },
  { name: 'Repositories', path: '/repositories', icon: GitBranch },
  { name: 'Agent Runs', path: '/runs', icon: Bot },
  { name: 'Billing', path: '/billing', icon: CreditCard },
  { name: 'Settings', path: '/settings', icon: Settings },
];

export function Sidebar({ isOpen, onClose }) {
  const { isConnected, isDbReady } = useHealth();

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex flex-col w-64 bg-background-subtle border-r border-border-subtle transition-transform duration-200 ease-in-out lg:static lg:translate-x-0',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Brand Header */}
        <div className="flex items-center justify-between h-16 px-5 border-b border-border-subtle">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center justify-center w-8 h-8 rounded-md bg-background-card border border-border-subtle text-accent shadow-subtle">
              <Terminal className="w-4 h-4" />
            </div>
            <div>
              <span className="text-base font-semibold tracking-tight text-content-primary">
                My<span className="text-accent">SDE</span>
              </span>
              <span className="ml-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-background-card border border-border-subtle text-content-muted">
                v0.1
              </span>
            </div>
          </div>
          {/* Close button on mobile */}
          <button
            onClick={onClose}
            className="p-1 rounded-md text-content-secondary hover:text-content-primary hover:bg-background-card lg:hidden"
            aria-label="Close navigation"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors group relative',
                    isActive
                      ? 'bg-accent/10 text-accent border border-accent/20'
                      : 'text-content-secondary hover:text-content-primary hover:bg-background-card'
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon
                      className={cn(
                        'w-4 h-4 transition-colors',
                        isActive ? 'text-accent' : 'text-content-muted group-hover:text-content-secondary'
                      )}
                    />
                    <span>{item.name}</span>
                    {isActive && (
                      <span className="absolute right-2 w-1.5 h-1.5 rounded-full bg-accent" />
                    )}
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* System Status Footer */}
        <div className="p-4 border-t border-border-subtle bg-background-card/40">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="text-content-muted font-medium">System Status</span>
            <StatusBadge
              status={isConnected ? 'connected' : 'disconnected'}
              label={isConnected ? 'API Online' : 'API Offline'}
            />
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-content-muted">Database</span>
            <span
              className={cn(
                'font-mono text-[11px]',
                isDbReady ? 'text-emerald-400' : 'text-rose-400'
              )}
            >
              {isDbReady ? 'Ready' : 'Not Connected'}
            </span>
          </div>
        </div>
      </aside>
    </>
  );
}
