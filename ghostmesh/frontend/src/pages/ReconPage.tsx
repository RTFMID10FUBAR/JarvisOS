import { Link } from 'react-router-dom';
import { Radar, Globe, Cpu, Archive, FileSearch, ChevronRight, AlertTriangle } from 'lucide-react';
import { SectionHeader } from '../components';

// ---------------------------------------------------------------------------
// Sub-module definitions
// ---------------------------------------------------------------------------

const RECON_MODULES = [
  {
    label: 'Browser',
    path: '/recon/browser',
    icon: Globe,
    description: 'Isolated disposable browser sessions with proxy support',
    accentBg: 'rgba(47,129,247,0.12)',
    accentColor: 'var(--gm-accent)',
  },
  {
    label: 'Tech Sniper',
    path: '/recon/tech-sniper',
    icon: Cpu,
    description: 'Detect technology stack from HTTP responses',
    accentBg: 'rgba(57,211,83,0.12)',
    accentColor: 'var(--gm-teal)',
  },
  {
    label: 'Archive',
    path: '/recon/archive',
    icon: Archive,
    description: 'Search web archive snapshots',
    accentBg: 'rgba(188,140,255,0.12)',
    accentColor: 'var(--gm-purple)',
  },
  {
    label: 'Metadata',
    path: '/recon/metadata',
    icon: FileSearch,
    description: 'Extract metadata from documents and images',
    accentBg: 'rgba(240,167,50,0.12)',
    accentColor: 'var(--gm-yellow)',
  },
] as const;

// ---------------------------------------------------------------------------
// ReconPage
// ---------------------------------------------------------------------------

export function ReconPage() {
  return (
    <div className="max-w-3xl animate-fade-in">
      <SectionHeader
        icon={Radar}
        title="Recon"
        subtitle="Passive and active reconnaissance tools"
      />

      {/* Active mode warning */}
      <div
        className="flex items-start gap-3 rounded-lg border px-4 py-3 mb-8 text-sm"
        style={{
          background: 'rgba(240,167,50,0.06)',
          borderColor: 'rgba(240,167,50,0.35)',
        }}
      >
        <AlertTriangle
          size={15}
          className="shrink-0 mt-0.5"
          style={{ color: 'var(--gm-yellow)' }}
        />
        <p style={{ color: 'var(--gm-yellow)', margin: 0, lineHeight: 1.6 }}>
          <span className="font-semibold">Active scanning is disabled by default.</span>{' '}
          Only use active mode on systems you own or have written authorization to test.
        </p>
      </div>

      {/* Module cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {RECON_MODULES.map(({ label, path, icon: Icon, description, accentBg, accentColor }) => (
          <Link key={path} to={path} style={{ textDecoration: 'none' }}>
            <div
              className="gm-card h-full flex items-center gap-5 transition-all duration-150 group"
              style={{ cursor: 'pointer', padding: '1.25rem' }}
              onMouseEnter={(e) => {
                const el = e.currentTarget as HTMLDivElement;
                el.style.borderColor = 'var(--gm-accent)';
                el.style.background = 'var(--gm-bg-hover)';
                el.style.transform = 'translateY(-2px)';
                el.style.boxShadow = '0 6px 20px rgba(0,0,0,0.35)';
              }}
              onMouseLeave={(e) => {
                const el = e.currentTarget as HTMLDivElement;
                el.style.borderColor = 'var(--gm-border)';
                el.style.background = 'var(--gm-bg-card)';
                el.style.transform = 'translateY(0)';
                el.style.boxShadow = 'none';
              }}
            >
              {/* Icon square */}
              <div
                className="w-14 h-14 rounded-xl flex items-center justify-center shrink-0"
                style={{ background: accentBg, color: accentColor }}
              >
                <Icon size={26} />
              </div>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <p
                  className="text-sm font-semibold mb-1"
                  style={{ color: 'var(--gm-text-primary)' }}
                >
                  {label}
                </p>
                <p
                  className="text-xs leading-relaxed"
                  style={{ color: 'var(--gm-text-secondary)' }}
                >
                  {description}
                </p>
              </div>

              {/* Chevron */}
              <ChevronRight
                size={16}
                className="shrink-0 transition-transform group-hover:translate-x-0.5"
                style={{ color: 'var(--gm-text-muted)' }}
              />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
