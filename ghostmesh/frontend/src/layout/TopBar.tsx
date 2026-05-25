import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Shield,
  Menu,
  X,
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
  LayoutGrid,
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
    label: 'Modules',
    path: '/modules',
    icon: <LayoutGrid size={16} />,
  },
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

export function TopBar() {
  const location = useLocation();
  const { data: health } = useHealth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    '/recon': true,
    '/entities': true,
  });

  const apiOnline = health?.api_status === 'online';
  const apiDegraded = health?.api_status === 'degraded';

  const statusColor = apiOnline
    ? 'var(--gm-teal)'
    : apiDegraded
    ? 'var(--gm-yellow)'
    : 'var(--gm-red)';

  const statusLabel = apiOnline ? 'API online' : apiDegraded ? 'API degraded' : 'API offline';

  function isActive(path: string): boolean {
    if (path === '/') return location.pathname === '/';
    return location.pathname === path || location.pathname.startsWith(path + '/');
  }

  function isSubActive(path: string): boolean {
    return location.pathname === path;
  }

  function toggleSection(path: string) {
    setExpandedSections((prev) => ({ ...prev, [path]: !prev[path] }));
  }

  function closeDrawer() {
    setDrawerOpen(false);
  }

  return (
    <>
      {/* Top bar */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          height: '52px',
          background: 'var(--gm-bg-panel)',
          borderBottom: '1px solid var(--gm-border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingLeft: '12px',
          paddingRight: '12px',
          zIndex: 50,
        }}
      >
        {/* Left: hamburger */}
        <button
          onClick={() => setDrawerOpen(true)}
          aria-label="Open navigation menu"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '36px',
            height: '36px',
            background: 'transparent',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
            color: 'var(--gm-text-secondary)',
            flexShrink: 0,
            transition: 'background 0.15s, color 0.15s',
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'var(--gm-bg-hover)';
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-text-primary)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
            (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-text-secondary)';
          }}
        >
          <Menu size={20} />
        </button>

        {/* Center: brand */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            position: 'absolute',
            left: '50%',
            transform: 'translateX(-50%)',
          }}
        >
          <div
            style={{
              width: '26px',
              height: '26px',
              background: 'linear-gradient(135deg, var(--gm-accent-dim), var(--gm-accent))',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Shield size={14} color="white" />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1px' }}>
            <span style={{ color: 'var(--gm-text-primary)', fontWeight: 700, fontSize: '14px', letterSpacing: '0.02em', whiteSpace: 'nowrap', lineHeight: 1 }}>
              JarvisOS
            </span>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: '3px',
              padding: '1px 5px', borderRadius: '3px',
              background: 'rgba(47,129,247,0.15)', border: '1px solid rgba(47,129,247,0.3)',
              color: 'var(--gm-accent)', fontSize: '8px', letterSpacing: '0.06em',
              textTransform: 'uppercase', fontWeight: 700,
            }}>GhostMesh <span style={{ color: 'var(--gm-teal)' }}>●</span></span>
          </div>
        </div>

        {/* Right: status dot */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            flexShrink: 0,
          }}
          title={statusLabel}
        >
          <div
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: statusColor,
              flexShrink: 0,
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
            {apiOnline ? 'Online' : apiDegraded ? 'Degraded' : 'Offline'}
          </span>
        </div>
      </div>

      {/* Overlay */}
      {drawerOpen && (
        <div
          onClick={closeDrawer}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.55)',
            zIndex: 58,
            backdropFilter: 'blur(2px)',
          }}
          aria-hidden="true"
        />
      )}

      {/* Slide-in drawer */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          bottom: 0,
          width: '260px',
          background: 'var(--gm-bg-panel)',
          borderRight: '1px solid var(--gm-border)',
          zIndex: 59,
          display: 'flex',
          flexDirection: 'column',
          transform: drawerOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
          overflow: 'hidden',
        }}
        aria-hidden={!drawerOpen}
      >
        {/* Drawer header */}
        <div
          style={{
            height: '52px',
            borderBottom: '1px solid var(--gm-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingLeft: '14px',
            paddingRight: '10px',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '26px',
                height: '26px',
                background: 'linear-gradient(135deg, var(--gm-accent-dim), var(--gm-accent))',
                borderRadius: '6px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Shield size={14} color="white" />
            </div>
            <div>
              <div
                style={{
                  color: 'var(--gm-text-primary)',
                  fontWeight: 700,
                  fontSize: '14px',
                  letterSpacing: '0.02em',
                }}
              >
                JarvisOS
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                <span style={{
                  display: 'inline-flex', alignItems: 'center',
                  padding: '1px 5px', borderRadius: '3px',
                  background: 'rgba(47,129,247,0.15)', border: '1px solid rgba(47,129,247,0.3)',
                  color: 'var(--gm-accent)', fontSize: '9px', letterSpacing: '0.06em',
                  textTransform: 'uppercase', fontWeight: 700,
                }}>GhostMesh</span>
                <span style={{ color: 'var(--gm-teal)', fontSize: '9px' }}>●</span>
              </div>
            </div>
          </div>
          <button
            onClick={closeDrawer}
            aria-label="Close navigation menu"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '32px',
              height: '32px',
              background: 'transparent',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              color: 'var(--gm-text-muted)',
              transition: 'background 0.15s, color 0.15s',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--gm-bg-hover)';
              (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-text-primary)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
              (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-text-muted)';
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Drawer nav */}
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
            const isExpanded = expandedSections[item.path];

            return (
              <div key={item.path}>
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
                      onClick={() => toggleSection(item.path)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        width: '100%',
                        padding: '9px 12px 9px 14px',
                        gap: '10px',
                        background: active ? 'rgba(47, 129, 247, 0.12)' : 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        color: active ? 'var(--gm-accent)' : 'var(--gm-text-secondary)',
                        fontSize: '13px',
                        fontWeight: active ? 600 : 400,
                        textAlign: 'left',
                        transition: 'background 0.15s, color 0.15s',
                      }}
                      onMouseEnter={(e) => {
                        if (!active) {
                          (e.currentTarget as HTMLButtonElement).style.background = 'var(--gm-bg-hover)';
                          (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-text-primary)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!active) {
                          (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                          (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-text-secondary)';
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
                      onClick={closeDrawer}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        padding: '9px 12px 9px 14px',
                        gap: '10px',
                        background: active ? 'rgba(47, 129, 247, 0.12)' : 'transparent',
                        color: active ? 'var(--gm-accent)' : 'var(--gm-text-secondary)',
                        fontSize: '13px',
                        fontWeight: active ? 600 : 400,
                        textDecoration: 'none',
                        transition: 'background 0.15s, color 0.15s',
                      }}
                      onMouseEnter={(e) => {
                        if (!active) {
                          (e.currentTarget as HTMLAnchorElement).style.background = 'var(--gm-bg-hover)';
                          (e.currentTarget as HTMLAnchorElement).style.color = 'var(--gm-text-primary)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!active) {
                          (e.currentTarget as HTMLAnchorElement).style.background = 'transparent';
                          (e.currentTarget as HTMLAnchorElement).style.color = 'var(--gm-text-secondary)';
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
                            onClick={closeDrawer}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              padding: '7px 12px 7px 12px',
                              gap: '8px',
                              background: subActive ? 'rgba(47, 129, 247, 0.10)' : 'transparent',
                              color: subActive ? 'var(--gm-accent)' : 'var(--gm-text-muted)',
                              fontSize: '12px',
                              fontWeight: subActive ? 600 : 400,
                              textDecoration: 'none',
                              transition: 'background 0.15s, color 0.15s',
                            }}
                            onMouseEnter={(e) => {
                              if (!subActive) {
                                (e.currentTarget as HTMLAnchorElement).style.background = 'var(--gm-bg-hover)';
                                (e.currentTarget as HTMLAnchorElement).style.color = 'var(--gm-text-secondary)';
                              }
                            }}
                            onMouseLeave={(e) => {
                              if (!subActive) {
                                (e.currentTarget as HTMLAnchorElement).style.background = 'transparent';
                                (e.currentTarget as HTMLAnchorElement).style.color = 'var(--gm-text-muted)';
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

        {/* Drawer footer */}
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
    </>
  );
}
