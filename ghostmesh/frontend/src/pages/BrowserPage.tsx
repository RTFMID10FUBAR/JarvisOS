import { Globe, AlertTriangle, Monitor, Shield, Cookie, Fingerprint, Info, Settings, PlusCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { SectionHeader, StatusBadge, EmptyState } from '../components';
import type { ServiceStatus } from '../types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ServiceRow {
  icon: React.ElementType;
  label: string;
  status: ServiceStatus;
  detail: string;
}

// ---------------------------------------------------------------------------
// Static service status data
// ---------------------------------------------------------------------------

const SERVICE_ROWS: ServiceRow[] = [
  {
    icon: Shield,
    label: 'Proxy Chain',
    status: 'offline',
    detail: 'Unavailable — proxy service not configured',
  },
  {
    icon: Monitor,
    label: 'Session Container',
    status: 'offline',
    detail: 'Unavailable — container service not running',
  },
  {
    icon: Cookie,
    label: 'Cookie Isolation',
    status: 'offline',
    detail: 'Unavailable',
  },
  {
    icon: Fingerprint,
    label: 'Device Profile',
    status: 'degraded',
    detail: 'Default browser headers',
  },
];

// ---------------------------------------------------------------------------
// BrowserPage
// ---------------------------------------------------------------------------

export function BrowserPage() {
  return (
    <div className="max-w-2xl animate-fade-in space-y-5">
      <SectionHeader
        icon={Globe}
        title="Browser"
        subtitle="Disposable isolated browser sessions"
      />

      {/* ------------------------------------------------------------------ */}
      {/* Status panel                                                        */}
      {/* ------------------------------------------------------------------ */}
      <div className="gm-card">
        <p
          className="text-xs font-semibold uppercase tracking-widest mb-4"
          style={{ color: 'var(--gm-text-muted)' }}
        >
          Service Status
        </p>
        <div className="space-y-0">
          {SERVICE_ROWS.map(({ icon: Icon, label, status, detail }) => (
            <div
              key={label}
              className="flex items-center justify-between gap-4 py-3 border-b last:border-b-0"
              style={{ borderColor: 'var(--gm-border)' }}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className="w-7 h-7 rounded-md flex items-center justify-center shrink-0"
                  style={{ background: 'var(--gm-bg-hover)', color: 'var(--gm-text-muted)' }}
                >
                  <Icon size={13} />
                </div>
                <div className="min-w-0">
                  <p
                    className="text-sm font-medium leading-tight"
                    style={{ color: 'var(--gm-text-primary)' }}
                  >
                    {label}
                  </p>
                  <p
                    className="text-xs mt-0.5"
                    style={{ color: 'var(--gm-text-muted)' }}
                  >
                    {detail}
                  </p>
                </div>
              </div>
              <StatusBadge status={status} size="sm" />
            </div>
          ))}
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* New Disposable Tab — disabled                                       */}
      {/* ------------------------------------------------------------------ */}
      <div className="gm-card">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <p
              className="text-sm font-semibold mb-1"
              style={{ color: 'var(--gm-text-primary)' }}
            >
              New Disposable Tab
            </p>
            <p
              className="text-xs leading-relaxed"
              style={{ color: 'var(--gm-text-muted)' }}
            >
              Isolated sessions require proxy and container services. See{' '}
              <Link
                to="/settings"
                className="hover:underline"
                style={{ color: 'var(--gm-accent)' }}
              >
                Settings &gt; Diagnostics
              </Link>{' '}
              to configure.
            </p>
          </div>
          <button
            className="gm-btn gm-btn-primary shrink-0"
            disabled
            title="Isolated sessions require proxy and container services. See Settings > Diagnostics to configure."
          >
            <PlusCircle size={14} />
            New Tab
          </button>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Current sessions — empty                                            */}
      {/* ------------------------------------------------------------------ */}
      <div className="gm-card">
        <p
          className="text-xs font-semibold uppercase tracking-widest mb-1"
          style={{ color: 'var(--gm-text-muted)' }}
        >
          Active Sessions
        </p>
        <EmptyState
          icon={Monitor}
          title="No active sessions"
          description="Sessions require the container service to be running. Configure the container runtime to enable isolated browser sessions."
          className="py-10"
        />
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Diagnostics / requirements card                                     */}
      {/* ------------------------------------------------------------------ */}
      <div className="gm-card space-y-4">
        <div className="flex items-center gap-2">
          <Info size={14} style={{ color: 'var(--gm-accent)' }} />
          <p
            className="text-sm font-semibold"
            style={{ color: 'var(--gm-text-primary)' }}
          >
            Requirements for Isolated Sessions
          </p>
        </div>

        <ul className="space-y-2.5">
          {[
            { label: 'Proxy service', example: 'e.g. Tor, SOCKS5 proxy' },
            { label: 'Container runtime', example: 'e.g. Docker, Podman' },
            { label: 'Session isolation backend', example: 'GhostMesh session-worker' },
          ].map(({ label, example }) => (
            <li key={label} className="flex items-start gap-2.5 text-sm">
              <span
                className="mt-2 w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: 'var(--gm-text-muted)' }}
              />
              <span>
                <span style={{ color: 'var(--gm-text-primary)' }}>{label}</span>
                {' '}
                <span style={{ color: 'var(--gm-text-muted)' }}>({example})</span>
              </span>
            </li>
          ))}
        </ul>

        <Link
          to="/settings"
          className="gm-btn gm-btn-secondary text-xs inline-flex"
          style={{ width: 'fit-content' }}
        >
          <Settings size={12} />
          Open Settings
        </Link>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Implementation note                                                 */}
      {/* ------------------------------------------------------------------ */}
      <div
        className="flex items-start gap-3 rounded-lg border px-4 py-3 text-sm"
        style={{
          background: 'rgba(47,129,247,0.05)',
          borderColor: 'rgba(47,129,247,0.25)',
        }}
      >
        <AlertTriangle size={14} className="shrink-0 mt-0.5" style={{ color: 'var(--gm-accent)' }} />
        <p style={{ color: 'var(--gm-text-secondary)', margin: 0, lineHeight: 1.6 }}>
          <span className="font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
            Browser isolation is not yet fully implemented.
          </span>{' '}
          Status shown above reflects actual service availability. Features will become available
          once the required backend services are configured and running.
        </p>
      </div>
    </div>
  );
}
