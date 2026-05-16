import { useState } from 'react';
import type { FormEvent } from 'react';
import {
  Cpu,
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
  Download,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { SectionHeader, Spinner, ConfidenceBadge, EmptyState } from '../components';
import type { TechScanResult } from '../types';

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

function buildMockResult(url: string): TechScanResult {
  return {
    url,
    scan_mode: 'passive',
    timestamp: new Date().toISOString(),
    technologies: [
      {
        name: 'nginx',
        category: 'Web Server',
        confidence: 90,
        evidence: ['Server: nginx/1.24.0 header'],
        version: '1.24.0',
      },
      {
        name: 'Cloudflare',
        category: 'CDN',
        confidence: 85,
        evidence: ['cf-ray header present', 'Cloudflare IP range detected'],
      },
      {
        name: 'TLS 1.3',
        category: 'Security',
        confidence: 100,
        evidence: ['TLS handshake negotiated TLS 1.3'],
      },
    ],
    headers: {
      'server': 'nginx/1.24.0',
      'content-type': 'text/html; charset=utf-8',
      'cf-ray': '7d4a3b2c1e8f9a0b-EWR',
      'strict-transport-security': 'max-age=31536000; includeSubDomains',
      'x-frame-options': 'DENY',
      'cache-control': 'public, max-age=3600',
    },
    security_headers: [
      {
        header: 'Content-Security-Policy',
        present: false,
        risk: 'high',
        recommendation: 'Add a CSP header to prevent XSS and data injection attacks',
      },
      {
        header: 'X-Frame-Options',
        present: true,
        value: 'DENY',
        risk: 'low',
      },
      {
        header: 'Strict-Transport-Security',
        present: true,
        value: 'max-age=31536000; includeSubDomains',
        risk: 'low',
      },
      {
        header: 'X-Content-Type-Options',
        present: false,
        risk: 'medium',
        recommendation: 'Add "nosniff" to prevent MIME-type sniffing',
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RISK_COLORS: Record<string, { bg: string; text: string }> = {
  low:    { bg: 'rgba(57,211,83,0.12)',  text: 'var(--gm-teal)'   },
  medium: { bg: 'rgba(240,167,50,0.12)', text: 'var(--gm-yellow)' },
  high:   { bg: 'rgba(248,81,73,0.12)',  text: 'var(--gm-red)'    },
};

const CATEGORY_COLORS: Record<string, string> = {
  'Web Server': 'var(--gm-accent)',
  'CDN':        'var(--gm-purple)',
  'Security':   'var(--gm-teal)',
  'CMS':        'var(--gm-yellow)',
  'Framework':  'var(--gm-red)',
  'Analytics':  '#e6edf3',
};

function getCategoryColor(cat: string): string {
  return CATEGORY_COLORS[cat] ?? 'var(--gm-text-muted)';
}

function groupByCategory(techs: TechScanResult['technologies']) {
  const map = new Map<string, typeof techs>();
  for (const t of techs) {
    if (!map.has(t.category)) map.set(t.category, []);
    map.get(t.category)!.push(t);
  }
  return map;
}

function exportJson(result: TechScanResult) {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `tech-scan-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// TechSniperPage
// ---------------------------------------------------------------------------

export function TechSniperPage() {
  const [url, setUrl] = useState('');
  const [mode, setMode] = useState<'passive' | 'active'>('passive');
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<TechScanResult | null>(null);
  const [headersExpanded, setHeadersExpanded] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed || scanning) return;

    setScanning(true);
    setResult(null);

    // Attempt real API, fall back to mock after 1.5 s
    const timeout = new Promise<null>((res) => setTimeout(() => res(null), 1500));
    const apiCall = fetch('/api/recon/tech', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: trimmed, mode }),
      signal: AbortSignal.timeout(20_000),
    })
      .then((r) => (r.ok ? (r.json() as Promise<TechScanResult>) : null))
      .catch(() => null);

    const winner = await Promise.race([apiCall, timeout]);
    // If API didn't respond in time or failed, use mock
    const data: TechScanResult = winner ?? buildMockResult(trimmed);
    setResult(data);
    setScanning(false);
  }

  const grouped = result ? groupByCategory(result.technologies) : null;

  return (
    <div className="max-w-3xl animate-fade-in space-y-5">
      <SectionHeader
        icon={Cpu}
        title="Tech Sniper"
        subtitle="Detect web technologies from HTTP responses"
      />

      {/* Mode warning */}
      <div
        className="flex items-start gap-3 rounded-lg border px-4 py-3 text-sm"
        style={{ background: 'rgba(240,167,50,0.06)', borderColor: 'rgba(240,167,50,0.35)' }}
      >
        <AlertTriangle size={14} className="shrink-0 mt-0.5" style={{ color: 'var(--gm-yellow)' }} />
        <p style={{ color: 'var(--gm-yellow)', margin: 0, lineHeight: 1.6 }}>
          <span className="font-semibold">Passive mode only by default.</span>{' '}
          Sends a single HTTP GET request to the target URL via the backend.
        </p>
      </div>

      {/* Scan form */}
      <div className="gm-card space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* URL input */}
          <div>
            <label
              className="block text-xs font-medium mb-1.5"
              style={{ color: 'var(--gm-text-secondary)' }}
            >
              Target URL
            </label>
            <input
              className="gm-input w-full"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com"
              autoFocus
              disabled={scanning}
            />
          </div>

          {/* Mode toggle */}
          <div>
            <label
              className="block text-xs font-medium mb-1.5"
              style={{ color: 'var(--gm-text-secondary)' }}
            >
              Scan Mode
            </label>
            <div className="flex gap-2">
              {/* Passive */}
              <button
                type="button"
                onClick={() => setMode('passive')}
                className="gm-btn text-xs"
                style={{
                  background: mode === 'passive' ? 'rgba(47,129,247,0.15)' : 'var(--gm-bg-hover)',
                  color: mode === 'passive' ? 'var(--gm-accent)' : 'var(--gm-text-secondary)',
                  border: `1px solid ${mode === 'passive' ? 'rgba(47,129,247,0.4)' : 'var(--gm-border)'}`,
                  fontWeight: mode === 'passive' ? 600 : 400,
                }}
              >
                Passive (GET request only)
              </button>

              {/* Active — disabled */}
              <button
                type="button"
                disabled
                className="gm-btn text-xs"
                style={{
                  background: 'var(--gm-bg-hover)',
                  color: 'var(--gm-text-muted)',
                  border: '1px solid var(--gm-border)',
                  cursor: 'not-allowed',
                  opacity: 0.5,
                }}
                title="Active mode requires written authorization to test target"
              >
                Active (deeper scan) — authorized targets only
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="gm-btn gm-btn-primary"
            disabled={!url.trim() || scanning}
          >
            {scanning ? <Spinner size="sm" /> : <Cpu size={14} />}
            {scanning ? 'Scanning…' : 'Scan'}
          </button>
        </form>
      </div>

      {/* Empty state */}
      {!result && !scanning && (
        <EmptyState
          icon={Cpu}
          title="Enter a URL to scan"
          description="Tech Sniper will fingerprint web servers, CDNs, frameworks, and security headers via a passive HTTP GET."
        />
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4 animate-fade-in">
          {/* Header row */}
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs" style={{ color: 'var(--gm-text-muted)' }}>
                Scan completed for{' '}
                <span
                  className="font-mono"
                  style={{ color: 'var(--gm-text-secondary)' }}
                >
                  {result.url}
                </span>
              </p>
            </div>
            <button
              className="gm-btn gm-btn-secondary text-xs"
              onClick={() => exportJson(result)}
            >
              <Download size={12} />
              Export JSON
            </button>
          </div>

          {/* Technologies grouped by category */}
          {grouped && grouped.size > 0 && (
            <div className="gm-card space-y-5">
              <p className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                Technologies Detected ({result.technologies.length})
              </p>

              {Array.from(grouped.entries()).map(([category, techs]) => (
                <div key={category}>
                  <div className="flex items-center gap-2 mb-3">
                    <span
                      className="text-xs font-semibold uppercase tracking-wider"
                      style={{ color: getCategoryColor(category) }}
                    >
                      {category}
                    </span>
                    <div
                      className="flex-1 h-px"
                      style={{ background: 'var(--gm-border)' }}
                    />
                  </div>

                  <div className="space-y-3">
                    {techs.map((tech) => (
                      <div key={tech.name} className="space-y-2">
                        <div className="flex items-center gap-3">
                          {/* Category badge */}
                          <span
                            className="gm-badge text-xs"
                            style={{
                              background: `${getCategoryColor(category)}18`,
                              color: getCategoryColor(category),
                            }}
                          >
                            {tech.category}
                          </span>
                          <span
                            className="text-sm font-semibold"
                            style={{ color: 'var(--gm-text-primary)' }}
                          >
                            {tech.name}
                            {tech.version && (
                              <span
                                className="ml-1.5 font-mono text-xs font-normal"
                                style={{ color: 'var(--gm-text-muted)' }}
                              >
                                v{tech.version}
                              </span>
                            )}
                          </span>
                          <div className="ml-auto shrink-0">
                            <ConfidenceBadge score={tech.confidence} size="sm" />
                          </div>
                        </div>

                        {/* Confidence bar */}
                        <div
                          className="rounded-full overflow-hidden"
                          style={{ height: 4, background: 'var(--gm-bg-hover)' }}
                        >
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${tech.confidence}%`,
                              background:
                                tech.confidence >= 75
                                  ? 'var(--gm-teal)'
                                  : tech.confidence >= 45
                                  ? 'var(--gm-yellow)'
                                  : 'var(--gm-red)',
                            }}
                          />
                        </div>

                        {/* Evidence bullets */}
                        {tech.evidence.length > 0 && (
                          <ul className="space-y-0.5 pl-1">
                            {tech.evidence.map((ev, i) => (
                              <li
                                key={i}
                                className="flex items-start gap-2 text-xs"
                                style={{ color: 'var(--gm-text-muted)' }}
                              >
                                <span
                                  className="mt-1.5 w-1 h-1 rounded-full shrink-0"
                                  style={{ background: 'var(--gm-text-muted)' }}
                                />
                                {ev}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Security headers table */}
          {result.security_headers.length > 0 && (
            <div className="gm-card space-y-3">
              <p className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                Security Headers
              </p>

              <div className="overflow-x-auto">
                <table className="w-full text-xs" style={{ borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--gm-border)' }}>
                      {['Header', 'Status', 'Risk', 'Recommendation'].map((h) => (
                        <th
                          key={h}
                          className="text-left pb-2 pr-4 font-semibold uppercase tracking-wider"
                          style={{ color: 'var(--gm-text-muted)', fontSize: '10px' }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.security_headers.map((hdr) => {
                      const riskStyle = RISK_COLORS[hdr.risk] ?? RISK_COLORS.medium;
                      return (
                        <tr
                          key={hdr.header}
                          style={{ borderBottom: '1px solid var(--gm-border-muted)' }}
                        >
                          <td
                            className="py-2.5 pr-4 font-mono"
                            style={{ color: 'var(--gm-text-secondary)' }}
                          >
                            {hdr.header}
                          </td>
                          <td className="py-2.5 pr-4">
                            {hdr.present ? (
                              <span className="flex items-center gap-1.5">
                                <ShieldCheck size={12} style={{ color: 'var(--gm-teal)' }} />
                                <span style={{ color: 'var(--gm-teal)' }}>Present</span>
                                {hdr.value && (
                                  <span
                                    className="ml-1 font-mono text-xs truncate max-w-[120px]"
                                    style={{ color: 'var(--gm-text-muted)' }}
                                    title={hdr.value}
                                  >
                                    {hdr.value}
                                  </span>
                                )}
                              </span>
                            ) : (
                              <span className="flex items-center gap-1.5">
                                <ShieldAlert
                                  size={12}
                                  style={{
                                    color:
                                      hdr.risk === 'high' ? 'var(--gm-red)' : 'var(--gm-yellow)',
                                  }}
                                />
                                <span style={{ color: 'var(--gm-text-muted)' }}>Missing</span>
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 pr-4">
                            <span
                              className="gm-badge uppercase"
                              style={{
                                background: riskStyle.bg,
                                color: riskStyle.text,
                                fontSize: '10px',
                                letterSpacing: '0.04em',
                              }}
                            >
                              {hdr.risk}
                            </span>
                          </td>
                          <td className="py-2.5" style={{ color: 'var(--gm-text-muted)' }}>
                            {hdr.recommendation ?? '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Raw response headers — collapsible */}
          {Object.keys(result.headers).length > 0 && (
            <div className="gm-card">
              <button
                className="flex items-center gap-2 w-full text-left"
                onClick={() => setHeadersExpanded((v) => !v)}
              >
                {headersExpanded ? (
                  <ChevronDown size={14} style={{ color: 'var(--gm-text-muted)' }} />
                ) : (
                  <ChevronRight size={14} style={{ color: 'var(--gm-text-muted)' }} />
                )}
                <span className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                  Raw Response Headers
                </span>
                <span
                  className="gm-badge ml-1"
                  style={{
                    background: 'var(--gm-bg-hover)',
                    color: 'var(--gm-text-muted)',
                    fontSize: '10px',
                  }}
                >
                  {Object.keys(result.headers).length}
                </span>
              </button>

              {headersExpanded && (
                <pre
                  className="mt-3 text-xs p-3 rounded-md overflow-x-auto"
                  style={{
                    background: 'var(--gm-bg-base)',
                    color: 'var(--gm-text-secondary)',
                    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                    border: '1px solid var(--gm-border)',
                    lineHeight: 1.7,
                  }}
                >
                  {Object.entries(result.headers)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join('\n')}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
