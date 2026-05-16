import { Network, BookOpen, ExternalLink, ChevronRight } from 'lucide-react';

interface OsintCategory {
  name: string;
  color: string;
  tools: Array<{
    name: string;
    description: string;
    url: string;
    mode: 'passive' | 'active' | 'both';
  }>;
}

const OSINT_FRAMEWORK: OsintCategory[] = [
  {
    name: 'Domain & DNS',
    color: 'var(--gm-accent)',
    tools: [
      { name: 'SecurityTrails', description: 'Historical DNS records, subdomains, and IP history', url: 'https://securitytrails.com', mode: 'passive' },
      { name: 'DNSDumpster', description: 'Free domain research and DNS recon tool', url: 'https://dnsdumpster.com', mode: 'passive' },
      { name: 'Shodan', description: 'Internet-connected device search engine', url: 'https://shodan.io', mode: 'passive' },
    ],
  },
  {
    name: 'People & Identities',
    color: 'var(--gm-purple)',
    tools: [
      { name: 'Pipl', description: 'People search engine for public records', url: 'https://pipl.com', mode: 'passive' },
      { name: 'WhatsMyName', description: 'Username enumeration across platforms', url: 'https://whatsmyname.app', mode: 'passive' },
      { name: 'Spokeo', description: 'Public records aggregator', url: 'https://spokeo.com', mode: 'passive' },
    ],
  },
  {
    name: 'Email & Credentials',
    color: 'var(--gm-teal)',
    tools: [
      { name: 'HaveIBeenPwned', description: 'Check email addresses against breach databases', url: 'https://haveibeenpwned.com', mode: 'passive' },
      { name: 'Hunter.io', description: 'Find email addresses for any company', url: 'https://hunter.io', mode: 'passive' },
      { name: 'IntelX', description: 'Intelligence search engine for leaked data', url: 'https://intelx.io', mode: 'passive' },
    ],
  },
  {
    name: 'Social Media',
    color: 'var(--gm-yellow)',
    tools: [
      { name: 'Social Searcher', description: 'Search social media mentions in real-time', url: 'https://social-searcher.com', mode: 'passive' },
      { name: 'Twint', description: 'Twitter intelligence tool (no API needed)', url: 'https://github.com/twintproject/twint', mode: 'passive' },
      { name: 'Maltego', description: 'Visual link analysis and data mining', url: 'https://maltego.com', mode: 'both' },
    ],
  },
  {
    name: 'IP & Network',
    color: 'var(--gm-red)',
    tools: [
      { name: 'Shodan', description: 'Banner grabbing and port scanning (passive mode)', url: 'https://shodan.io', mode: 'passive' },
      { name: 'GreyNoise', description: 'Internet noise analysis and IP context', url: 'https://greynoise.io', mode: 'passive' },
      { name: 'IPinfo', description: 'IP geolocation and ASN lookup', url: 'https://ipinfo.io', mode: 'passive' },
    ],
  },
];

const MODE_COLORS: Record<string, { bg: string; text: string }> = {
  passive: { bg: 'rgba(57,211,83,0.12)', text: 'var(--gm-teal)' },
  active:  { bg: 'rgba(248,81,73,0.12)', text: 'var(--gm-red)' },
  both:    { bg: 'rgba(240,167,50,0.12)', text: 'var(--gm-yellow)' },
};

export function FrameworkPage() {
  return (
    <div style={{ maxWidth: '860px' }}>
      <div style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Network size={20} color="var(--gm-accent)" />
        <div>
          <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--gm-text-primary)' }}>
            OSINT Framework
          </h1>
          <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-muted)' }}>
            Curated intelligence gathering tools and resources
          </p>
        </div>
      </div>

      {/* Legend */}
      <div
        style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          marginBottom: '20px',
          padding: '8px 12px',
          background: 'var(--gm-bg-card)',
          border: '1px solid var(--gm-border)',
          borderRadius: '6px',
          flexWrap: 'wrap',
        }}
      >
        <BookOpen size={13} color="var(--gm-text-muted)" />
        <span style={{ fontSize: '12px', color: 'var(--gm-text-muted)' }}>Mode:</span>
        {Object.entries(MODE_COLORS).map(([mode, col]) => (
          <span
            key={mode}
            style={{
              fontSize: '11px',
              padding: '1px 8px',
              borderRadius: '9999px',
              background: col.bg,
              color: col.text,
              fontWeight: 600,
              textTransform: 'capitalize',
            }}
          >
            {mode}
          </span>
        ))}
      </div>

      {/* Categories */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {OSINT_FRAMEWORK.map((category) => (
          <div key={category.name} className="gm-card">
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '12px',
                paddingBottom: '10px',
                borderBottom: '1px solid var(--gm-border)',
              }}
            >
              <div
                style={{
                  width: '4px',
                  height: '16px',
                  borderRadius: '2px',
                  background: category.color,
                  flexShrink: 0,
                }}
              />
              <span style={{ fontWeight: 700, fontSize: '13px', color: 'var(--gm-text-primary)' }}>
                {category.name}
              </span>
              <span
                style={{
                  fontSize: '11px',
                  color: 'var(--gm-text-muted)',
                  marginLeft: 'auto',
                }}
              >
                {category.tools.length} tools
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {category.tools.map((tool) => {
                const modeStyle = MODE_COLORS[tool.mode] ?? MODE_COLORS.passive;
                return (
                  <div
                    key={tool.name}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      background: 'var(--gm-bg-panel)',
                      border: '1px solid var(--gm-border)',
                      transition: 'border-color 0.15s',
                    }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = category.color; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--gm-border)'; }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--gm-text-primary)' }}>
                          {tool.name}
                        </span>
                        <span
                          style={{
                            fontSize: '10px',
                            padding: '1px 6px',
                            borderRadius: '9999px',
                            background: modeStyle.bg,
                            color: modeStyle.text,
                            fontWeight: 600,
                            textTransform: 'capitalize',
                          }}
                        >
                          {tool.mode}
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: '12px', color: 'var(--gm-text-secondary)' }}>
                        {tool.description}
                      </p>
                    </div>
                    <a
                      href={tool.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '12px',
                        color: 'var(--gm-accent)',
                        textDecoration: 'none',
                        flexShrink: 0,
                        padding: '4px 8px',
                        borderRadius: '4px',
                        background: 'rgba(47,129,247,0.1)',
                        transition: 'background 0.15s',
                      }}
                    >
                      Open <ExternalLink size={11} />
                    </a>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          marginTop: '20px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '12px',
          color: 'var(--gm-text-muted)',
        }}
      >
        <ChevronRight size={13} />
        <span>
          Based on the{' '}
          <a
            href="https://osintframework.com"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'var(--gm-accent)' }}
          >
            OSINT Framework
          </a>{' '}
          by Justin Nordine. Tools link to external sites — use responsibly.
        </span>
      </div>
    </div>
  );
}
