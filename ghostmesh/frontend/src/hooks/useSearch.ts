import { useMutation } from '@tanstack/react-query';
import type { SearchQuery, SearchResponse, SearchResult } from '../types';

function generateMockResults(query: string): SearchResult[] {
  return [
    {
      id: '1',
      title: `Search results for "${query}" — service offline`,
      snippet:
        'The GhostMesh search API is currently unavailable. Configure at least one search engine to begin returning real results.',
      url: '#',
      source_engine: 'system',
      confidence: 0,
      tags: ['system'],
      category: 'status',
      archived: false,
    },
  ];
}

async function runSearch(params: SearchQuery): Promise<SearchResponse> {
  const res = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function useSearch() {
  return useMutation<SearchResponse, Error, SearchQuery>({
    mutationFn: async (params) => {
      try {
        return await runSearch(params);
      } catch {
        return {
          query: params.query,
          results: generateMockResults(params.query),
          engines_used: [],
          engines_failed: params.engines,
          total: 0,
          duration_ms: 0,
        };
      }
    },
  });
}
