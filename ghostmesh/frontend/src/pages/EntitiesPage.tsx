import { Users, Image, Braces, Network, ChevronRight } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

interface ModuleCard {
  icon: LucideIcon;
  title: string;
  description: string;
  to: string;
  accent: string;
}

const MODULES: ModuleCard[] = [
  {
    icon: Users,
    title: 'People Finder',
    description: 'Search public records and social profiles',
    to: '/entities/people',
    accent: 'var(--gm-accent)',
  },
  {
    icon: Image,
    title: 'Image Search',
    description: 'Reverse image search and visual matching',
    to: '/entities/images',
    accent: 'var(--gm-purple)',
  },
  {
    icon: Braces,
    title: 'Entity Extract',
    description: 'Extract emails, IPs, domains, usernames from text',
    to: '/entities/extract',
    accent: 'var(--gm-teal)',
  },
  {
    icon: Network,
    title: 'Entity Graph',
    description: 'Visualize relationships between entities',
    to: '/entities/graph',
    accent: 'var(--gm-yellow)',
  },
];

export function EntitiesPage() {
  return (
    <div style={{ maxWidth: '860px' }}>
      {/* Page header */}
      <div style={{ marginBottom: '28px' }}>
        <h1
          style={{
            margin: '0 0 4px 0',
            fontSize: '20px',
            fontWeight: 700,
            color: 'var(--gm-text-primary)',
          }}
        >
          Entities
        </h1>
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-secondary)' }}>
          OSINT tools for people, images, and entity relationship mapping
        </p>
      </div>

      {/* Module grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
          gap: '14px',
        }}
      >
        {MODULES.map((mod) => (
          <ModuleCardItem key={mod.to} {...mod} />
        ))}
      </div>
    </div>
  );
}

function ModuleCardItem({ icon: Icon, title, description, to, accent }: ModuleCard) {
  return (
    <Link
      to={to}
      style={{ textDecoration: 'none' }}
    >
      <div
        className="gm-card"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '16px',
          padding: '20px',
          cursor: 'pointer',
          transition: 'border-color 0.15s, background 0.15s',
          borderColor: 'var(--gm-border)',
        }}
        onMouseEnter={(e) => {
          const el = e.currentTarget as HTMLDivElement;
          el.style.borderColor = accent;
          el.style.background = 'var(--gm-bg-hover)';
        }}
        onMouseLeave={(e) => {
          const el = e.currentTarget as HTMLDivElement;
          el.style.borderColor = 'var(--gm-border)';
          el.style.background = 'var(--gm-bg-card)';
        }}
      >
        {/* Icon */}
        <div
          style={{
            width: '48px',
            height: '48px',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            background: `color-mix(in srgb, ${accent} 12%, transparent)`,
            color: accent,
          }}
        >
          <Icon size={22} />
        </div>

        {/* Text */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: '15px',
              fontWeight: 600,
              color: 'var(--gm-text-primary)',
              marginBottom: '3px',
            }}
          >
            {title}
          </div>
          <div
            style={{
              fontSize: '13px',
              color: 'var(--gm-text-secondary)',
              lineHeight: '1.4',
            }}
          >
            {description}
          </div>
        </div>

        {/* Arrow */}
        <ChevronRight size={18} style={{ color: 'var(--gm-text-muted)', flexShrink: 0 }} />
      </div>
    </Link>
  );
}
