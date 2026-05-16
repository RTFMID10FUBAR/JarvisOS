import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Search,
  Radar,
  Users,
  Network,
} from 'lucide-react';

interface MobileNavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
}

const MOBILE_NAV_ITEMS: MobileNavItem[] = [
  {
    label: 'Overview',
    path: '/',
    icon: <LayoutDashboard size={20} />,
  },
  {
    label: 'Search',
    path: '/search',
    icon: <Search size={20} />,
  },
  {
    label: 'Recon',
    path: '/recon',
    icon: <Radar size={20} />,
  },
  {
    label: 'Entities',
    path: '/entities',
    icon: <Users size={20} />,
  },
  {
    label: 'Framework',
    path: '/framework',
    icon: <Network size={20} />,
  },
];

export function MobileNav() {
  const location = useLocation();

  function isActive(path: string): boolean {
    if (path === '/') return location.pathname === '/';
    return location.pathname === path || location.pathname.startsWith(path + '/');
  }

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        background: 'var(--gm-bg-panel)',
        borderTop: '1px solid var(--gm-border)',
        display: 'flex',
        alignItems: 'stretch',
        zIndex: 50,
        paddingBottom: 'env(safe-area-inset-bottom, 0px)',
      }}
    >
      {MOBILE_NAV_ITEMS.map((item) => {
        const active = isActive(item.path);
        return (
          <Link
            key={item.path}
            to={item.path}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: '56px',
              padding: '6px 4px',
              gap: '3px',
              textDecoration: 'none',
              color: active ? 'var(--gm-accent)' : 'var(--gm-text-muted)',
              transition: 'color 0.15s',
              WebkitTapHighlightColor: 'transparent',
            }}
            onMouseEnter={(e) => {
              if (!active) {
                (e.currentTarget as HTMLAnchorElement).style.color =
                  'var(--gm-text-secondary)';
              }
            }}
            onMouseLeave={(e) => {
              if (!active) {
                (e.currentTarget as HTMLAnchorElement).style.color =
                  'var(--gm-text-muted)';
              }
            }}
          >
            {/* Hit target wrapper — minimum 48x48 */}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '3px',
                minWidth: '48px',
                minHeight: '48px',
                borderRadius: '8px',
                background: active ? 'rgba(47, 129, 247, 0.12)' : 'transparent',
                transition: 'background 0.15s',
              }}
            >
              {item.icon}
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: active ? 600 : 400,
                  letterSpacing: '0.02em',
                  lineHeight: 1,
                  whiteSpace: 'nowrap',
                }}
              >
                {item.label}
              </span>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
