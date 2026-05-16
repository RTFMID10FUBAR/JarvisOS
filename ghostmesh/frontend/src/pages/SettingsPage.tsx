import { useState } from 'react';
import { Settings, Key, CheckCircle2, AlertCircle, Eye, EyeOff, Save, RefreshCw } from 'lucide-react';
import { useHealth } from '../hooks/useHealth';

interface ApiKeyField {
  id: string;
  label: string;
  envVar: string;
  description: string;
  docsUrl: string;
}

const API_KEY_FIELDS: ApiKeyField[] = [
  {
    id: 'shodan',
    label: 'Shodan',
    envVar: 'SHODAN_API_KEY',
    description: 'Required for IP/host intelligence and device search.',
    docsUrl: 'https://developer.shodan.io/',
  },
  {
    id: 'virustotal',
    label: 'VirusTotal',
    envVar: 'VT_API_KEY',
    description: 'Required for file/URL/hash reputation lookups.',
    docsUrl: 'https://developers.virustotal.com/',
  },
  {
    id: 'hunter',
    label: 'Hunter.io',
    envVar: 'HUNTER_API_KEY',
    description: 'Required for email finding and verification.',
    docsUrl: 'https://hunter.io/api',
  },
  {
    id: 'haveibeenpwned',
    label: 'HaveIBeenPwned',
    envVar: 'HIBP_API_KEY',
    description: 'Required for breach database lookups.',
    docsUrl: 'https://haveibeenpwned.com/API/v3',
  },
  {
    id: 'google_cse',
    label: 'Google CSE',
    envVar: 'GOOGLE_CSE_KEY',
    description: 'Custom Search Engine key for Google results.',
    docsUrl: 'https://developers.google.com/custom-search/',
  },
];

interface KeyValues {
  [key: string]: string;
}

interface ShowKeys {
  [key: string]: boolean;
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize: '11px',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'var(--gm-text-muted)',
        display: 'block',
        marginBottom: '6px',
      }}
    >
      {children}
    </span>
  );
}

