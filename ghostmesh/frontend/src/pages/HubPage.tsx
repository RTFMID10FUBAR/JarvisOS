import { Link } from 'react-router-dom';
import {
  Shield,
  Brain,
  Code2,
  Wifi,
  Database,
  Lock,
  ChevronRight,
  Zap,
} from 'lucide-react';

interface Module {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  status: 'active' | 'coming_soon';
  version?: string;
  route?: string;
  tags: string[];
}

const MODULES: Module[] = [
  {
    id: 'ghostmesh',
    name: 'GhostMesh',
    description:
      'Professional OSINT & recon workspace. Multi-engine search, people finder, reverse image, entity graph, tech detection, and archive research — all passive, all transparent.',
    icon: <Shield size={28} />,
    status: 'active',
    version: '0.1.0',
    route: '/',
    tags: ['OSINT', 'Recon', 'Search', 'Entities'],
  },
  {
    id: 'cortex',
    name: 'Cortex AI',
    description:
      'Local AI assistant with multi-model routing, tool use, and long-term memory. Runs entirely on-device or connects to your own API endpoints.',
    icon: <Brain size={28} />,
    status: 'coming_soon',
    tags: ['AI', 'LLM', 'Assistant'],
  },
  {
    id: 'codescope',
    name: 'CodeScope',
    description:
      'Static analysis and code intelligence platform. AST search, dependency auditing, secret scanning, and SBOM generation across any repo.',
    icon: <Code2 size={28} />,
    status: 'coming_soon',
    tags: ['Code', 'Security', 'SAST'],
  },
  {
    id: 'netwatch',
    name: 'NetWatch',
    description:
      'Passive network monitoring and traffic analysis. Captures, classifies, and correlates flows without active scanning against unauthorized hosts.',
    icon: <Wifi size={28} />,
    status: 'coming_soon',
    tags: ['Network', 'Traffic', 'Passive'],
  },
  {
    id: 'vaultkeeper',
    name: 'VaultKeeper',
    description:
      'Encrypted local secrets and credential store with audit trails. AES-256 at rest, zero cloud sync, full access log.',
    icon: <Lock size={28} />,
    status: 'coming_soon',
    tags: ['Secrets', 'Vault', 'Audit'],
  },
  {
    id: 'databridge',
    name: 'DataBridge',
    description:
      'ETL pipeline builder for security data. Ingest from APIs, normalize to common schema, output to Elasticsearch, Splunk, or flat files.',
    icon: <Database size={28} />,
    status: 'coming_soon',
    tags: ['ETL', 'Data', 'Pipeline'],
  },
];

