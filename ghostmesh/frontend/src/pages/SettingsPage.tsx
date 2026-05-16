import { useState } from 'react';
import {
  Settings,
  Activity,
  ClipboardList,
  Info,
  RefreshCw,
  Copy,
  Check,
  CheckCircle2,
  AlertCircle,
  Terminal,
  ChevronDown,
  ChevronRight,
  Trash2,
  Server,
  Clock,
  Layers,
  ShieldCheck,
} from 'lucide-react';
import { useHealth } from '../hooks/useHealth';
import { SectionHeader } from '../components/SectionHeader';
import { StatusBadge } from '../components/StatusBadge';
import { CopyButton } from '../components/CopyButton';
import type { ServiceStatus } from '../types';

// ── Engine definitions ─────────────────────────────────────────────────────

interface EngineConfig {
  id: string;
  name: string;
  requiresKey: boolean;
  envVar: string | null;
  note: string;
}

const ENGINES: EngineConfig[] = [
  {
    id: 'duckduckgo',
    name: 'DuckDuckGo',
    requiresKey: false,
    envVar: null,
    note: 'No API key required. Uses the public DuckDuckGo Instant Answer API.',
  },
  {
    id: 'searxng',
    name: 'SearXNG',
    requiresKey: false,
    envVar: 'SEARXNG_URL',
    note: 'Self-hosted SearXNG instance. Set SEARXNG_URL to your instance URL.',
  },
  {
    id: 'shodan',
    name: 'Shodan',
    requiresKey: true,
    envVar: 'SHODAN_API_KEY',
    note: 'IP intelligence, open ports, banner data. Requires a Shodan account.',
  },
  {
    id: 'virustotal',
    name: 'VirusTotal',
    requiresKey: true,
    envVar: 'VT_API_KEY',
    note: 'File, URL, and hash reputation analysis from 70+ AV engines.',
  },
  {
    id: 'haveibeenpwned',
    name: 'HaveIBeenPwned',
    requiresKey: true,
    envVar: 'HIBP_API_KEY',
    note: 'Breach database lookups. Requires a paid HIBP API plan.',
  },
  {
    id: 'hunter',
    name: 'Hunter.io',
    requiresKey: true,
    envVar: 'HUNTER_API_KEY',
    note: 'Email discovery and verification for a given domain.',
  },
];

// ── Audit log ──────────────────────────────────────────────────────────────

const AUDIT_LS_KEY = 'gm-audit-log';

interface AuditEntry {
  id: string;
  action: string;
  query?: string;
  timestamp: string;
  result_count?: number;
  engine?: string;
}

function loadAuditLog(): AuditEntry[] {
  try {
    const raw = localStorage.getItem(AUDIT_LS_KEY);
    if (raw) return JSON.parse(raw) as AuditEntry[];
  } catch { /* ignore */ }
  return [];
}

// ── Helpers ────────────────────────────────────────────────────────────────

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', second: '2-digit',
  });
}

// ── Tab button ─────────────────────────────────────────────────────────────

function TabBtn({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ElementType;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '6px 14px',
        borderRadius: '6px',
        border: 'none',
        cursor: 'pointer',
        fontSize: '13px',
        fontWeight: active ? 600 : 400,
        background: active ? 'rgba(47,129,247,0.15)' : 'transparent',
        color: active ? 'var(--gm-accent)' : 'var(--gm-text-secondary)',
        transition: 'all 0.15s',
        whiteSpace: 'nowrap',
      }}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}

// ── Info row ───────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '8px 0',
        borderBottom: '1px solid var(--gm-border)',
        fontSize: '13px',
      }}
    >
      <span style={{ color: 'var(--gm-text-muted)' }}>{label}</span>
      <span style={{ color: 'var(--gm-text-primary)', fontWeight: 500 }}>{value}</span>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

