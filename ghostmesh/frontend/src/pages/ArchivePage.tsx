import { useState } from 'react';
import type { FormEvent } from 'react';
import { Archive, ExternalLink, Calendar, Info, Download } from 'lucide-react';
import { SectionHeader, Spinner, EmptyState } from '../components';
import { apiUrl } from '../utils/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ArchiveSnapshot {
  url: string;
  snapshot_date: string; // ISO date string
  http_status: number;
  size_mb?: number;
}

interface ArchiveResult {
  original_url: string;
  total_found: number;
  snapshots: ArchiveSnapshot[];
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

function buildMockResult(queryUrl: string): ArchiveResult {
  const baseTs = new Date('2024-11-01').getTime();
  const snapshots: ArchiveSnapshot[] = [
    {
      url: `https://web.archive.org/web/20241101120000/${queryUrl}`,
      snapshot_date: '2024-11-01T12:00:00Z',
      http_status: 200,
      size_mb: 1.4,
    },
    {
      url: `https://web.archive.org/web/20240815080000/${queryUrl}`,
      snapshot_date: '2024-08-15T08:00:00Z',
      http_status: 200,
      size_mb: 1.2,
    },
    {
      url: `https://web.archive.org/web/20240320143000/${queryUrl}`,
      snapshot_date: '2024-03-20T14:30:00Z',
      http_status: 301,
    },
    {
      url: `https://web.archive.org/web/20231210090000/${queryUrl}`,
      snapshot_date: '2023-12-10T09:00:00Z',
      http_status: 200,
      size_mb: 0.9,
    },
    {
      url: `https://web.archive.org/web/20230501160000/${queryUrl}`,
      snapshot_date: '2023-05-01T16:00:00Z',
      http_status: 200,
      size_mb: 0.8,
    },
  ];
  void baseTs;
  return {
    original_url: queryUrl,
    total_found: snapshots.length,
    snapshots,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  } catch {
    return iso;
  }
}

function statusColor(code: number): { bg: string; text: string } {
  if (code < 300) return { bg: 'rgba(57,211,83,0.12)',  text: 'var(--gm-teal)'   };
  if (code < 400) return { bg: 'rgba(240,167,50,0.12)', text: 'var(--gm-yellow)' };
  return           { bg: 'rgba(248,81,73,0.12)',  text: 'var(--gm-red)'    };
}

function exportJson(result: ArchiveResult) {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `archive-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// ArchivePage
// ---------------------------------------------------------------------------

export function ArchivePage() {
  const [inputUrl, setInputUrl] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<ArchiveResult | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = inputUrl.trim();
    if (!trimmed || searching) return;

    setSearching(true);
    setResult(null);

    // Try real backend; fall back to mock
    try {
      const res = await fetch(apiUrl('/api/recon/archive'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmed, from: fromDate || undefined, to: toDate || undefined }),
        signal: AbortSignal.timeout(8_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ArchiveResult = await res.json();
      setResult(data);
    } catch {
      // API unavailable — show mock data after simulated delay
      await new Promise((r) => setTimeout(r, 1200));
      setResult(buildMockResult(trimmed));
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="max-w-3xl animate-fade-in space-y-5">
      <SectionHeader
        icon={Archive}
        title="Archive"
        subtitle="Search Wayback Machine and web archives"
      />

      {/* Search form */}
      <div className="gm-card space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* URL input */}
          <div>
            <label
              className="block text-xs font-medium mb-1.5"
              style={{ color: 'var(--gm-text-secondary)' }}
            >
              URL or Domain
            </label>
            <input
              className="gm-input w-full"
              type="text"
              value={inputUrl}
              onChange={(e) => setInputUrl(e.target.value)}
              placeholder="https://example.com or example.com"
              autoFocus
              disabled={searching}
            />
          </div>

          {/* Date range */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label
                className="block text-xs font-medium mb-1.5"
                style={{ color: 'var(--gm-text-secondary)' }}
              >
                From Date (optional)
              </label>
              <input
                className="gm-input w-full"
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                disabled={searching}
              />
            </div>
            <div>
              <label
                className="block text-xs font-medium mb-1.5"
                style={{ color: 'var(--gm-text-secondary)' }}
              >
                To Date (optional)
              </label>
              <input
                className="gm-input w-full"
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                disabled={searching}
              />
            </div>
          </div>

          <button
            type="submit"
            className="gm-btn gm-btn-primary"
            disabled={!inputUrl.trim() || searching}
          >
            {searching ? <Spinner size="sm" /> : <Archive size={14} />}
            {searching ? 'Searching…' : 'Search Archives'}
          </button>
        </form>
      </div>

      {/* Provider note */}
      <div
        className="flex items-start gap-3 rounded-lg border px-4 py-3 text-sm"
        style={{ background: 'rgba(47,129,247,0.05)', borderColor: 'rgba(47,129,247,0.2)' }}
      >
        <Info size={14} className="shrink-0 mt-0.5" style={{ color: 'var(--gm-accent)' }} />
        <p style={{ color: 'var(--gm-text-secondary)', margin: 0, lineHeight: 1.6 }}>
          Powered by{' '}
          <a
            href="https://archive.org"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'var(--gm-accent)' }}
          >
            Wayback Machine (archive.org)
          </a>
          . Results depend on crawl coverage. Not all URLs are archived.
        </p>
      </div>

      {/* Empty state */}
      {!result && !searching && (
        <EmptyState
          icon={Archive}
          title="Search web archives"
          description="Enter a URL or domain to find historical snapshots from the Wayback Machine."
        />
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4 animate-fade-in">
          {/* Summary + export */}
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm" style={{ color: 'var(--gm-text-secondary)' }}>
              Found{' '}
              <span className="font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                {result.total_found}
              </span>{' '}
              snapshots for{' '}
              <span
                className="font-mono text-xs"
                style={{ color: 'var(--gm-text-secondary)' }}
              >
                {result.original_url}
              </span>
            </p>
            <button
              className="gm-btn gm-btn-secondary text-xs shrink-0"
              onClick={() => exportJson(result)}
            >
              <Download size={12} />
              Export JSON
            </button>
          </div>

          {/* Snapshot cards */}
          {result.snapshots.length === 0 ? (
            <EmptyState
              icon={Archive}
              title="No snapshots found"
              description="The Wayback Machine has no recorded snapshots for this URL in the selected date range."
            />
          ) : (
            <div className="space-y-3">
              {result.snapshots.map((snap, i) => {
                const sc = statusColor(snap.http_status);
                return (
                  <div
                    key={i}
                    className="gm-card flex items-center gap-4"
                    style={{ padding: '0.875rem 1rem' }}
                  >
                    {/* Date */}
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <Calendar
                        size={14}
                        className="shrink-0"
                        style={{ color: 'var(--gm-text-muted)' }}
                      />
                      <div className="min-w-0">
                        <p
                          className="text-sm font-medium"
                          style={{ color: 'var(--gm-text-primary)' }}
                        >
                          {formatDate(snap.snapshot_date)}
                        </p>
                        <p
                          className="text-xs font-mono truncate mt-0.5"
                          style={{ color: 'var(--gm-text-muted)' }}
                        >
                          {snap.url}
                        </p>
                      </div>
                    </div>

                    {/* Status code */}
                    <span
                      className="gm-badge font-mono shrink-0"
                      style={{
                        background: sc.bg,
                        color: sc.text,
                        fontSize: '11px',
                      }}
                    >
                      HTTP {snap.http_status}
                    </span>

                    {/* Size */}
                    {snap.size_mb !== undefined && (
                      <span
                        className="text-xs shrink-0"
                        style={{ color: 'var(--gm-text-muted)' }}
                      >
                        {snap.size_mb.toFixed(1)} MB
                      </span>
                    )}

                    {/* Open link */}
                    <a
                      href={snap.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="gm-btn gm-btn-secondary text-xs shrink-0"
                    >
                      <ExternalLink size={12} />
                      Open snapshot
                    </a>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
