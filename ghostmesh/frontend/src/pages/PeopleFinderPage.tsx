import { useState, FormEvent } from 'react';
import {
  Users,
  Info,
  ExternalLink,
  Flag,
  Download,
  Search,
  X,
  Clock,
} from 'lucide-react';
import {
  SectionHeader,
  ConfidenceBadge,
  EmptyState,
  ErrorMessage,
  CopyButton,
} from '../components';
import type { PeopleResult } from '../types';
import { exportJSON, exportCSV } from '../utils/export';

interface SearchForm {
  firstName: string;
  lastName: string;
  location: string;
  username: string;
  email: string;
  phone: string;
  domain: string;
}

const EMPTY_FORM: SearchForm = {
  firstName: '',
  lastName: '',
  location: '',
  username: '',
  email: '',
  phone: '',
  domain: '',
};

// Demo result to show how results would appear
const DEMO_RESULT: PeopleResult = {
  id: 'demo-001',
  name: 'Alex Morgan',
  confidence: 78,
  matched_fields: ['username', 'email', 'domain'],
  profiles: [
    {
      platform: 'GitHub',
      url: 'https://github.com/alexmorgan',
      username: 'alexmorgan',
      verified: false,
    },
    {
      platform: 'LinkedIn',
      url: 'https://linkedin.com/in/alexmorgan',
      username: 'alexmorgan',
      verified: false,
    },
    {
      platform: 'Twitter/X',
      url: 'https://x.com/alexmorgan',
      username: '@alexmorgan',
      verified: false,
    },
  ],
  last_checked: new Date().toISOString(),
};