type Tab = 'engine_config' | 'diagnostics' | 'audit_log' | 'about';

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>('engine_config');
  const { data: health, refetch, isFetching } = useHealth();

  return (
    <div style={{ maxWidth: '780px' }}>
      <SectionHeader
        icon={Settings}
        title="Settings"
        subtitle="Engine configuration, diagnostics, audit log, and about"
      />

      {/* Tab bar */}
      <div
        style={{
          display: 'flex',
          gap: '4px',
          padding: '4px',
          background: 'var(--gm-bg-card)',
          border: '1px solid var(--gm-border)',
          borderRadius: '8px',
          marginBottom: '24px',
          width: 'fit-content',
          flexWrap: 'wrap',
        }}
      >
        <TabBtn active={tab === 'engine_config'} onClick={() => setTab('engine_config')} icon={Layers}       label="Engine Config" />
        <TabBtn active={tab === 'diagnostics'}   onClick={() => setTab('diagnostics')}   icon={Activity}     label="Diagnostics" />
        <TabBtn active={tab === 'audit_log'}     onClick={() => setTab('audit_log')}     icon={ClipboardList} label="Audit Log" />
        <TabBtn active={tab === 'about'}         onClick={() => setTab('about')}         icon={Info}         label="About" />
      </div>

      {tab === 'engine_config' && <EngineConfigTab health={health} />}
      {tab === 'diagnostics'   && <DiagnosticsTab health={health} refetch={refetch} isFetching={isFetching} />}
      {tab === 'audit_log'     && <AuditLogTab />}
      {tab === 'about'         && <AboutTab />}
    </div>
  );
}

// ── Engine Config Tab ──────────────────────────────────────────────────────

