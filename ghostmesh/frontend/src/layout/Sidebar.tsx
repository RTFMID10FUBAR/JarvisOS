import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Shield,
  LayoutDashboard,
  Search,
  Radar,
  Users,
  Network,
  FileText,
  Settings,
  ChevronRight,
  Globe,
  Cpu,
  Archive,
  FileSearch,
  UserSearch,
  Image,
  Scissors,
  GitFork,
} from 'lucide-react';
import { useHealth } from '../hooks/useHealth';

interface NavSubItem {
  label: string;
  path: string;
  icon: React.ReactNode;
}

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  subItems?: NavSubItem[];
}

const NAV_ITEMS: NavItem[] = [
  {
    label: 'Overview',
    path: '/',
    icon: <LayoutDashboard size={16} />,
  },
  {
    label: 'Search',
    path: '/search',
    icon: <Search size={16} />,
  },
  {
    label: 'Recon',
    path: '/recon',
    icon: <Radar size={16} />,
    subItems: [
      { label: 'Browser', path: '/recon/browser', icon: <Globe size={14} /> },
      { label: 'Tech Sniper', path: '/recon/tech', icon: <Cpu size={14} /> },
      { label: 'Archive', path: '/recon/archive', icon: <Archive size={14} /> },
      { label: 'Metadata', path: '/recon/metadata', icon: <FileSearch size={14} /> },
    ],
  },
  {
    label: 'Entities',
    path: '/entities',
    icon: <Users size={16} />,
    subItems: [
      { label: 'People Finder', path: '/entities/people', icon: <UserSearch size={14} /> },
      { label: 'Image Search', path: '/entities/images', icon: <Image size={14} /> },
      { label: 'Extract', path: '/entities/extract', icon: <Scissors size={14} /> },
      { label: 'Graph', path: '/entities/graph', icon: <GitFork size={14} /> },
    ],
  },
  {
    label: 'Framework',
    path: '/framework',
    icon: <Network size={16} />,
  },
  {
    label: 'Reports',
    path: '/reports',
    icon: <FileText size={16} />,
  },
  {
    label: 'Settings',
    path: '/settings',
    icon: <Settings size={16} />,
  },
];