export function PeopleFinderPage() {
  const [form, setForm] = useState<SearchForm>(EMPTY_FORM);
  const [submitted, setSubmitted] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [results, setResults] = useState<PeopleResult[]>([]);
  const [flagged, setFlagged] = useState<Set<string>>(new Set());

  function handleChange(field: keyof SearchForm, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const anyFilled = Object.values(form).some((v) => v.trim() !== '');
    if (!anyFilled) return;

    // Simulate: if email contains "error" trigger error state for demo
    if (form.email.includes('error')) {
      setHasError(true);
      setResults([]);
      setSubmitted(true);
      return;
    }

    setHasError(false);
    setSubmitted(true);

    // Produce a demo result when at least one field is filled
    const hasName = form.firstName.trim() || form.lastName.trim();
    const matched: string[] = [];
    if (form.firstName || form.lastName) matched.push('name');
    if (form.username) matched.push('username');
    if (form.email) matched.push('email');
    if (form.phone) matched.push('phone');
    if (form.domain) matched.push('domain');
    if (form.location) matched.push('location');

    const mockResult: PeopleResult = {
      ...DEMO_RESULT,
      name: hasName
        ? `${form.firstName} ${form.lastName}`.trim()
        : DEMO_RESULT.name,
      matched_fields: matched.length > 0 ? matched : DEMO_RESULT.matched_fields,
      confidence: Math.min(40 + matched.length * 12, 95),
      last_checked: new Date().toISOString(),
    };
    setResults([mockResult]);
  }

  function handleClear() {
    setForm(EMPTY_FORM);
    setSubmitted(false);
    setResults([]);
    setHasError(false);
    setFlagged(new Set());
  }

  function handleRetry() {
    setHasError(false);
    setSubmitted(false);
  }

  function toggleFlag(id: string) {
    setFlagged((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleExport(result: PeopleResult) {
    exportJSON(result, `people-result-${result.id}`);
  }

  return (
    <div style={{ maxWidth: '860px' }}>
      <SectionHeader
        icon={Users}
        title="People Finder"
        subtitle="Search public records and open source profiles"
      />

      {/* Safety disclaimer */}
      <div
        style={{
          display: 'flex',
          gap: '12px',
          padding: '14px 16px',
          borderRadius: '8px',
          border: '1px solid rgba(47,129,247,0.3)',
          background: 'rgba(47,129,247,0.08)',
          marginBottom: '20px',
        }}
      >
        <Info size={16} style={{ color: 'var(--gm-accent)', flexShrink: 0, marginTop: '1px' }} />
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-secondary)', lineHeight: '1.5' }}>
          This tool searches <strong style={{ color: 'var(--gm-text-primary)' }}>publicly available information only</strong>.
          Results show public profile links and open records. No private account access.
          Authorized research and investigative use only.
        </p>
      </div>

      {/* Search form */}
      <form className="gm-card" style={{ marginBottom: '20px', padding: '20px' }} onSubmit={handleSubmit}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
            gap: '14px',
            marginBottom: '16px',
          }}
        >
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--gm-text-muted)',
                marginBottom: '6px',
              }}
            >
              First Name
            </label>
            <input
              className="gm-input"
              type="text"
              placeholder="First name"
              value={form.firstName}
              onChange={(e) => handleChange('firstName', e.target.value)}
            />
          </div>

          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--gm-text-muted)',
                marginBottom: '6px',
              }}
            >
              Last Name
            </label>
            <input
              className="gm-input"
              type="text"
              placeholder="Last name"
              value={form.lastName}
              onChange={(e) => handleChange('lastName', e.target.value)}
            />
          </div>

          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--gm-text-muted)',
                marginBottom: '6px',
              }}
            >
              City / State / Country
            </label>
            <input
              className="gm-input"
              type="text"
              placeholder="City, State or Country"
              value={form.location}
              onChange={(e) => handleChange('location', e.target.value)}
            />
          </div>

          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--gm-text-muted)',
                marginBottom: '6px',
              }}
            >
              Username
            </label>
            <input
              className="gm-input"
              type="text"
              placeholder="@username or handle"
              value={form.username}
              onChange={(e) => handleChange('username', e.target.value)}
            />
          </div>

          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--gm-text-muted)',
                marginBottom: '6px',
              }}
            >
              Email
            </label>
            <input
              className="gm-input"
              type="email"
              placeholder="email@example.com"
              value={form.email}
              onChange={(e) => handleChange('email', e.target.value)}
            />
          </div>

          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--gm-text-muted)',
                marginBottom: '6px',
              }}
            >
              Phone
            </label>
            <input
              className="gm-input"
              type="tel"
              placeholder="+1 (555) 000-0000"
              value={form.phone}
              onChange={(e) => handleChange('phone', e.target.value)}
            />
          </div>

          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: 'var(--gm-text-muted)',
                marginBottom: '6px',
              }}
            >
              Domain
            </label>
            <input
              className="gm-input"
              type="text"
              placeholder="example.com"
              value={form.domain}
              onChange={(e) => handleChange('domain', e.target.value)}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            type="submit"
            className="gm-btn gm-btn-primary"
            disabled={!Object.values(form).some((v) => v.trim() !== '')}
          >
            <Search size={15} />
            Search
          </button>
          <button
            type="button"
            className="gm-btn gm-btn-secondary"
            onClick={handleClear}
          >
            <X size={15} />
            Clear
          </button>
        </div>
      </form>

      {/* Results area */}
      {submitted && (
        <div style={{ animation: 'fadeIn 0.2s ease-out' }}>
          {hasError ? (
            <ErrorMessage
              title="Search service unavailable"
              message="The People Finder API is currently unreachable. Check your connection or try again in a moment."
              onRetry={handleRetry}
            />
          ) : results.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No results found"
              description="No public records matched your search criteria. Try broadening your search or using different identifiers."
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {results.map((result) => (
                <ResultCard
                  key={result.id}
                  result={result}
                  isFlagged={flagged.has(result.id)}
                  onFlag={() => toggleFlag(result.id)}
                  onExport={() => handleExport(result)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Footer note */}
      <p
        style={{
          marginTop: '32px',
          fontSize: '12px',
          color: 'var(--gm-text-muted)',
          lineHeight: '1.5',
        }}
      >
        Source transparency: all results link to publicly accessible sources. GhostMesh does not
        store search history externally.
      </p>
    </div>
  );
}

function ResultCard({
  result,
  isFlagged,
  onFlag,
  onExport,
}: {
  result: PeopleResult;
  isFlagged: boolean;
  onFlag: () => void;
  onExport: () => void;
}) {
  return (
    <div className="gm-card" style={{ padding: '18px' }}>
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: '12px',
          marginBottom: '14px',
        }}
      >
        <div>
          <div
            style={{
              fontSize: '16px',
              fontWeight: 700,
              color: 'var(--gm-text-primary)',
              marginBottom: '4px',
            }}
          >
            {result.name}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ConfidenceBadge score={result.confidence} />
            <span style={{ fontSize: '12px', color: 'var(--gm-text-muted)' }}>
              confidence
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className="gm-btn gm-btn-secondary"
            style={{ fontSize: '12px', padding: '5px 10px' }}
            onClick={onFlag}
          >
            <Flag size={12} style={{ color: isFlagged ? 'var(--gm-yellow)' : undefined }} />
            {isFlagged ? 'Flagged' : 'Flag false positive'}
          </button>
          <button
            className="gm-btn gm-btn-secondary"
            style={{ fontSize: '12px', padding: '5px 10px' }}
            onClick={onExport}
          >
            <Download size={12} />
            Export
          </button>
        </div>
      </div>

      {/* Matched fields */}
      <div style={{ marginBottom: '14px' }}>
        <div
          style={{
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--gm-text-muted)',
            marginBottom: '8px',
          }}
        >
          Matched Fields
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {result.matched_fields.map((field) => (
            <span
              key={field}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '2px 10px',
                borderRadius: '9999px',
                fontSize: '12px',
                fontWeight: 600,
                background: 'rgba(47,129,247,0.15)',
                color: 'var(--gm-accent)',
                border: '1px solid rgba(47,129,247,0.25)',
              }}
            >
              {field}
            </span>
          ))}
        </div>
      </div>

      {/* Profiles */}
      <div style={{ marginBottom: '12px' }}>
        <div
          style={{
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--gm-text-muted)',
            marginBottom: '8px',
          }}
        >
          Public Profiles
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {result.profiles.map((profile) => (
            <div
              key={profile.platform}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '12px',
                padding: '8px 10px',
                borderRadius: '6px',
                background: 'var(--gm-bg-panel)',
                border: '1px solid var(--gm-border)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                <span
                  style={{
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--gm-text-primary)',
                    minWidth: '80px',
                    flexShrink: 0,
                  }}
                >
                  {profile.platform}
                </span>
                {profile.username && (
                  <span
                    style={{
                      fontSize: '12px',
                      color: 'var(--gm-text-secondary)',
                      fontFamily: 'monospace',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {profile.username}
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
                <CopyButton value={profile.url} size={13} />
                <a
                  href={profile.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontSize: '12px',
                    color: 'var(--gm-accent)',
                    textDecoration: 'none',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    background: 'rgba(47,129,247,0.1)',
                  }}
                >
                  Open <ExternalLink size={11} />
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Timestamp */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
        <Clock size={12} style={{ color: 'var(--gm-text-muted)' }} />
        <span style={{ fontSize: '11px', color: 'var(--gm-text-muted)' }}>
          Last checked: {new Date(result.last_checked).toLocaleString()}
        </span>
      </div>
    </div>
  );
}
