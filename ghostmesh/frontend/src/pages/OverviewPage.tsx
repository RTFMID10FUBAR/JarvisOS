import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  LayoutDashboard,
  Server,
  Zap,
  Clock,
  Cpu,
  Search,
  Users,
  Network,
  Settings,
  AlertCircle,
  CheckCircle,
  XCircle,
  ChevronRight,
  ExternalLink,
  X,
  Key,
} from 'lucide-react';
import { useHealth } from '../hooks/useHealth';
import { StatusBadge, EmptyState, SectionHeader, Spinner } from '../components';
import { cn } from '../utils/cn';
import type { Alert, ServiceStatus } from '../types';

// ---------------------------------------------------------------------------
// Local types
// ---------------------------------------------------------------------------

interface RecentSearch {
  id: string;
  query: string;
  timestamp: string;
  resultCount: number;
  engines: string[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RECENT_SEARCHES_KEY = 'gm-recent-searches';

const INITIAL_ALERTS: Alert[] = [
  {
    id: 'alert-api-offline',
    severity: 'critical',
    title: 'API Backend Offline',
    message: 'Search and recon features unavailable',
    timestamp: new Date().toISOString(),
    dismissed: false,
  },
  {
    id: 'alert-missing-keys',
    severity: 'warning',
    title: '3 engines missing API keys',
    message: 'Configure in Settings',
    action: '/settings',
    timestamp: new Date().toISOString(),
    dismissed: false,
  },
  {
    id: 'alert-version',
    severity: 'info',
    title: 'GhostMesh v0.1.0 loaded',
    message: 'Check Settings to configure engines',
    action: '/settings',
    timestamp: new Date().toISOString(),
    dismissed: false,
  },
];

const MOCK_ENGINE_LIST: Array<{
  id: string;
  name: string;
  defaultStatus: 'online' | 'offline' | 'missing_key';
  defaultReason: string;
}> = [
  { id: 'searxng',        name: 'SearXNG',        defaultStatus: 'offline',      defaultReason: 'Service not running' },
  { id: 'duckduckgo',     name: 'DuckDuckGo',     defaultStatus: 'online',       defaultReason: 'No API key required' },
  { id: 'shodan',         name: 'Shodan',          defaultStatus: 'missing_key',  defaultReason: 'API key not configured' },
  { id: 'virustotal',     name: 'VirusTotal',      defaultStatus: 'missing_key',  defaultReason: 'API key not configured' },
  { id: 'haveibeenpwned', name: 'HaveIBeenPwned', defaultStatus: 'missing_key',  defaultReason: 'API key not configured' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60)    return 'just now';
  if (seconds < 3600)  return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function formatUptime(seconds: number): string {
  if (seconds === 0) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function loadRecentSearches(): RecentSearch[] {
  try {
    const raw = localStorage.getItem(RECENT_SEARCHES_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as RecentSearch[];
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// AlertBanner
// ---------------------------------------------------------------------------

interface AlertBannerProps {
  alerts: Alert[];
  onDismiss: (id: string) => void;
}

const SEVERITY_STYLES = {
  critical: {
    border: 'border-red-500/40',
    bg:     'bg-red-500/5',
    iconColor: 'var(--gm-red)',
    badgeBg:   'rgba(248,81,73,0.18)',
    badgeText: 'var(--gm-red)',
  },
  warning: {
    border: 'border-yellow-500/40',
    bg:     'bg-yellow-500/5',
    iconColor: 'var(--gm-yellow)',
    badgeBg:   'rgba(240,167,50,0.18)',
    badgeText: 'var(--gm-yellow)',
  },
  info: {
    border: 'border-blue-500/40',
    bg:     'bg-blue-500/5',
    iconColor: 'var(--gm-accent)',
    badgeBg:   'rgba(47,129,247,0.18)',
    badgeText: 'var(--gm-accent)',
  },
} as const;

function SeverityIcon({ severity, color }: { severity: string; color: string }) {
  if (severity === 'critical') return <XCircle     size={15} style={{ color }} className="shrink-0 mt-0.5" />;
  if (severity === 'warning')  return <AlertCircle size={15} style={{ color }} className="shrink-0 mt-0.5" />;
  return                              <CheckCircle size={15} style={{ color }} className="shrink-0 mt-0.5" />;
}

function AlertBanner({ alerts, onDismiss }: AlertBannerProps) {
  const active = alerts.filter(a => !a.dismissed);
  if (active.length === 0) return null;

  return (
    <div
      className="flex gap-3 overflow-x-auto pb-1 mb-5"
      style={{ scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch' } as React.CSSProperties}
    >
      {active.map(alert => {
        const s = SEVERITY_STYLES[alert.severity] ?? SEVERITY_STYLES.info;
        return (
          <div
            key={alert.id}
            className={cn(
              'flex items-start gap-2.5 shrink-0 rounded-lg border px-3 py-2.5',
              'min-w-[260px] max-w-[340px]',
              s.border, s.bg,
            )}
          >
            <SeverityIcon severity={alert.severity} color={s.iconColor} />
            <div className="flex-1 min-w-0">
              <div className="mb-0.5">
                <span
                  className="gm-badge text-[10px] font-semibold uppercase tracking-wide"
                  style={{ background: s.badgeBg, color: s.badgeText }}
                >
                  {alert.severity}
                </span>
              </div>
              <p className="text-xs font-semibold leading-tight" style={{ color: 'var(--gm-text-primary)' }}>
                {alert.title}
              </p>
              <p className="text-xs mt-0.5 leading-tight" style={{ color: 'var(--gm-text-secondary)' }}>
                {alert.message}
              </p>
              {alert.action && (
                <Link
                  to={alert.action}
                  className="text-xs mt-1 inline-flex items-center gap-0.5 hover:underline"
                  style={{ color: 'var(--gm-accent)' }}
                >
                  Configure <ChevronRight size={11} />
                </Link>
              )}
            </div>
            <button
              onClick={() => onDismiss(alert.id)}
              className="shrink-0 p-0.5 rounded hover:bg-[var(--gm-bg-hover)] transition-colors"
              style={{ color: 'var(--gm-text-muted)' }}
              aria-label={`Dismiss ${alert.severity} alert`}
            >
              <X size={13} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StatusCard
// ---------------------------------------------------------------------------

function StatusCard({
  icon: Icon,
  title,
  statusNode,
  detail,
  iconColor,
}: {
  icon: React.ElementType;
  title: string;
  statusNode: React.ReactNode;
  detail?: string;
  iconColor?: string;
}) {
  return (
    <div className="gm-card flex flex-col gap-2 min-w-0">
      <div className="flex items-center justify-between gap-2">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: 'var(--gm-bg-hover)', color: iconColor ?? 'var(--gm-text-secondary)' }}
        >
          <Icon size={16} />
        </div>
        <span className="text-xs shrink-0" style={{ color: 'var(--gm-text-muted)' }}>
          {title}
        </span>
      </div>
      <div className="mt-1">{statusNode}</div>
      {detail && (
        <p className="text-xs" style={{ color: 'var(--gm-text-muted)' }}>
          {detail}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// QuickActionButton
// ---------------------------------------------------------------------------

function QuickActionButton({
  to,
  icon: Icon,
  label,
  description,
  accent,
}: {
  to: string;
  icon: React.ElementType;
  label: string;
  description: string;
  accent?: string;
}) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3 p-3 rounded-lg border transition-all group hover:bg-[var(--gm-bg-hover)]"
      style={{ borderColor: 'var(--gm-border)', textDecoration: 'none' }}
    >
      <div
        className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
        style={{
          background: accent ? `${accent}18` : 'var(--gm-bg-hover)',
          color: accent ?? 'var(--gm-text-secondary)',
        }}
      >
        <Icon size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium leading-tight" style={{ color: 'var(--gm-text-primary)' }}>
          {label}
        </p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--gm-text-muted)' }}>
          {description}
        </p>
      </div>
      <ChevronRight
        size={15}
        className="shrink-0 transition-transform group-hover:translate-x-0.5"
        style={{ color: 'var(--gm-text-muted)' }}
      />
    </Link>
  );
}

// ---------------------------------------------------------------------------
// EngineStatusRow
// ---------------------------------------------------------------------------

function EngineStatusRow({
  name,
  engineStatus,
  reason,
}: {
  name: string;
  engineStatus: 'online' | 'offline' | 'missing_key';
  reason: string;
}) {
  const statusBadgeMap: Record<string, ServiceStatus> = {
    online:      'online',
    offline:     'offline',
    missing_key: 'degraded',
  };

  return (
    <div
      className="flex items-center gap-3 py-2.5 border-b last:border-b-0"
      style={{ borderColor: 'var(--gm-border)' }}
    >
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate" style={{ color: 'var(--gm-text-primary)' }}>
          {name}
        </p>
        {engineStatus !== 'online' && (
          <p
            className="text-xs mt-0.5 truncate flex items-center gap-1"
            style={{ color: 'var(--gm-text-muted)' }}
          >
            {engineStatus === 'missing_key' && <Key size={10} className="shrink-0" />}
            {reason}
          </p>
        )}
      </div>
      <StatusBadge status={statusBadgeMap[engineStatus] ?? 'unknown'} size="sm" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// RecentSearchRow
// ---------------------------------------------------------------------------

function RecentSearchRow({ search }: { search: RecentSearch }) {
  return (
    <Link
      to={`/search?q=${encodeURIComponent(search.query)}`}
      className="flex items-center gap-3 py-2.5 border-b last:border-b-0 group -mx-4 px-4 transition-colors hover:bg-[var(--gm-bg-hover)]"
      style={{ borderColor: 'var(--gm-border)', textDecoration: 'none' }}
    >
      <Search size={14} className="shrink-0" style={{ color: 'var(--gm-text-muted)' }} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate" style={{ color: 'var(--gm-text-primary)' }}>
          {search.query}
        </p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--gm-text-muted)' }}>
          {formatTimeAgo(new Date(search.timestamp))}
          {' · '}
          {search.resultCount} result{search.resultCount !== 1 ? 's' : ''}
          {search.engines.length > 0 && (
            <> · {search.engines.join(', ')}</>
          )}
        </p>
      </div>
      <ExternalLink
        size={13}
        className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ color: 'var(--gm-text-muted)' }}
      />
    </Link>
  );
}

// ---------------------------------------------------------------------------
// OverviewPage
// ---------------------------------------------------------------------------

export function OverviewPage() {
  const { data: health, isLoading } = useHealth();

  const [alerts, setAlerts] = useState<Alert[]>(INITIAL_ALERTS);
  const [recentSearches, setRecentSearches] = useState<RecentSearch[]>([]);

  // Load recent searches from localStorage on mount and listen for updates
  useEffect(() => {
    setRecentSearches(loadRecentSearches());

    const handleStorage = (e: StorageEvent) => {
      if (e.key === RECENT_SEARCHES_KEY) {
        setRecentSearches(loadRecentSearches());
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const dismissAlert = useCallback((id: string) => {
    setAlerts(prev => prev.map(a => (a.id === id ? { ...a, dismissed: true } : a)));
  }, []);

  // Derive values from health
  const apiStatus       = health?.api_status ?? 'unknown';
  const uptimeSecs      = health?.uptime_seconds ?? 0;
  const configuredCount = health?.configured_engines?.length ?? 0;
  const lastQueryTime   = health?.last_query_time;
  const missingVars     = health?.missing_env_vars ?? [];

  // Merge live health data into mock engine list
  const engines = MOCK_ENGINE_LIST.map(eng => {
    const unavailable = health?.unavailable_engines?.find(
      u => u.name.toLowerCase() === eng.name.toLowerCase(),
    );
    if (!unavailable) {
      const isConfigured = health?.configured_engines?.some(
        c => c.toLowerCase() === eng.id,
      );
      return {
        ...eng,
        status: isConfigured ? ('online' as const) : eng.defaultStatus,
        reason: eng.defaultReason,
      };
    }
    return {
      ...eng,
      status: (unavailable.missing_key ? 'missing_key' : 'offline') as 'offline' | 'missing_key',
      reason: unavailable.reason,
    };
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <Spinner size="lg" />
          <p className="text-sm" style={{ color: 'var(--gm-text-secondary)' }}>Loading system status…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6 animate-fade-in">

      {/* Page header */}
      <SectionHeader
        icon={LayoutDashboard}
        title="Overview"
        subtitle="System status & recent activity"
      />

      {/* Alert banner row — horizontally scrollable */}
      <AlertBanner alerts={alerts} onDismiss={dismissAlert} />

      {/* Status cards: 2-col mobile → 4-col desktop */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatusCard
          icon={Cpu}
          title="System"
          iconColor="var(--gm-teal)"
          statusNode={<StatusBadge status="online" />}
          detail={`Uptime ${formatUptime(uptimeSecs)}`}
        />
        <StatusCard
          icon={Server}
          title="API Backend"
          iconColor={apiStatus === 'online' ? 'var(--gm-teal)' : 'var(--gm-red)'}
          statusNode={<StatusBadge status={apiStatus} />}
          detail={apiStatus === 'offline' ? 'Cannot reach backend' : undefined}
        />
        <StatusCard
          icon={Zap}
          title="Search Engines"
          iconColor="var(--gm-yellow)"
          statusNode={
            <span className="text-lg font-bold font-mono" style={{ color: 'var(--gm-text-primary)' }}>
              {configuredCount}
              <span className="text-sm font-normal ml-1" style={{ color: 'var(--gm-text-muted)' }}>
                / {MOCK_ENGINE_LIST.length}
              </span>
            </span>
          }
          detail="Configured engines"
        />
        <StatusCard
          icon={Clock}
          title="Last Search"
          iconColor="var(--gm-accent)"
          statusNode={
            lastQueryTime ? (
              <span className="text-sm font-medium" style={{ color: 'var(--gm-text-primary)' }}>
                {formatTimeAgo(new Date(lastQueryTime))}
              </span>
            ) : (
              <span className="text-sm" style={{ color: 'var(--gm-text-muted)' }}>Never</span>
            )
          }
        />
      </div>

      {/* Engine Health + Quick Actions: stacked on mobile, side-by-side on desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Engine Health */}
        <div className="gm-card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
              Engine Health
            </h2>
            <Link
              to="/settings"
              className="text-xs flex items-center gap-1 hover:underline"
              style={{ color: 'var(--gm-accent)', textDecoration: 'none' }}
            >
              Configure <Settings size={11} />
            </Link>
          </div>
          <div>
            {engines.map(eng => (
              <EngineStatusRow
                key={eng.id}
                name={eng.name}
                engineStatus={eng.status}
                reason={eng.reason}
              />
            ))}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="gm-card">
          <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--gm-text-primary)' }}>
            Quick Actions
          </h2>
          <div className="space-y-2">
            <QuickActionButton
              to="/search"
              icon={Search}
              label="New Search"
              description="Multi-engine OSINT query"
              accent="var(--gm-accent)"
            />
            <QuickActionButton
              to="/entities/people"
              icon={Users}
              label="People Finder"
              description="Search public profiles and identities"
              accent="var(--gm-teal)"
            />
            <QuickActionButton
              to="/framework"
              icon={Network}
              label="OSINT Framework"
              description="Browse categorized intelligence tools"
              accent="#bc8cff"
            />
            <QuickActionButton
              to="/settings"
              icon={Settings}
              label="Run Diagnostics"
              description="Check engine status and configuration"
              accent="var(--gm-yellow)"
            />
          </div>
        </div>
      </div>

      {/* Recent Searches */}
      <div className="gm-card">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
            Recent Searches
          </h2>
          {recentSearches.length > 0 && (
            <Link
              to="/search"
              className="text-xs flex items-center gap-1 hover:underline"
              style={{ color: 'var(--gm-accent)', textDecoration: 'none' }}
            >
              New search <ChevronRight size={12} />
            </Link>
          )}
        </div>

        {recentSearches.length === 0 ? (
          <EmptyState
            icon={Search}
            title="No searches yet"
            description="Run a query from the Search page — your history will appear here."
          />
        ) : (
          <div className="mt-2">
            {recentSearches.slice(0, 5).map(s => (
              <RecentSearchRow key={s.id} search={s} />
            ))}
          </div>
        )}
      </div>

      {/* Missing Environment Variables — conditional */}
      {missingVars.length > 0 && (
        <div className="gm-card" style={{ borderColor: 'rgba(240,167,50,0.3)' }}>
          <div className="flex items-start gap-3">
            <AlertCircle size={16} className="mt-0.5 shrink-0" style={{ color: 'var(--gm-yellow)' }} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold mb-1" style={{ color: 'var(--gm-text-primary)' }}>
                Missing Environment Variables
              </p>
              <p className="text-xs mb-3" style={{ color: 'var(--gm-text-secondary)' }}>
                The following API keys are not configured. Some search engines will be unavailable.
              </p>
              <ul className="space-y-2">
                {missingVars.map(varName => (
                  <li key={varName} className="flex items-center justify-between gap-3 flex-wrap">
                    <code
                      className="text-xs font-mono px-2 py-0.5 rounded"
                      style={{ background: 'var(--gm-bg-hover)', color: 'var(--gm-yellow)' }}
                    >
                      {varName}
                    </code>
                    <Link
                      to="/settings"
                      className="text-xs flex items-center gap-1 shrink-0 hover:underline"
                      style={{ color: 'var(--gm-accent)', textDecoration: 'none' }}
                    >
                      Configure <ExternalLink size={10} />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