export function SettingsPage() {
  const { data: health, refetch } = useHealth();
  const [keyValues, setKeyValues] = useState<KeyValues>({});
  const [showKeys, setShowKeys] = useState<ShowKeys>({});
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set());
  const [activeSection, setActiveSection] = useState<'general' | 'api_keys' | 'diagnostics'>('general');

  const missingEnvVars = new Set(health?.missing_env_vars ?? []);

  function toggleShow(id: string) {
    setShowKeys((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  function saveKey(field: ApiKeyField) {
    // In a real app, this would POST to the API; here we just mark as "saved" in UI
    setSavedKeys((prev) => new Set([...prev, field.id]));
    setTimeout(() => {
      setSavedKeys((prev) => {
        const next = new Set(prev);
        next.delete(field.id);
        return next;
      });
    }, 2000);
  }

  const tabStyle = (tab: string): React.CSSProperties => ({
    padding: '6px 14px',
    borderRadius: '6px',
    border: 'none',
    cursor: 'pointer',
    fontSize: '13px',
    fontWeight: activeSection === tab ? 600 : 400,
    background: activeSection === tab ? 'rgba(47,129,247,0.15)' : 'transparent',
    color: activeSection === tab ? 'var(--gm-accent)' : 'var(--gm-text-secondary)',
    transition: 'all 0.15s',
  });

  return (
    <div style={{ maxWidth: '720px' }}>
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Settings size={20} color="var(--gm-accent)" />
        <div>
          <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--gm-text-primary)' }}>
            Settings
          </h1>
          <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-muted)' }}>
            Configuration, API keys, and diagnostics
          </p>
        </div>
      </div>

      {/* Tab nav */}
      <div
        style={{
          display: 'flex',
          gap: '4px',
          padding: '4px',
          background: 'var(--gm-bg-card)',
          border: '1px solid var(--gm-border)',
          borderRadius: '8px',
          marginBottom: '20px',
          width: 'fit-content',
        }}
      >
        <button style={tabStyle('general')} onClick={() => setActiveSection('general')}>General</button>
        <button style={tabStyle('api_keys')} onClick={() => setActiveSection('api_keys')}>API Keys</button>
        <button style={tabStyle('diagnostics')} onClick={() => setActiveSection('diagnostics')}>Diagnostics</button>
      </div>

      {/* General */}
      {activeSection === 'general' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div className="gm-card">
            <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)', marginBottom: '16px' }}>
              Application
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <Label>Default recon mode</Label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {['passive', 'active'].map((m) => (
                    <button
                      key={m}
                      style={{
                        padding: '6px 16px',
                        borderRadius: '6px',
                        border: '1px solid',
                        borderColor: m === 'passive' ? 'var(--gm-accent)' : 'var(--gm-border)',
                        background: m === 'passive' ? 'rgba(47,129,247,0.12)' : 'transparent',
                        color: m === 'passive' ? 'var(--gm-accent)' : 'var(--gm-text-muted)',
                        fontSize: '13px',
                        fontWeight: m === 'passive' ? 600 : 400,
                        cursor: 'pointer',
                        textTransform: 'capitalize',
                      }}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <Label>Max results per query</Label>
                <select
                  className="gm-input"
                  defaultValue="50"
                  style={{ maxWidth: '200px', appearance: 'none' }}
                >
                  <option value="10">10</option>
                  <option value="25">25</option>
                  <option value="50">50</option>
                  <option value="100">100</option>
                </select>
              </div>
              <div>
                <Label>Theme</Label>
                <select
                  className="gm-input"
                  defaultValue="dark"
                  style={{ maxWidth: '200px', appearance: 'none' }}
                >
                  <option value="dark">Dark (default)</option>
                  <option value="darker">Darker</option>
                </select>
              </div>
            </div>
          </div>

          <div className="gm-card">
            <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)', marginBottom: '12px' }}>
              Data &amp; Privacy
            </div>
            <p style={{ fontSize: '13px', color: 'var(--gm-text-secondary)', margin: '0 0 12px', lineHeight: 1.5 }}>
              GhostMesh stores search history locally in your browser. No data is sent to external servers unless
              you explicitly trigger a search through a configured engine.
            </p>
            <button
              className="gm-btn gm-btn-danger"
              style={{ fontSize: '12px' }}
              onClick={() => {
                localStorage.clear();
                window.location.reload();
              }}
            >
              Clear Local Data
            </button>
          </div>
        </div>
      )}

      {/* API Keys */}
      {activeSection === 'api_keys' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div
            style={{
              padding: '10px 14px',
              background: 'rgba(47,129,247,0.06)',
              border: '1px solid rgba(47,129,247,0.2)',
              borderRadius: '6px',
              fontSize: '13px',
              color: 'var(--gm-text-secondary)',
              lineHeight: 1.5,
            }}
          >
            API keys are stored in environment variables on the backend. Set them in your{' '}
            <code style={{ fontFamily: 'monospace', color: 'var(--gm-accent)' }}>.env</code> file and
            restart the server.
          </div>
          {API_KEY_FIELDS.map((field) => {
            const isMissing = missingEnvVars.has(field.envVar);
            const val = keyValues[field.id] ?? '';
            const isSaved = savedKeys.has(field.id);
            return (
              <div key={field.id} className="gm-card">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                  <Key size={14} color={isMissing ? 'var(--gm-yellow)' : 'var(--gm-teal)'} />
                  <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)', flex: 1 }}>
                    {field.label}
                  </span>
                  {isMissing ? (
                    <span style={{ fontSize: '11px', color: 'var(--gm-yellow)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <AlertCircle size={11} /> Not configured
                    </span>
                  ) : (
                    <span style={{ fontSize: '11px', color: 'var(--gm-teal)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle2 size={11} /> Configured
                    </span>
                  )}
                </div>
                <p style={{ fontSize: '12px', color: 'var(--gm-text-muted)', margin: '0 0 10px', lineHeight: 1.4 }}>
                  {field.description}{' '}
                  <a href={field.docsUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gm-accent)' }}>
                    Docs →
                  </a>
                </p>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <div style={{ flex: 1, position: 'relative' }}>
                    <input
                      className="gm-input"
                      type={showKeys[field.id] ? 'text' : 'password'}
                      placeholder={`Paste ${field.envVar}…`}
                      value={val}
                      onChange={(e) => setKeyValues((prev) => ({ ...prev, [field.id]: e.target.value }))}
                      style={{ paddingRight: '36px', fontFamily: val ? 'monospace' : undefined }}
                    />
                    <button
                      onClick={() => toggleShow(field.id)}
                      style={{
                        position: 'absolute',
                        right: '8px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        color: 'var(--gm-text-muted)',
                        display: 'flex',
                        alignItems: 'center',
                      }}
                    >
                      {showKeys[field.id] ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                  <button
                    className="gm-btn gm-btn-primary"
                    style={{ fontSize: '12px', padding: '6px 12px' }}
                    disabled={!val.trim()}
                    onClick={() => saveKey(field)}
                  >
                    {isSaved ? <CheckCircle2 size={13} /> : <Save size={13} />}
                    {isSaved ? 'Saved!' : 'Save'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Diagnostics */}
      {activeSection === 'diagnostics' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{ fontSize: '13px', color: 'var(--gm-text-muted)' }}>
              Last checked: {health?.timestamp ? new Date(health.timestamp).toLocaleTimeString() : 'n/a'}
            </span>
            <button
              className="gm-btn gm-btn-secondary"
              style={{ fontSize: '12px', padding: '5px 12px' }}
              onClick={() => refetch()}
            >
              <RefreshCw size={13} />
              Refresh
            </button>
          </div>

          {/* Service versions */}
          <div className="gm-card">
            <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)', marginBottom: '12px' }}>
              Service Versions
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {Object.entries(health?.service_versions ?? {}).map(([svc, ver]) => (
                <div key={svc} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                  <span style={{ color: 'var(--gm-text-muted)', textTransform: 'capitalize' }}>{svc}</span>
                  <span style={{ color: 'var(--gm-text-secondary)', fontFamily: 'monospace' }}>{ver}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Engine status */}
          <div className="gm-card">
            <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)', marginBottom: '12px' }}>
              Engine Registry
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {(health?.configured_engines ?? []).map((eng) => (
                <div key={eng} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
                  <CheckCircle2 size={13} color="var(--gm-teal)" />
                  <span style={{ color: 'var(--gm-text-secondary)', flex: 1 }}>{eng}</span>
                  <span style={{ color: 'var(--gm-teal)', fontSize: '11px' }}>online</span>
                </div>
              ))}
              {(health?.unavailable_engines ?? []).map((eng) => (
                <div key={eng.name} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '12px' }}>
                  <AlertCircle size={13} color="var(--gm-red)" style={{ flexShrink: 0, marginTop: '1px' }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ color: 'var(--gm-text-secondary)' }}>{eng.name}</span>
                    <span style={{ color: 'var(--gm-text-muted)', marginLeft: '8px' }}>{eng.reason}</span>
                    {eng.missing_key && (
                      <code style={{ marginLeft: '8px', fontFamily: 'monospace', fontSize: '11px', color: 'var(--gm-yellow)' }}>
                        {eng.missing_key}
                      </code>
                    )}
                  </div>
                </div>
              ))}
              {(health?.configured_engines?.length ?? 0) === 0 &&
                (health?.unavailable_engines?.length ?? 0) === 0 && (
                  <p style={{ fontSize: '13px', color: 'var(--gm-text-muted)', margin: 0 }}>
                    No engine data available.
                  </p>
                )}
            </div>
          </div>

          {/* Missing env vars */}
          {(health?.missing_env_vars?.length ?? 0) > 0 && (
            <div className="gm-card" style={{ borderColor: 'rgba(240,167,50,0.3)' }}>
              <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-yellow)', marginBottom: '10px' }}>
                Missing Environment Variables
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {health!.missing_env_vars.map((v) => (
                  <code
                    key={v}
                    style={{
                      fontFamily: 'monospace',
                      fontSize: '12px',
                      color: 'var(--gm-text-secondary)',
                      padding: '3px 8px',
                      background: 'var(--gm-bg-hover)',
                      borderRadius: '4px',
                      display: 'block',
                    }}
                  >
                    {v}
                  </code>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
