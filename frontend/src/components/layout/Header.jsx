import React, { useState } from 'react';
import { Menu, ChevronDown, Layers, User, LogOut, Check } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';

const ROUTE_TITLES = {
  '/': 'Dashboard',
  '/projects': 'Projects',
  '/tasks': 'Tasks',
  '/repositories': 'Repositories',
  '/runs': 'Agent Runs',
  '/settings': 'Settings',
};

export function Header({ onMenuClick }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, workspaces, activeWorkspace, setActiveWorkspaceId, logout } = useAuth();

  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const currentTitle = ROUTE_TITLES[location.pathname] || 'Overview';

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch (err) {
      console.error('Logout error:', err);
    }
  };

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between h-16 px-4 sm:px-6 bg-background/80 backdrop-blur-md border-b border-border-subtle">
      {/* Left: Mobile Toggle & Page Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="p-2 -ml-2 rounded-md text-content-secondary hover:text-content-primary hover:bg-background-card lg:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="w-5 h-5" />
        </button>
        <h1 className="text-lg font-semibold text-content-primary tracking-tight">
          {currentTitle}
        </h1>
      </div>

      {/* Right: Workspace Selector & User Dropdown */}
      <div className="flex items-center gap-3">
        {/* Workspace Selector Dropdown */}
        <div className="relative">
          <button
            onClick={() => setWorkspaceMenuOpen(!workspaceMenuOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-background-card border border-border-subtle text-xs font-medium text-content-secondary hover:text-content-primary transition-colors"
          >
            <Layers className="w-3.5 h-3.5 text-accent" />
            <span className="hidden sm:inline">Workspace:</span>
            <span className="text-content-primary font-medium truncate max-w-[120px]">
              {activeWorkspace?.name || 'Personal'}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-content-muted" />
          </button>

          {workspaceMenuOpen && (
            <>
              <div
                className="fixed inset-0 z-30"
                onClick={() => setWorkspaceMenuOpen(false)}
              />
              <div className="absolute right-0 mt-1.5 w-56 p-1.5 rounded-lg bg-background-card border border-border-strong shadow-card z-40 text-xs">
                <div className="px-2 py-1 text-[11px] font-medium text-content-muted uppercase tracking-wider">
                  Select Workspace
                </div>
                {workspaces.map((ws) => (
                  <button
                    key={ws.id}
                    onClick={() => {
                      setActiveWorkspaceId(ws.id);
                      setWorkspaceMenuOpen(false);
                    }}
                    className="w-full flex items-center justify-between px-2.5 py-2 rounded text-left hover:bg-background-hover text-content-primary transition-colors"
                  >
                    <span className="truncate">{ws.name}</span>
                    {activeWorkspace?.id === ws.id && (
                      <Check className="w-3.5 h-3.5 text-accent shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* User Profile & Logout */}
        <div className="relative pl-2 border-l border-border-subtle">
          <button
            onClick={() => setUserMenuOpen(!userMenuOpen)}
            className="flex items-center gap-2.5 p-1 rounded-md hover:bg-background-card transition-colors"
          >
            <div className="flex items-center justify-center w-8 h-8 rounded-full bg-background-subtle border border-border-subtle text-accent font-medium text-xs">
              {user?.full_name ? user.full_name.charAt(0).toUpperCase() : <User className="w-4 h-4" />}
            </div>
            <div className="hidden md:block text-left text-xs">
              <p className="font-medium text-content-primary leading-none">
                {user?.full_name || 'Developer'}
              </p>
              <p className="text-[11px] text-content-muted mt-0.5 truncate max-w-[140px]">
                {user?.email || 'dev@mysde.local'}
              </p>
            </div>
            <ChevronDown className="w-3.5 h-3.5 text-content-muted hidden sm:block" />
          </button>

          {userMenuOpen && (
            <>
              <div
                className="fixed inset-0 z-30"
                onClick={() => setUserMenuOpen(false)}
              />
              <div className="absolute right-0 mt-1.5 w-48 p-1.5 rounded-lg bg-background-card border border-border-strong shadow-card z-40 text-xs">
                <div className="px-2.5 py-2 border-b border-border-subtle mb-1">
                  <p className="font-medium text-content-primary truncate">{user?.full_name || 'Developer'}</p>
                  <p className="text-[11px] text-content-muted truncate">{user?.email}</p>
                </div>
                <button
                  onClick={() => {
                    setUserMenuOpen(false);
                    handleLogout();
                  }}
                  className="w-full flex items-center gap-2 px-2.5 py-2 rounded text-rose-400 hover:bg-rose-500/10 transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                  Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
