import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

/**
 * Custom hook to monitor backend process health and database readiness.
 */
export function useHealth() {
  const healthQuery = useQuery({
    queryKey: ['system', 'health'],
    queryFn: () => api.getHealth(),
    refetchInterval: 15000, // Refresh every 15s
    retry: 1,
  });

  const readinessQuery = useQuery({
    queryKey: ['system', 'readiness'],
    queryFn: () => api.getReadiness(),
    refetchInterval: 15000,
    retry: 1,
  });

  const isConnected = !healthQuery.isError && healthQuery.data?.status === 'ok';
  const isDbReady = !readinessQuery.isError && readinessQuery.data?.status === 'ready';

  return {
    health: healthQuery.data,
    readiness: readinessQuery.data,
    isLoading: healthQuery.isLoading || readinessQuery.isLoading,
    isError: healthQuery.isError || readinessQuery.isError,
    error: healthQuery.error || readinessQuery.error,
    isConnected,
    isDbReady,
    refetch: () => {
      healthQuery.refetch();
      readinessQuery.refetch();
    },
  };
}