function EngineConfigTab({ health }: { health: ReturnType<typeof useHealth>['data'] }) {
  const configuredSet = new Set(health?.configured_engines ?? []);
  const missingSet    = new Set(health?.missing_env_vars ?? []);

  function engineStatus(eng: EngineConfig): ServiceStatus {
    if (!eng.requiresKey && !eng.envVar) return 'online';
    if (eng.envVar && missingSet.has(eng.envVar)) return 'degraded';
    if (configuredSet.has(eng.id)) return 'online';
    return 'degraded';
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {/* Note banner */}
      <div
        style={{
          padding: '10px 14px',
          background: 'rgba(47,129,247,0.06)',
          border: '1px solid rgba(47,129,247,0.2)',
          borderRadius: '6px',
          fontSize: '13px',
          color: 'var(--gm-text-secondary)',
          lineHeight: 1.6,
          marginBottom: '4px',
        }}
      >
        API keys are configured via environment variables on the backend. Edit the{' '}
        <code style={{ fontFamily: 'monospace', color: 'var(--gm-accent)', fontSize: '12px' }}>.env</code>{' '}
        file and restart the backend service.
      </div>

      {ENGINES.map((eng) => {
        const status = engineStatus(eng);
        const isConfigured = status === 'online';

        return (
          <div
            key={eng.id}
            className="gm-card"
            style={{ padding: '14px 16px' }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
              {/* Status indicator */}
              <div
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: isConfigured ? 'var(--gm-teal)' : 'var(--gm-yellow)',
                  marginTop: '5px',
                  flexShrink: 0,
                }}
              />

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px', flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)' }}>
                    {eng.name}
                  </span>
                  <StatusBadge status={status} size="sm" label={isConfigured ? 'Online' : 'Not configured'} />
                </div>

                <p style={{ margin: '0 0 8px', fontSize: '12px', color: 'var(--gm-text-muted)', lineHeight: 1.5 }}>
                  {eng.note}
                </p>

                {eng.envVar && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--gm-text-muted)' }}>Env var:</span>
                    <code
                      style={{
                        fontFamily: 'monospace',
                        fontSize: '12px',
                        color: isConfigured ? 'var(--gm-teal)' : 'var(--gm-yellow)',
                        background: 'var(--gm-bg-hover)',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        border: `1px solid ${isConfigured ? 'rgba(45,212,191,0.2)' : 'rgba(240,167,50,0.2)'}`,
                      }}
                    >
                      {eng.envVar}
                    </code>
                    <CopyButton value={eng.envVar} size={12} />
                  </div>
                )}
                {!eng.envVar && (
                  <span style={{ fontSize: '11px', color: 'var(--gm-teal)' }}>
                    No API key required
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Diagnostics Tab ────────────────────────────────────────────────────────

function DiagnosticsTab({
  health,
  refetch,
  isFetching,
}: {
  health: ReturnType<typeof useHealth>['data'];
  refetch: () => void;
  isFetching: boolean;
}) {
  const [rawOpen, setRawOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  function copyDiagnostics() {
    navigator.clipboard.writeText(JSON.stringify(health, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontSize: '12px', color: 'var(--gm-text-muted)' }}>
          {health?.timestamp ? `Last checked: ${formatDate(health.timestamp)}` : 'Checking…'}
        </span>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button
            className="gm-btn gm-btn-secondary"
            style={{ fontSize: '12px', padding: '5px 12px' }}
            onClick={copyDiagnostics}
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
            {copied ? 'Copied!' : 'Copy diagnostics'}
          </button>
          <button
            className="gm-btn gm-btn-secondary"
            style={{ fontSize: '12px', padding: '5px 12px' }}
            onClick={() => refetch()}
          >
            <RefreshCw size={13} style={{ animation: isFetching ? 'spin 1s linear infinite' : undefined }} />
            Refresh
          </button>
        </div>
      </div>

      {/* UI Status */}
      <DiagCard icon={ShieldCheck} title="UI Status">
        <InfoRow label="Status" value={<StatusBadge status={health?.ui_status ?? 'unknown'} size="sm" />} />
        <InfoRow label="Framework" value="React + Vite + TypeScript" />
      </DiagCard>

      {/* API Backend */}
      <DiagCard icon={Server} title="API Backend">
        <InfoRow label="Status" value={<StatusBadge status={health?.api_status ?? 'unknown'} size="sm" />} />
        <InfoRow label="Endpoint" value={<code style={{ fontFamily: 'monospace', fontSize: '12px' }}>/api/health</code>} />
        {health?.timestamp && (
          <InfoRow label="Last response" value={formatDate(health.timestamp)} />
        )}
      </DiagCard>

      {/* Engine Registry */}
      <DiagCard icon={Layers} title="Engine Registry">
        <InfoRow
          label="Registry status"
          value={<StatusBadge status={health?.engine_registry_status ?? 'unknown'} size="sm" />}
        />
        <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {(health?.configured_engines ?? []).map((eng) => (
            <div key={eng} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
              <CheckCircle2 size={13} color="var(--gm-teal)" />
              <span style={{ color: 'var(--gm-text-secondary)', flex: 1, textTransform: 'capitalize' }}>{eng}</span>
              <span style={{ color: 'var(--gm-teal)', fontSize: '11px' }}>online</span>
            </div>
          ))}
          {(health?.unavailable_engines ?? []).map((eng) => (
            <div key={eng.name} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '12px' }}>
              <AlertCircle size={13} color="var(--gm-yellow)" style={{ flexShrink: 0, marginTop: '1px' }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ color: 'var(--gm-text-secondary)' }}>{eng.name}</span>
                <span style={{ color: 'var(--gm-text-muted)', marginLeft: '8px', fontSize: '11px' }}>{eng.reason}</span>
                {eng.missing_key && (
                  <code
                    style={{
                      marginLeft: '8px',
                      fontFamily: 'monospace',
                      fontSize: '11px',
                      color: 'var(--gm-yellow)',
                      background: 'rgba(240,167,50,0.1)',
                      padding: '1px 5px',
                      borderRadius: '3px',
                    }}
                  >
                    {eng.missing_key}
                  </code>
                )}
              </div>
            </div>
          ))}
          {(health?.configured_engines?.length ?? 0) === 0 &&
            (health?.unavailable_engines?.length ?? 0) === 0 && (
              <span style={{ fontSize: '12px', color: 'var(--gm-text-muted)' }}>No engine data available</span>
            )}
        </div>
      </DiagCard>

      {/* Missing env vars */}
      {(health?.missing_env_vars?.length ?? 0) > 0 && (
        <DiagCard icon={AlertCircle} title="Missing Environment Variables" accent="var(--gm-yellow)">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
            {health!.missing_env_vars.map((v) => (
              <div key={v} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <code
                  style={{
                    fontFamily: 'monospace',
                    fontSize: '12px',
                    color: 'var(--gm-yellow)',
                    background: 'rgba(240,167,50,0.08)',
                    border: '1px solid rgba(240,167,50,0.2)',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    flex: 1,
                  }}
                >
                  {v}
                </code>
                <CopyButton value={v} size={12} />
              </div>
            ))}
          </div>
        </DiagCard>
      )}

      {/* Service Versions */}
      <DiagCard icon={Terminal} title="Service Versions">
        {Object.entries(health?.service_versions ?? {}).map(([svc, ver]) => (
          <InfoRow
            key={svc}
            label={svc.charAt(0).toUpperCase() + svc.slice(1)}
            value={<code style={{ fontFamily: 'monospace', fontSize: '12px' }}>v{ver}</code>}
          />
        ))}
      </DiagCard>

      {/* Uptime */}
      <DiagCard icon={Clock} title="Uptime">
        <InfoRow
          label="Backend uptime"
          value={health?.uptime_seconds != null ? formatUptime(health.uptime_seconds) : 'n/a'}
        />
      </DiagCard>

      {/* Raw JSON */}
      <div className="gm-card" style={{ padding: '12px 14px' }}>
        <button
          onClick={() => setRawOpen((v) => !v)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--gm-text-secondary)',
            fontSize: '13px',
            fontWeight: 600,
            padding: 0,
          }}
        >
          {rawOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          Raw health JSON
        </button>
        {rawOpen && (
          <pre
            style={{
              marginTop: '10px',
              padding: '12px',
              background: 'var(--gm-bg-base)',
              borderRadius: '6px',
              border: '1px solid var(--gm-border)',
              fontFamily: 'monospace',
              fontSize: '11px',
              color: 'var(--gm-text-secondary)',
              overflowX: 'auto',
              lineHeight: 1.6,
              maxHeight: '320px',
              overflowY: 'auto',
            }}
          >
            {JSON.stringify(health, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

function DiagCard({
  icon: Icon,
  title,
  accent = 'var(--gm-accent)',
  children,
}: {
  icon: React.ElementType;
  title: string;
  accent?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="gm-card" style={{ padding: '14px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
        <Icon size={14} color={accent} />
        <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)' }}>{title}</span>
      </div>
      {children}
    </div>
  );
}

// ── Audit Log Tab ──────────────────────────────────────────────────────────

function AuditLogTab() {
  const [entries, setEntries] = useState<AuditEntry[]>(() => loadAuditLog());
  const [confirmClear, setConfirmClear] = useState(false);

  function clearLog() {
    localStorage.removeItem(AUDIT_LS_KEY);
    setEntries([]);
    setConfirmClear(false);
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '12px', color: 'var(--gm-text-muted)' }}>
          {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
        </span>
        {entries.length > 0 && (
          confirmClear ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '12px', color: 'var(--gm-text-muted)' }}>Clear all entries?</span>
              <button
                onClick={clearLog}
                style={{
                  fontSize: '12px',
                  padding: '4px 12px',
                  background: 'var(--gm-red)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontWeight: 600,
                }}
              >
                Clear
              </button>
              <button
                className="gm-btn gm-btn-secondary"
                style={{ fontSize: '12px', padding: '4px 12px' }}
                onClick={() => setConfirmClear(false)}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              className="gm-btn gm-btn-secondary"
              style={{ fontSize: '12px', padding: '5px 12px', color: 'var(--gm-red)' }}
              onClick={() => setConfirmClear(true)}
            >
              <Trash2 size={13} />
              Clear Audit Log
            </button>
          )
        )}
      </div>

      {entries.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '48px 16px',
            color: 'var(--gm-text-muted)',
            fontSize: '13px',
          }}
        >
          <ClipboardList size={28} style={{ display: 'block', margin: '0 auto 12px', opacity: 0.4 }} />
          No audit log entries
        </div>
      ) : (
        <div
          className="gm-card"
          style={{ padding: 0, overflow: 'hidden' }}
        >
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--gm-border)' }}>
                {['Timestamp', 'Action', 'Query / Value', 'Results', 'Engine'].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: '8px 12px',
                      textAlign: 'left',
                      color: 'var(--gm-text-muted)',
                      fontWeight: 600,
                      fontSize: '11px',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, i) => (
                <tr
                  key={entry.id}
                  style={{
                    borderBottom: i < entries.length - 1 ? '1px solid var(--gm-border)' : undefined,
                    background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                  }}
                >
                  <td style={{ padding: '8px 12px', color: 'var(--gm-text-muted)', whiteSpace: 'nowrap' }}>
                    {formatDate(entry.timestamp)}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <span
                      style={{
                        fontSize: '11px',
                        padding: '2px 7px',
                        borderRadius: '4px',
                        background: 'rgba(47,129,247,0.1)',
                        color: 'var(--gm-accent)',
                        fontWeight: 600,
                      }}
                    >
                      {entry.action}
                    </span>
                  </td>
                  <td
                    style={{
                      padding: '8px 12px',
                      color: 'var(--gm-text-secondary)',
                      maxWidth: '220px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {entry.query ?? '—'}
                  </td>
                  <td style={{ padding: '8px 12px', color: 'var(--gm-text-muted)' }}>
                    {entry.result_count ?? '—'}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    {entry.engine ? (
                      <code
                        style={{
                          fontFamily: 'monospace',
                          fontSize: '11px',
                          color: 'var(--gm-text-secondary)',
                          background: 'var(--gm-bg-hover)',
                          padding: '1px 5px',
                          borderRadius: '3px',
                        }}
                      >
                        {entry.engine}
                      </code>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── About Tab ──────────────────────────────────────────────────────────────

function AboutTab() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Identity */}
      <div className="gm-card" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '10px',
              background: 'rgba(47,129,247,0.15)',
              border: '1px solid rgba(47,129,247,0.25)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--gm-accent)',
              fontSize: '20px',
              fontWeight: 900,
              fontFamily: 'monospace',
            }}
          >
            GM
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: '16px', color: 'var(--gm-text-primary)' }}>
              GhostMesh
            </div>
            <div style={{ fontSize: '12px', color: 'var(--gm-text-muted)', fontFamily: 'monospace' }}>
              v0.1.0
            </div>
          </div>
        </div>
        <p style={{ margin: '0', fontSize: '13px', color: 'var(--gm-text-secondary)', lineHeight: 1.6 }}>
          GhostMesh is an open source intelligence workstation built on JarvisOS.
          It provides a unified interface for passive OSINT data gathering across multiple
          public intelligence sources.
        </p>
      </div>

      {/* Architecture */}
      <div className="gm-card" style={{ padding: '14px 16px' }}>
        <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)', marginBottom: '10px' }}>
          Architecture
        </div>
        <InfoRow label="Frontend"   value="React + Vite + TypeScript" />
        <InfoRow label="Backend"    value="FastAPI (Python 3.11+)" />
        <InfoRow label="Framework"  value="JarvisOS v0.1.0" />
        <InfoRow label="Version"    value={<code style={{ fontFamily: 'monospace', fontSize: '12px' }}>v0.1.0</code>} />
        <InfoRow label="License"    value="MIT" />
      </div>

      {/* Source */}
      <div className="gm-card" style={{ padding: '14px 16px' }}>
        <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)', marginBottom: '10px' }}>
          Source
        </div>
        <div style={{ fontSize: '13px', color: 'var(--gm-text-muted)', marginBottom: '4px' }}>GitHub repository</div>
        <code
          style={{
            fontFamily: 'monospace',
            fontSize: '12px',
            color: 'var(--gm-accent)',
            background: 'var(--gm-bg-hover)',
            padding: '4px 10px',
            borderRadius: '4px',
            display: 'block',
          }}
        >
          JarvisOS/ghostmesh
        </code>
      </div>

      {/* Safety */}
      <div
        style={{
          padding: '12px 14px',
          background: 'rgba(45,212,191,0.05)',
          border: '1px solid rgba(45,212,191,0.2)',
          borderRadius: '8px',
          fontSize: '13px',
          color: 'var(--gm-text-secondary)',
          lineHeight: 1.6,
          display: 'flex',
          gap: '10px',
          alignItems: 'flex-start',
        }}
      >
        <ShieldCheck size={16} color="var(--gm-teal)" style={{ flexShrink: 0, marginTop: '1px' }} />
        <span>
          GhostMesh is designed for passive, public-source intelligence gathering. Active scanning
          features require explicit authorization. No private data is accessed.
        </span>
      </div>
    </div>
  );
}
