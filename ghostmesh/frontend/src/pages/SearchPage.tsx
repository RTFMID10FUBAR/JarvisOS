import { useState, useEffect, useRef } from 'react';
import type { FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Search,
  Filter,
  Download,
  ChevronDown,
  ExternalLink,
  AlertTriangle,
  Layers,
  Grid,
  List,
  Clock,
  Tag,
  CheckSquare,
  Square,
  Info,
} from 'lucide-react';
import { useSearch } from '../hooks/useSearch';
import {
  ConfidenceBadge,
  EmptyState,
  ErrorMessage,
  Spinner,
} from '../components';
import { cn } from '../utils/cn';
import { exportJSON, exportCSV, exportMarkdown } from '../utils/export';
import type { SearchResult, ReconMode } from '../types';

// ---------------------------------------------------------------------------
// Constants & types
// ---------------------------------------------------------------------------

const RECENT_SEARCHES_KEY = 'gm-recent-searches';
const MAX_RECENT = 10;

type ViewMode = 'blended' | 'grouped' | 'sidebyside';
type SortKey  = 'relevance' | 'date' | 'confidence' | 'source';

interface EngineOption {
  id:          string;
  name:        string;
  letter:      string;
  status:      'online' | 'offline' | 'key_required';
  statusLabel: string;
}

interface RecentSearchEntry {
  id:          string;
  query:       string;
  timestamp:   string;
  resultCount: number;
  engines:     string[];
}

const ENGINE_OPTIONS: EngineOption[] = [
  { id: 'duckduckgo',     name: 'DuckDuckGo',      letter: 'D', status: 'online',       statusLabel: 'Online'       },
  { id: 'marginalia',     name: 'Marginalia',       letter: 'M', status: 'online',       statusLabel: 'Online'       },
  { id: 'urlscan',        name: 'URLScan.io',       letter: 'U', status: 'online',       statusLabel: 'Online'       },
  { id: 'crtsh',          name: 'Crt.sh',           letter: 'C', status: 'online',       statusLabel: 'Online'       },
  { id: 'searxng',        name: 'SearXNG',          letter: 'X', status: 'offline',      statusLabel: 'Self-hosted'  },
  { id: 'brave',          name: 'Brave Search',     letter: 'B', status: 'key_required', statusLabel: 'Key required' },
  { id: 'otx',            name: 'AlienVault OTX',   letter: 'O', status: 'key_required', statusLabel: 'Key required' },
  { id: 'shodan',         name: 'Shodan',            letter: 'S', status: 'key_required', statusLabel: 'Key required' },
  { id: 'virustotal',     name: 'VirusTotal',        letter: 'V', status: 'key_required', statusLabel: 'Key required' },
  { id: 'haveibeenpwned', name: 'HaveIBeenPwned',   letter: 'H', status: 'key_required', statusLabel: 'Key required' },
];

const MAX_RESULTS_OPTIONS = [10, 25, 50] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function saveRecentSearch(query: string, resultCount: number, engines: string[]) {
  try {
    const existing: RecentSearchEntry[] = JSON.parse(
      localStorage.getItem(RECENT_SEARCHES_KEY) ?? '[]',
    );
    const deduped = existing.filter(
      e => e.query.toLowerCase() !== query.toLowerCase(),
    );
    const entry: RecentSearchEntry = {
      id:          crypto.randomUUID(),
      query,
      timestamp:   new Date().toISOString(),
      resultCount,
      engines,
    };
    const updated = [entry, ...deduped].slice(0, MAX_RECENT);
    localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(updated));
    // Notify OverviewPage in the same tab
    window.dispatchEvent(new StorageEvent('storage', { key: RECENT_SEARCHES_KEY }));
  } catch {
    // Ignore storage errors
  }
}

function sortResults(results: SearchResult[], key: SortKey): SearchResult[] {
  const copy = [...results];
  switch (key) {
    case 'confidence':
      return copy.sort((a, b) => b.confidence - a.confidence);
    case 'date':
      return copy.sort((a, b) => {
        const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0;
        const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0;
        return tb - ta;
      });
    case 'source':
      return copy.sort((a, b) => a.source_engine.localeCompare(b.source_engine));
    default:
      return copy; // relevance = original order
  }
}

function formatTimeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60)    return 'just now';
  if (seconds < 3600)  return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

// ---------------------------------------------------------------------------
// EngineLetter badge
// ---------------------------------------------------------------------------

function EngineLetter({ letter, status }: { letter: string; status: EngineOption['status'] }) {
  const colorMap = {
    online:       { bg: 'rgba(57,211,83,0.15)',  color: 'var(--gm-teal)'   },
    offline:      { bg: 'rgba(248,81,73,0.15)',  color: 'var(--gm-red)'    },
    key_required: { bg: 'rgba(240,167,50,0.15)', color: 'var(--gm-yellow)' },
  };
  const { bg, color } = colorMap[status];
  return (
    <span
      className="w-7 h-7 rounded flex items-center justify-center text-xs font-bold shrink-0"
      style={{ background: bg, color }}
    >
      {letter}
    </span>
  );
}

// ---------------------------------------------------------------------------
// EngineStatusPill
// ---------------------------------------------------------------------------

function EngineStatusPill({ status, label }: { status: EngineOption['status']; label: string }) {
  const styles = {
    online:       { bg: 'rgba(57,211,83,0.12)',  color: 'var(--gm-teal)',   dot: 'var(--gm-teal)'   },
    offline:      { bg: 'rgba(248,81,73,0.12)',  color: 'var(--gm-red)',    dot: 'var(--gm-red)'    },
    key_required: { bg: 'rgba(240,167,50,0.12)', color: 'var(--gm-yellow)', dot: 'var(--gm-yellow)' },
  };
  const s = styles[status];
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded"
      style={{ background: s.bg, color: s.color }}
    >
      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: s.dot }} />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// EngineCheckbox
// ---------------------------------------------------------------------------

function EngineCheckbox({
  engine,
  checked,
  onChange,
}: {
  engine: EngineOption;
  checked: boolean;
  onChange: (id: string, checked: boolean) => void;
}) {
  return (
    <label
      className={cn(
        'flex items-center gap-2.5 p-2.5 rounded-lg border cursor-pointer transition-all select-none',
        checked
          ? 'border-[var(--gm-accent)]/60 bg-[var(--gm-accent)]/5'
          : 'border-[var(--gm-border)] hover:bg-[var(--gm-bg-hover)]',
      )}
    >
      <input
        type="checkbox"
        className="sr-only"
        checked={checked}
        onChange={e => onChange(engine.id, e.target.checked)}
      />
      {checked
        ? <CheckSquare size={14} style={{ color: 'var(--gm-accent)' }} className="shrink-0" />
        : <Square      size={14} style={{ color: 'var(--gm-text-muted)' }} className="shrink-0" />
      }
      <EngineLetter letter={engine.letter} status={engine.status} />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium truncate" style={{ color: 'var(--gm-text-primary)' }}>
          {engine.name}
        </p>
        <EngineStatusPill status={engine.status} label={engine.statusLabel} />
      </div>
    </label>
  );
}

// ---------------------------------------------------------------------------
// ModeToggle
// ---------------------------------------------------------------------------

