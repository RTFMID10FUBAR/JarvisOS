import { useQuery } from '@tanstack/react-query';
import type { HealthData } from '../types';
import { apiUrl } from '../utils/api';

const MOCK_HEALTH: HealthData = {
  ui_status: 'online',
  api_status: 'offline',
  engine_registry_status: 'degraded',
  configured_engines: [],
  unavailable_engines: [
    { name: 'SearXNG', reason: 'Service not running', missing_key: undefined },
    { name: 'Shodan', reason: 'API key not configured', missing_key: 'SHODAN_API_KEY' },
    { name: 'VirusTotal', reason: 'API key not configured', missing_key: 'VT_API_KEY' },
  ],
  missing_env_vars: ['SHODAN_API_KEY', 'VT_API_KEY', 'HUNTER_API_KEY'],
  last_query_time: null,
  service_versions: { ghostmesh: '0.1.0', api: 'unavailable' },
  uptime_seconds: 0,
  timestamp: new Date().toISOString(),
};

async function fetchHealth(): Promise<HealthData> {
  const res = await fetch(apiUrl('/api/health'), { signal: AbortSignal.timeout(5000) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useHealth() {
  return useQuery<HealthData>({
    queryKey: ['health'],
    queryFn: async () => {
      try {
        return await fetchHealth();
      } catch {
        return { ...MOCK_HEALTH, timestamp: new Date().toISOString() };
      }
    },
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}