function ModuleCard({ mod }: { mod: Module }) {
  const isActive = mod.status === 'active';

  const card = (
    <div
      style={{
        background: 'var(--gm-bg-panel)',
        border: `1px solid ${isActive ? 'rgba(47,129,247,0.35)' : 'var(--gm-border)'}`,
        borderRadius: '12px',
        padding: '22px',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
        position: 'relative',
        overflow: 'hidden',
        transition: 'border-color 0.2s, box-shadow 0.2s',
        cursor: isActive ? 'pointer' : 'default',
        opacity: isActive ? 1 : 0.65,
      }}
      onMouseEnter={(e) => {
        if (isActive) {
          (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--gm-accent)';
          (e.currentTarget as HTMLDivElement).style.boxShadow = '0 0 0 1px rgba(47,129,247,0.2), 0 4px 24px rgba(47,129,247,0.08)';
        }
      }}
      onMouseLeave={(e) => {
        if (isActive) {
          (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(47,129,247,0.35)';
          (e.currentTarget as HTMLDivElement).style.boxShadow = 'none';
        }
      }}
    >
      {/* Glow accent for active */}
      {isActive && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: '2px',
          background: 'linear-gradient(90deg, var(--gm-accent-dim), var(--gm-accent), var(--gm-teal))',
          borderRadius: '12px 12px 0 0',
        }} />
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
        <div style={{
          width: '52px', height: '52px', flexShrink: 0,
          background: isActive
            ? 'linear-gradient(135deg, var(--gm-accent-dim), rgba(47,129,247,0.3))'
            : 'var(--gm-bg-hover)',
          borderRadius: '10px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: isActive ? 'var(--gm-accent)' : 'var(--gm-text-muted)',
          border: `1px solid ${isActive ? 'rgba(47,129,247,0.3)' : 'var(--gm-border)'}`,
        }}>
          {mod.icon}
        </div>
        <div style={{ textAlign: 'right' }}>
          {isActive ? (
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px',
              padding: '3px 8px', borderRadius: '999px', fontSize: '11px', fontWeight: 700,
              background: 'rgba(35,197,94,0.15)', border: '1px solid rgba(35,197,94,0.3)',
              color: 'var(--gm-teal)',
            }}>
              <Zap size={10} /> Active
            </span>
          ) : (
            <span style={{
              display: 'inline-flex', alignItems: 'center',
              padding: '3px 8px', borderRadius: '999px', fontSize: '11px', fontWeight: 600,
              background: 'var(--gm-bg-hover)', border: '1px solid var(--gm-border)',
              color: 'var(--gm-text-muted)',
            }}>
              Coming Soon
            </span>
          )}
        </div>
      </div>

      {/* Name + version */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <span style={{ fontSize: '17px', fontWeight: 700, color: 'var(--gm-text-primary)' }}>
            {mod.name}
          </span>
          {mod.version && (
            <span style={{ fontSize: '11px', color: 'var(--gm-text-muted)', fontFamily: 'monospace' }}>
              v{mod.version}
            </span>
          )}
        </div>
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-secondary)', lineHeight: '1.55' }}>
          {mod.description}
        </p>
      </div>

      {/* Tags */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        {mod.tags.map(tag => (
          <span key={tag} style={{
            padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 500,
            background: 'var(--gm-bg-hover)', color: 'var(--gm-text-muted)',
            border: '1px solid var(--gm-border)',
          }}>
            {tag}
          </span>
        ))}
      </div>

      {/* CTA */}
      {isActive && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--gm-accent)', fontSize: '13px', fontWeight: 600, marginTop: '2px' }}>
          Open module <ChevronRight size={14} />
        </div>
      )}
    </div>
  );

  if (isActive && mod.route) {
    return <Link to={mod.route} style={{ textDecoration: 'none' }}>{card}</Link>;
  }
  return card;
}

export function HubPage() {
  return (
    <div style={{ maxWidth: '1060px' }}>
      {/* Hero */}
      <div style={{ marginBottom: '36px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '12px' }}>
          <div style={{
            width: '48px', height: '48px',
            background: 'linear-gradient(135deg, var(--gm-accent-dim), var(--gm-accent))',
            borderRadius: '12px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Shield size={26} color="white" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 800, color: 'var(--gm-text-primary)', letterSpacing: '-0.02em' }}>
              JarvisOS
            </h1>
            <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-muted)', marginTop: '2px' }}>
              Modular intelligence & security platform
            </p>
          </div>
        </div>
        <p style={{ margin: 0, fontSize: '14px', color: 'var(--gm-text-secondary)', lineHeight: '1.6', maxWidth: '600px' }}>
          Select a module below to launch it. Each module is a self-contained workspace.
          Active modules are fully functional — no stubs, no placeholders.
        </p>
      </div>

      {/* Module grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap: '16px',
      }}>
        {MODULES.map(mod => <ModuleCard key={mod.id} mod={mod} />)}
      </div>

      <p style={{ marginTop: '40px', fontSize: '12px', color: 'var(--gm-text-muted)', lineHeight: '1.5' }}>
        JarvisOS v0.1 — All modules run locally. No telemetry. No external data sharing.
      </p>
    </div>
  );
}