function ModeToggle({ mode, onChange }: { mode: ReconMode; onChange: (m: ReconMode) => void }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target as Node)) {
        setShowTooltip(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div className="flex items-center gap-2">
      <div
        className="flex rounded-lg overflow-hidden border"
        style={{ background: 'var(--gm-bg-panel)', borderColor: 'var(--gm-border)' }}
      >
        {(['passive', 'active'] as const).map(m => (
          <button
            key={m}
            type="button"
            onClick={() => onChange(m)}
            className={cn(
              'px-4 py-1.5 text-xs font-medium transition-all capitalize',
              mode === m ? 'text-white' : 'text-[var(--gm-text-muted)] hover:text-[var(--gm-text-secondary)]',
            )}
            style={mode === m
              ? { background: m === 'active' ? 'var(--gm-red)' : 'var(--gm-accent)' }
              : { background: 'transparent' }
            }
          >
            {m}
          </button>
        ))}
      </div>

      {/* Active warning tooltip trigger */}
      {mode === 'active' && (
        <div className="relative" ref={tooltipRef}>
          <button
            type="button"
            onClick={() => setShowTooltip(v => !v)}
            className="p-1 rounded-full transition-colors hover:bg-[var(--gm-bg-hover)]"
            style={{ color: 'var(--gm-yellow)' }}
            aria-label="Active mode warning"
          >
            <Info size={14} />
          </button>
          {showTooltip && (
            <div
              className="absolute left-7 top-0 z-50 rounded-lg border p-3 text-xs w-56 shadow-xl"
              style={{
                background:  'var(--gm-bg-card)',
                borderColor: 'rgba(240,167,50,0.4)',
                color:       'var(--gm-text-secondary)',
              }}
            >
              <p className="font-semibold mb-1" style={{ color: 'var(--gm-yellow)' }}>
                Active mode warning
              </p>
              Active mode only on authorized targets. Unauthorized use may be illegal.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ExportMenu
// ---------------------------------------------------------------------------

function ExportMenu({ results, query }: { results: SearchResult[]; query: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const slug = query.toLowerCase().replace(/\s+/g, '-').slice(0, 40);

  const csvRows = results.map(r => ({
    title:         r.title,
    snippet:       r.snippet,
    url:           r.url,
    source_engine: r.source_engine,
    confidence:    r.confidence as unknown as string,
    tags:          r.tags.join('; '),
    timestamp:     r.timestamp ?? '',
    category:      r.category ?? '',
  }));

  const mdContent = [
    `# GhostMesh Search: ${query}`,
    `*Exported ${new Date().toLocaleString()}*`,
    '',
    ...results.map(r => [
      `## ${r.title}`,
      `**Source:** ${r.source_engine}  |  **Confidence:** ${r.confidence}%`,
      '',
      r.snippet,
      r.url !== '#' ? `\n[${r.url}](${r.url})` : '',
      '',
    ].join('\n')),
  ].join('\n');

  const items = [
    { label: 'JSON',     action: () => { exportJSON(results, `ghostmesh-${slug}`); setOpen(false); } },
    { label: 'CSV',      action: () => { exportCSV(csvRows, `ghostmesh-${slug}`); setOpen(false); } },
    { label: 'Markdown', action: () => { exportMarkdown(mdContent, `ghostmesh-${slug}`); setOpen(false); } },
  ];

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="gm-btn gm-btn-secondary text-xs gap-1.5"
      >
        <Download size={13} />
        Export
        <ChevronDown size={12} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-50 rounded-lg border shadow-xl overflow-hidden w-40"
          style={{ background: 'var(--gm-bg-card)', borderColor: 'var(--gm-border)' }}
        >
          {items.map(item => (
            <button
              key={item.label}
              type="button"
              onClick={item.action}
              className="w-full text-left px-3 py-2 text-xs transition-colors hover:bg-[var(--gm-bg-hover)]"
              style={{ color: 'var(--gm-text-primary)' }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResultCard
// ---------------------------------------------------------------------------

function ResultCard({ result }: { result: SearchResult }) {
  const hasUrl = result.url && result.url !== '#';

  return (
    <div className="gm-card transition-all hover:border-[var(--gm-accent)]/30 hover:bg-[var(--gm-bg-hover)]/40 animate-fade-in">
      {/* Title + confidence */}
      <div className="flex items-start justify-between gap-3 mb-1.5">
        {hasUrl ? (
          <a
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-semibold flex items-center gap-1.5 hover:underline min-w-0"
            style={{ color: 'var(--gm-accent)', textDecoration: 'none' }}
          >
            <span className="truncate">{result.title}</span>
            <ExternalLink size={12} className="shrink-0 opacity-70" />
          </a>
        ) : (
          <span className="text-sm font-semibold truncate" style={{ color: 'var(--gm-text-primary)' }}>
            {result.title}
          </span>
        )}
        <ConfidenceBadge score={result.confidence} size="sm" />
      </div>

      {/* Snippet */}
      <p className="text-xs leading-relaxed mb-2.5" style={{ color: 'var(--gm-text-secondary)' }}>
        {result.snippet}
      </p>

      {/* Footer */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Source engine */}
        <span
          className="gm-badge text-[10px]"
          style={{
            background:  'var(--gm-bg-hover)',
            color:       'var(--gm-text-muted)',
            border:      '1px solid var(--gm-border)',
          }}
        >
          {result.source_engine}
        </span>

        {/* Category */}
        {result.category && result.category !== 'status' && (
          <span
            className="gm-badge text-[10px]"
            style={{
              background: 'rgba(188,140,255,0.1)',
              color:      '#bc8cff',
              border:     '1px solid rgba(188,140,255,0.2)',
            }}
          >
            {result.category}
          </span>
        )}

        {/* Tags */}
        {result.tags.filter(t => t !== 'system').map(tag => (
          <span
            key={tag}
            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded"
            style={{
              background: 'rgba(47,129,247,0.1)',
              color:      'var(--gm-accent)',
              border:     '1px solid rgba(47,129,247,0.2)',
            }}
          >
            <Tag size={8} />
            {tag}
          </span>
        ))}

        <span className="flex-1" />

        {/* Timestamp */}
        {result.timestamp && (
          <span className="flex items-center gap-1 text-[10px]" style={{ color: 'var(--gm-text-muted)' }}>
            <Clock size={10} />
            {formatTimeAgo(result.timestamp)}
          </span>
        )}

        {/* URL */}
        {hasUrl && (
          <span
            className="text-[10px] font-mono truncate max-w-[180px] sm:max-w-[240px]"
            style={{ color: 'var(--gm-text-muted)' }}
            title={result.url}
          >
            {result.url}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Grouped results view
// ---------------------------------------------------------------------------

function GroupedResults({ results }: { results: SearchResult[] }) {
  const groups = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    (acc[r.source_engine] ??= []).push(r);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {Object.entries(groups).map(([engine, items]) => (
        <div key={engine}>
          <div className="flex items-center gap-2 mb-3">
            <h3
              className="text-xs font-semibold uppercase tracking-widest"
              style={{ color: 'var(--gm-text-muted)' }}
            >
              {engine}
            </h3>
            <div className="flex-1 h-px" style={{ background: 'var(--gm-border)' }} />
            <span className="text-xs" style={{ color: 'var(--gm-text-muted)' }}>{items.length}</span>
          </div>
          <div className="space-y-2">
            {items.map(r => <ResultCard key={r.id} result={r} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Side-by-side results view
// ---------------------------------------------------------------------------

function SideBySideResults({ results }: { results: SearchResult[] }) {
  const groups = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    (acc[r.source_engine] ??= []).push(r);
    return acc;
  }, {});

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {Object.entries(groups).map(([engine, items]) => (
        <div key={engine}>
          <div className="flex items-center gap-2 mb-2">
            <h3
              className="text-xs font-semibold uppercase tracking-widest"
              style={{ color: 'var(--gm-text-muted)' }}
            >
              {engine}
            </h3>
            <span className="text-xs" style={{ color: 'var(--gm-text-muted)' }}>({items.length})</span>
          </div>
          <div className="space-y-2">
            {items.map(r => <ResultCard key={r.id} result={r} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SearchPage
// ---------------------------------------------------------------------------

export function SearchPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Form state
  const [query, setQuery]                     = useState(searchParams.get('q') ?? '');
  const [selectedEngines, setSelectedEngines] = useState<string[]>(['duckduckgo', 'marginalia', 'urlscan']);
  const [mode, setMode]                       = useState<ReconMode>('passive');
  const [maxResults, setMaxResults]           = useState<number>(25);
  const [hasSearched, setHasSearched]         = useState(false);

  // Results UI state
  const [viewMode, setViewMode]               = useState<ViewMode>('blended');
  const [sortKey, setSortKey]                 = useState<SortKey>('relevance');
  const [activeCategory, setActiveCategory]   = useState<string | null>(null);

  const { data, isPending, isError, mutate, reset } = useSearch();

  // Auto-run search when URL has ?q= on mount
  useEffect(() => {
    const q = searchParams.get('q');
    if (q && q.trim()) {
      setQuery(q);
      setHasSearched(true);
      mutate({ query: q.trim(), engines: selectedEngines, mode, max_results: maxResults });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist to recent searches on results arrival
  useEffect(() => {
    if (data?.query) {
      saveRecentSearch(data.query, data.total, data.engines_used);
    }
  }, [data]);

  function handleToggleEngine(id: string, checked: boolean) {
    setSelectedEngines(prev =>
      checked ? [...prev, id] : prev.filter(e => e !== id),
    );
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || selectedEngines.length === 0) return;
    setHasSearched(true);
    setActiveCategory(null);
    navigate(`/search?q=${encodeURIComponent(trimmed)}`, { replace: true });
    mutate({ query: trimmed, engines: selectedEngines, mode, max_results: maxResults });
  }

  // Derived result data — never suppress results, always render what the API returns
  const allResults    = data?.results ?? [];
  const realResults   = allResults.filter(r => r.source_engine !== 'system');
  const categories    = [...new Set(realResults.map(r => r.category).filter(Boolean))] as string[];
  const filtered      = activeCategory ? realResults.filter(r => r.category === activeCategory) : realResults;
  const sorted        = sortResults(filtered, sortKey);
  const failedEngines = data?.engines_failed ?? [];
  const apiOffline    = hasSearched && !!data && data.engines_used.length === 0;

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-5 animate-fade-in">

      {/* ── Page header ── */}
      <div className="flex items-center gap-3">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: 'rgba(47,129,247,0.15)', color: 'var(--gm-accent)' }}
        >
          <Search size={16} />
        </div>
        <div>
          <h1 className="text-lg font-semibold leading-tight" style={{ color: 'var(--gm-text-primary)' }}>
            GhostMesh Search
          </h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--gm-text-secondary)' }}>
            Multi-engine open source intelligence search
          </p>
        </div>
      </div>

      {/* ── Search form card ── */}
      <form onSubmit={handleSubmit} className="gm-card space-y-4">

        {/* Query input */}
        <div className="relative">
          <Search
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: 'var(--gm-text-muted)' }}
          />
          <input
            className="gm-input"
            style={{ paddingLeft: '36px', fontSize: '14px', height: '44px' }}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search people, domains, emails, usernames, IPs..."
            autoFocus
            autoComplete="off"
            spellCheck={false}
          />
        </div>

        {/* Engine grid */}
        <div>
          <p
            className="text-xs font-semibold mb-2 uppercase tracking-widest"
            style={{ color: 'var(--gm-text-muted)' }}
          >
            Engines
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-5 gap-2">
            {ENGINE_OPTIONS.map(eng => (
              <EngineCheckbox
                key={eng.id}
                engine={eng}
                checked={selectedEngines.includes(eng.id)}
                onChange={handleToggleEngine}
              />
            ))}
          </div>
          {selectedEngines.length === 0 && (
            <p className="text-xs mt-1.5" style={{ color: 'var(--gm-red)' }}>
              Select at least one engine to search.
            </p>
          )}
        </div>

        {/* Mode + max results + submit */}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <ModeToggle mode={mode} onChange={setMode} />

          {/* Max results */}
          <div className="flex items-center gap-1.5 ml-auto">
            <span className="text-xs shrink-0" style={{ color: 'var(--gm-text-muted)' }}>
              Max results
            </span>
            <div
              className="flex rounded-lg overflow-hidden border"
              style={{ background: 'var(--gm-bg-panel)', borderColor: 'var(--gm-border)' }}
            >
              {MAX_RESULTS_OPTIONS.map(n => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setMaxResults(n)}
                  className={cn(
                    'px-3 py-1.5 text-xs font-medium transition-all',
                    maxResults === n
                      ? 'text-white'
                      : 'text-[var(--gm-text-muted)] hover:text-[var(--gm-text-secondary)]',
                  )}
                  style={maxResults === n ? { background: 'var(--gm-accent)' } : { background: 'transparent' }}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          <button
            type="submit"
            className="gm-btn gm-btn-primary w-full sm:w-auto"
            disabled={!query.trim() || selectedEngines.length === 0 || isPending}
          >
            {isPending ? <Spinner size="sm" /> : <Search size={14} />}
            {isPending ? 'Searching…' : 'Search'}
          </button>
        </div>
      </form>

      {/* ── Loading ── */}
      {isPending && (
        <div className="flex flex-col items-center gap-3 py-12">
          <Spinner size="lg" />
          <p className="text-sm" style={{ color: 'var(--gm-text-secondary)' }}>
            Querying {selectedEngines.length} engine{selectedEngines.length !== 1 ? 's' : ''}…
          </p>
        </div>
      )}

      {/* ── Mutation-level error ── */}
      {isError && !isPending && (
        <ErrorMessage
          title="Search failed"
          message="An unexpected error occurred. Please check your connection and try again."
          onRetry={() => {
            reset();
            const trimmed = query.trim();
            if (trimmed) mutate({ query: trimmed, engines: selectedEngines, mode, max_results: maxResults });
          }}
          onDiagnostics={() => navigate('/settings')}
        />
      )}

      {/* ── API offline banner (shown above results, not instead of them) ── */}
      {apiOffline && !isPending && (
        <ErrorMessage
          title="Search API unavailable"
          message="The GhostMesh backend could not be reached. Start the backend with ghostmesh/backend/start.sh, or add API keys in Settings."
          onRetry={() => mutate({ query: query.trim(), engines: selectedEngines, mode, max_results: maxResults })}
          onDiagnostics={() => navigate('/settings')}
        />
      )}

      {/* ── No search yet ── */}
      {!hasSearched && !isPending && (
        <EmptyState
          icon={Search}
          title="Enter a query and select at least one engine"
          description="GhostMesh fans out across configured OSINT engines and blends the results. DuckDuckGo requires no API key and is ready to use."
        />
      )}

      {/* ── Results ── */}
      {!isPending && data && realResults.length > 0 && (
        <div className="space-y-4">

          {/* Engine failure warning banner */}
          {failedEngines.length > 0 && (
            <div
              className="flex items-center gap-2.5 px-3 py-2.5 rounded-lg border text-xs flex-wrap"
              style={{
                background:  'rgba(240,167,50,0.06)',
                borderColor: 'rgba(240,167,50,0.35)',
                color:       'var(--gm-yellow)',
              }}
            >
              <AlertTriangle size={14} className="shrink-0" />
              <span>
                <strong>{failedEngines.length} engine{failedEngines.length !== 1 ? 's' : ''} failed</strong>
                {' '}({failedEngines.join(', ')})
              </span>
              <button
                type="button"
                className="underline hover:no-underline"
                onClick={() => navigate('/settings')}
              >
                view diagnostics
              </button>
            </div>
          )}

          {/* Results summary bar */}
          <div
            className="flex flex-wrap items-center gap-3 px-3 py-2 rounded-lg border"
            style={{ background: 'var(--gm-bg-card)', borderColor: 'var(--gm-border)' }}
          >
            <Filter size={13} style={{ color: 'var(--gm-text-muted)' }} />
            <span className="text-xs" style={{ color: 'var(--gm-text-secondary)' }}>
              <strong style={{ color: 'var(--gm-text-primary)' }}>{realResults.length}</strong>{' '}
              result{realResults.length !== 1 ? 's' : ''}
              {data.engines_used.length > 0 && (
                <>
                  {' from '}
                  <strong style={{ color: 'var(--gm-text-primary)' }}>
                    {data.engines_used.join(', ')}
                  </strong>
                </>
              )}
              {data.duration_ms > 0 && (
                <>
                  {' in '}
                  <strong style={{ color: 'var(--gm-text-primary)' }}>{data.duration_ms}ms</strong>
                </>
              )}
            </span>
            <div className="flex-1" />
            <ExportMenu results={realResults} query={data.query} />
          </div>

          {/* View toggle + sort */}
          <div className="flex flex-wrap items-center gap-2">
            <div
              className="flex rounded-lg overflow-hidden border"
              style={{ background: 'var(--gm-bg-panel)', borderColor: 'var(--gm-border)' }}
            >
              {([
                { id: 'blended',    label: 'Blended',     icon: Layers },
                { id: 'grouped',    label: 'Grouped',     icon: Grid   },
                { id: 'sidebyside', label: 'Side by side', icon: List  },
              ] as const).map(v => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setViewMode(v.id)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-all',
                    viewMode === v.id
                      ? 'text-white'
                      : 'text-[var(--gm-text-muted)] hover:text-[var(--gm-text-secondary)]',
                  )}
                  style={viewMode === v.id ? { background: 'var(--gm-accent)' } : { background: 'transparent' }}
                >
                  <v.icon size={12} />
                  <span className="hidden sm:inline">{v.label}</span>
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1.5 ml-auto">
              <span className="text-xs" style={{ color: 'var(--gm-text-muted)' }}>Sort</span>
              <select
                className="gm-input text-xs py-1"
                style={{ width: 'auto' }}
                value={sortKey}
                onChange={e => setSortKey(e.target.value as SortKey)}
              >
                <option value="relevance">Relevance</option>
                <option value="date">Date</option>
                <option value="confidence">Confidence</option>
                <option value="source">Source</option>
              </select>
            </div>
          </div>

          {/* Category filter chips */}
          {categories.length > 1 && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setActiveCategory(null)}
                className={cn(
                  'gm-badge text-xs cursor-pointer transition-all',
                  activeCategory === null
                    ? 'bg-[var(--gm-accent)] text-white'
                    : 'bg-[var(--gm-bg-hover)] text-[var(--gm-text-muted)] hover:bg-[var(--gm-border)]',
                )}
              >
                All
              </button>
              {categories.map(cat => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setActiveCategory(c => c === cat ? null : cat)}
                  className={cn(
                    'gm-badge text-xs cursor-pointer transition-all',
                    activeCategory === cat
                      ? 'bg-[var(--gm-accent)] text-white'
                      : 'bg-[var(--gm-bg-hover)] text-[var(--gm-text-muted)] hover:bg-[var(--gm-border)]',
                  )}
                >
                  {cat}
                </button>
              ))}
            </div>
          )}

          {/* Result list */}
          {sorted.length > 0 ? (
            <>
              {viewMode === 'blended'    && <div className="space-y-2">{sorted.map(r => <ResultCard key={r.id} result={r} />)}</div>}
              {viewMode === 'grouped'    && <GroupedResults    results={sorted} />}
              {viewMode === 'sidebyside' && <SideBySideResults results={sorted} />}
            </>
          ) : (
            <EmptyState
              icon={Search}
              title="No results in this category"
              description="Try clearing the category filter or broadening your search."
              action={{ label: 'Clear filter', onClick: () => setActiveCategory(null) }}
            />
          )}
        </div>
      )}

      {/* ── Zero results ── */}
      {!isPending && hasSearched && data && realResults.length === 0 && !apiOffline && (
        <EmptyState
          icon={Search}
          title={`No results for "${data.query}"`}
          description="Try broadening your query, selecting additional engines, or configuring more data sources in Settings."
          action={{
            label: 'New search',
            onClick: () => {
              setQuery('');
              setHasSearched(false);
              reset();
              navigate('/search', { replace: true });
            },
          }}
        />
      )}
    </div>
  );
}