export function Sidebar() {
  const location = useLocation();
  const { data: health } = useHealth();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    '/recon': true,
    '/entities': true,
  });

  const apiOnline = health?.api_status === 'online';
  const apiDegraded = health?.api_status === 'degraded';

  function toggleExpand(path: string) {
    setExpanded((prev) => ({ ...prev, [path]: !prev[path] }));
  }

  function isActive(path: string): boolean {
    if (path === '/') return location.pathname === '/';
    return location.pathname === path || location.pathname.startsWith(path + '/');
  }

  function isSubActive(path: string): boolean {
    return location.pathname === path;
  }

  const statusColor = apiOnline
    ? 'var(--gm-teal)'
    : apiDegraded
    ? 'var(--gm-yellow)'
    : 'var(--gm-red)';

  const statusLabel = apiOnline ? 'API online' : apiDegraded ? 'API degraded' : 'API offline';

  return (
    <div
      style={{
        position: 'fixed',
        left: 0,
        top: 0,
        bottom: 0,
        width: '220px',
        background: 'var(--gm-bg-panel)',
        borderRight: '1px solid var(--gm-border)',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 40,
        overflow: 'hidden',
      }}
    >
      {/* Logo / Title */}
      <div
        style={{
          padding: '16px 14px 14px',
          borderBottom: '1px solid var(--gm-border)',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: '32px',
            height: '32px',
            background: 'linear-gradient(135deg, var(--gm-accent-dim), var(--gm-accent))',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <Shield size={18} color="white" />
        </div>
        <div style={{ overflow: 'hidden' }}>
          <div
            style={{
              color: 'var(--gm-text-primary)',
              fontWeight: 700,
              fontSize: '15px',
              letterSpacing: '0.02em',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            GhostMesh
          </div>
          <div
            style={{
              color: 'var(--gm-text-muted)',
              fontSize: '10px',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            OSINT Platform
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          padding: '8px 0',
        }}
      >
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.path);
          const hasSubItems = !!item.subItems?.length;
          const isExpanded = expanded[item.path];

          return (
            <div key={item.path}>
              {/* Parent nav item */}
              <div style={{ position: 'relative' }}>
                {active && (
                  <div
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: '3px',
                      background: 'var(--gm-accent)',
                      borderRadius: '0 2px 2px 0',
                    }}
                  />
                )}
                {hasSubItems ? (
                  <button
                    onClick={() => toggleExpand(item.path)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      width: '100%',
                      padding: '8px 12px 8px 14px',
                      gap: '10px',
                      background: active
                        ? 'rgba(47, 129, 247, 0.12)'
                        : 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      color: active
                        ? 'var(--gm-accent)'
                        : 'var(--gm-text-secondary)',
                      fontSize: '13px',
                      fontWeight: active ? 600 : 400,
                      textAlign: 'left',
                      transition: 'background 0.15s, color 0.15s',
                      borderRadius: '0',
                    }}
                    onMouseEnter={(e) => {
                      if (!active) {
                        (e.currentTarget as HTMLButtonElement).style.background =
                          'var(--gm-bg-hover)';
                        (e.currentTarget as HTMLButtonElement).style.color =
                          'var(--gm-text-primary)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!active) {
                        (e.currentTarget as HTMLButtonElement).style.background =
                          'transparent';
                        (e.currentTarget as HTMLButtonElement).style.color =
                          'var(--gm-text-secondary)';
                      }
                    }}
                  >
                    <span style={{ flexShrink: 0 }}>{item.icon}</span>
                    <span
                      style={{
                        flex: 1,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {item.label}
                    </span>
                    <ChevronRight
                      size={13}
                      style={{
                        flexShrink: 0,
                        transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                        transition: 'transform 0.2s',
                        color: 'var(--gm-text-muted)',
                      }}
                    />
                  </button>
                ) : (
                  <Link
                    to={item.path}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      padding: '8px 12px 8px 14px',
                      gap: '10px',
                      background: active
                        ? 'rgba(47, 129, 247, 0.12)'
                        : 'transparent',
                      color: active
                        ? 'var(--gm-accent)'
                        : 'var(--gm-text-secondary)',
                      fontSize: '13px',
                      fontWeight: active ? 600 : 400,
                      textDecoration: 'none',
                      transition: 'background 0.15s, color 0.15s',
                    }}
                    onMouseEnter={(e) => {
                      if (!active) {
                        (e.currentTarget as HTMLAnchorElement).style.background =
                          'var(--gm-bg-hover)';
                        (e.currentTarget as HTMLAnchorElement).style.color =
                          'var(--gm-text-primary)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!active) {
                        (e.currentTarget as HTMLAnchorElement).style.background =
                          'transparent';
                        (e.currentTarget as HTMLAnchorElement).style.color =
                          'var(--gm-text-secondary)';
                      }
                    }}
                  >
                    <span style={{ flexShrink: 0 }}>{item.icon}</span>
                    <span
                      style={{
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {item.label}
                    </span>
                  </Link>
                )}
              </div>

              {/* Sub items */}
              {hasSubItems && isExpanded && (
                <div
                  style={{
                    borderLeft: '1px solid var(--gm-border-muted)',
                    marginLeft: '26px',
                    marginBottom: '4px',
                  }}
                >
                  {item.subItems!.map((sub) => {
                    const subActive = isSubActive(sub.path);
                    return (
                      <div key={sub.path} style={{ position: 'relative' }}>
                        {subActive && (
                          <div
                            style={{
                              position: 'absolute',
                              left: 0,
                              top: 0,
                              bottom: 0,
                              width: '2px',
                              background: 'var(--gm-accent)',
                            }}
                          />
                        )}
                        <Link
                          to={sub.path}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            padding: '6px 12px 6px 12px',
                            gap: '8px',
                            background: subActive
                              ? 'rgba(47, 129, 247, 0.10)'
                              : 'transparent',
                            color: subActive
                              ? 'var(--gm-accent)'
                              : 'var(--gm-text-muted)',
                            fontSize: '12px',
                            fontWeight: subActive ? 600 : 400,
                            textDecoration: 'none',
                            transition: 'background 0.15s, color 0.15s',
                          }}
                          onMouseEnter={(e) => {
                            if (!subActive) {
                              (e.currentTarget as HTMLAnchorElement).style.background =
                                'var(--gm-bg-hover)';
                              (e.currentTarget as HTMLAnchorElement).style.color =
                                'var(--gm-text-secondary)';
                            }
                          }}
                          onMouseLeave={(e) => {
                            if (!subActive) {
                              (e.currentTarget as HTMLAnchorElement).style.background =
                                'transparent';
                              (e.currentTarget as HTMLAnchorElement).style.color =
                                'var(--gm-text-muted)';
                            }
                          }}
                        >
                          <span style={{ flexShrink: 0 }}>{sub.icon}</span>
                          <span
                            style={{
                              whiteSpace: 'nowrap',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                            }}
                          >
                            {sub.label}
                          </span>
                        </Link>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Bottom status bar */}
      <div
        style={{
          borderTop: '1px solid var(--gm-border)',
          padding: '10px 14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: '11px',
            color: 'var(--gm-text-muted)',
            fontFamily: 'monospace',
            letterSpacing: '0.04em',
          }}
        >
          v0.1.0
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div
            title={statusLabel}
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: statusColor,
              flexShrink: 0,
              animation: apiOnline ? 'pulse-dot 2s ease-in-out infinite' : 'none',
            }}
            className={apiOnline ? 'animate-pulse-dot' : ''}
          />
          <span
            style={{
              fontSize: '11px',
              color: statusColor,
              whiteSpace: 'nowrap',
            }}
          >
            {statusLabel}
          </span>
        </div>
      </div>
    </div>
  );
}
