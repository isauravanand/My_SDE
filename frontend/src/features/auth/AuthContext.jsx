import React, { createContext, useContext, useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../../lib/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(null);

  // 1. Query Current User Profile
  const {
    data: user,
    isLoading: isUserLoading,
    isError: isUserError,
    refetch: refetchUser,
  } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        return await api.getMe();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          return null; // Not authenticated
        }
        throw err;
      }
    },
    retry: false,
    staleTime: 30000,
  });

  const isAuthenticated = !!user;

  // 2. Query Workspaces if Authenticated
  const {
    data: workspaces = [],
    isLoading: isWorkspacesLoading,
    refetch: refetchWorkspaces,
  } = useQuery({
    queryKey: ['workspaces', 'list'],
    queryFn: () => api.getWorkspaces(),
    enabled: isAuthenticated,
    staleTime: 30000,
  });

  // Set default active workspace
  useEffect(() => {
    if (workspaces.length > 0) {
      if (!activeWorkspaceId || !workspaces.some((ws) => ws.id === activeWorkspaceId)) {
        setActiveWorkspaceId(workspaces[0].id);
      }
    } else {
      setActiveWorkspaceId(null);
    }
  }, [workspaces, activeWorkspaceId]);

  const activeWorkspace = workspaces.find((ws) => ws.id === activeWorkspaceId) || workspaces[0] || null;

  // 3. Login Mutation
  const loginMutation = useMutation({
    mutationFn: (credentials) => api.login(credentials),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      await queryClient.invalidateQueries({ queryKey: ['workspaces', 'list'] });
    },
  });

  // 4. Register Mutation
  const registerMutation = useMutation({
    mutationFn: (data) => api.register(data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      await queryClient.invalidateQueries({ queryKey: ['workspaces', 'list'] });
    },
  });

  // 5. Logout Mutation
  const logoutMutation = useMutation({
    mutationFn: () => api.logout(),
    onSuccess: () => {
      queryClient.setQueryData(['auth', 'me'], null);
      queryClient.setQueryData(['workspaces', 'list'], []);
      setActiveWorkspaceId(null);
      queryClient.clear();
    },
  });

  const value = {
    user,
    isAuthenticated,
    isLoading: isUserLoading || (isAuthenticated && isWorkspacesLoading),
    workspaces,
    activeWorkspace,
    setActiveWorkspaceId,
    login: loginMutation.mutateAsync,
    register: registerMutation.mutateAsync,
    logout: logoutMutation.mutateAsync,
    refetchUser,
    refetchWorkspaces,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
