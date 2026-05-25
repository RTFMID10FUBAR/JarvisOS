import { useState } from 'react';
import type { FormEvent } from 'react';
import {
  Users,
  Info,
  ExternalLink,
  Flag,
  Download,
  Search,
  X,
  Clock,
  CheckCircle,
  Globe,
  Code,
  Briefcase,
  MessageSquare,
  Gamepad2,
  Camera,
  Shield,
} from 'lucide-react';
import {
  SectionHeader,
  ConfidenceBadge,
  EmptyState,
  ErrorMessage,
  CopyButton,
  Spinner,
} from '../components';
import { exportJSON } from '../utils/export';
import { apiUrl } from '../utils/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SearchForm {
  firstName: string;
  lastName: string;
  location: string;
  username: string;
  email: string;
  phone: string;
  domain: string;
}

interface ProfileHit {
  platform: string;
  url: string;
  username: string;
  category: string;
  verified: boolean;
  http_status: number;
}

interface PeopleResult {
  id: string;
  name: string;
  confidence: number;
  matched_fields: string[];
  profiles: ProfileHit[];
  sources_checked: string[];
  last_checked: string;
  platforms_found: number;
  platforms_checked: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EMPTY_FORM: SearchForm = {
  firstName: '',
  lastName: '',
  location: '',
  username: '',
  email: '',
  phone: '',
  domain: '',
};

const CAT_ICONS: Record<string, typeof Globe> = {
  code:         Code,
  social:       Users,
  professional: Briefcase,
  messaging:    MessageSquare,
  gaming:       Gamepad2,
  photos:       Camera,
  identity:     Shield,
  video:        Globe,
  streaming:    Globe,
  blog:         Globe,
  tech:         Globe,
  infrastructure: Globe,
};

const LABEL_STYLE: React.CSSProperties = {
  display: 'block',
  fontSize: '11px',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: 'var(--gm-text-muted)',
  marginBottom: '6px',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function callPeopleSearch(form: SearchForm): Promise<PeopleResult> {
  const res = await fetch(apiUrl('/api/people/search'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      first_name: form.firstName,
      last_name: form.lastName,
      username: form.username,
      email: form.email,
      phone: form.phone,
      domain: form.domain,
      location: form.location,
    }),
    signal: AbortSignal.timeout(60_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// ProfileRow
// ---------------------------------------------------------------------------

function ProfileRow({ profile }: { profile: ProfileHit }) {
  const Icon = CAT_ICONS[profile.category] ?? Globe;
  return (
    <div
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
        <Icon size={14} style={{ color: 'var(--gm-accent)', flexShrink: 0 }} />
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--gm-text-primary)', minWidth: '110px', flexShrink: 0 }}>
          {profile.platform}
        </span>
        <span style={{ fontSize: '12px', color: 'var(--gm-text-secondary)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {profile.username}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
        <CopyButton value={profile.url} size={13} />
        <a
          href={profile.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            fontSize: '12px', color: 'var(--gm-accent)', textDecoration: 'none',
            padding: '2px 8px', borderRadius: '4px', background: 'rgba(47,129,247,0.1)',
          }}
        >
          Open <ExternalLink size={11} />
        </a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResultCard
// ---------------------------------------------------------------------------

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
  const [showAll, setShowAll] = useState(false);
  const PREVIEW_COUNT = 5;
  const profiles = showAll ? result.profiles : result.profiles.slice(0, PREVIEW_COUNT);
  const hasMore = result.profiles.length > PREVIEW_COUNT;

  return (
    <div className="gm-card" style={{ padding: '18px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px', marginBottom: '14px' }}>
        <div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--gm-text-primary)', marginBottom: '4px' }}>
            {result.name}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <ConfidenceBadge score={result.confidence} />
            <span style={{ fontSize: '12px', color: 'var(--gm-text-muted)' }}>confidence</span>
            <span style={{ fontSize: '12px', color: 'var(--gm-teal)' }}>
              <CheckCircle size={12} style={{ display: 'inline', marginRight: '3px' }} />
              {result.platforms_found} of {result.platforms_checked} platforms found
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
          <button className="gm-btn gm-btn-secondary" style={{ fontSize: '12px', padding: '5px 10px' }} onClick={onFlag}>
            <Flag size={12} style={{ color: isFlagged ? 'var(--gm-yellow)' : undefined }} />
            {isFlagged ? 'Flagged' : 'Flag false positive'}
          </button>
          <button className="gm-btn gm-btn-secondary" style={{ fontSize: '12px', padding: '5px 10px' }} onClick={onExport}>
            <Download size={12} /> Export
          </button>
        </div>
      </div>

      {/* Matched fields */}
      <div style={{ marginBottom: '14px' }}>
        <div style={{ ...LABEL_STYLE, marginBottom: '8px' }}>Matched Fields</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {result.matched_fields.map(f => (
            <span key={f} style={{ display: 'inline-flex', alignItems: 'center', padding: '2px 10px', borderRadius: '9999px', fontSize: '12px', fontWeight: 600, background: 'rgba(47,129,247,0.15)', color: 'var(--gm-accent)', border: '1px solid rgba(47,129,247,0.25)' }}>
              {f}
            </span>
          ))}
        </div>
      </div>

      {/* Profiles */}
      {result.profiles.length > 0 ? (
        <div style={{ marginBottom: '12px' }}>
          <div style={{ ...LABEL_STYLE, marginBottom: '8px' }}>
            Public Profiles ({result.profiles.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {profiles.map(p => <ProfileRow key={p.platform + p.username} profile={p} />)}
          </div>
          {hasMore && (
            <button
              className="gm-btn gm-btn-secondary"
              style={{ marginTop: '8px', fontSize: '12px', padding: '4px 12px' }}
              onClick={() => setShowAll(v => !v)}
            >
              {showAll ? 'Show less' : `Show ${result.profiles.length - PREVIEW_COUNT} more`}
            </button>
          )}
        </div>
      ) : (
        <p style={{ fontSize: '13px', color: 'var(--gm-text-muted)', marginBottom: '12px' }}>
          No public profiles found for this username on checked platforms.
        </p>
      )}

      {/* Timestamp + sources */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <Clock size={12} style={{ color: 'var(--gm-text-muted)' }} />
          <span style={{ fontSize: '11px', color: 'var(--gm-text-muted)' }}>
            {new Date(result.last_checked).toLocaleString()}
          </span>
        </div>
        {result.sources_checked.length > 0 && (
          <span style={{ fontSize: '11px', color: 'var(--gm-text-muted)' }}>
            Sources: {result.sources_checked.join(', ')}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PeopleFinderPage
// ---------------------------------------------------------------------------

export function PeopleFinderPage() {
  const [form, setForm] = useState<SearchForm>(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [apiOffline, setApiOffline] = useState(false);
  const [results, setResults] = useState<PeopleResult[]>([]);
  const [flagged, setFlagged] = useState<Set<string>>(new Set());

  function handleChange(field: keyof SearchForm, value: string) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const anyFilled = Object.values(form).some(v => v.trim() !== '');
    if (!anyFilled || loading) return;

    setLoading(true);
    setSubmitted(true);
    setApiOffline(false);
    setResults([]);

    try {
      const result = await callPeopleSearch(form);
      setResults([result]);
    } catch {
      setApiOffline(true);
    } finally {
      setLoading(false);
    }
  }

  function handleClear() {
    setForm(EMPTY_FORM);
    setSubmitted(false);
    setResults([]);
    setApiOffline(false);
    setFlagged(new Set());
  }

  function toggleFlag(id: string) {
    setFlagged(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const anyFilled = Object.values(form).some(v => v.trim() !== '');

  return (
    <div style={{ maxWidth: '860px' }}>
      <SectionHeader
        icon={Users}
        title="People Finder"
        subtitle="Search public records and open source profiles"
      />

      {/* Safety disclaimer */}
      <div style={{ display: 'flex', gap: '12px', padding: '14px 16px', borderRadius: '8px', border: '1px solid rgba(47,129,247,0.3)', background: 'rgba(47,129,247,0.08)', marginBottom: '20px' }}>
        <Info size={16} style={{ color: 'var(--gm-accent)', flexShrink: 0, marginTop: '1px' }} />
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-secondary)', lineHeight: '1.5' }}>
          Searches <strong style={{ color: 'var(--gm-text-primary)' }}>publicly available information only</strong> — public profile URLs, certificate transparency records, and open registries. No login bypass or private data access. Authorized research use only.
        </p>
      </div>

      {/* Search form */}
      <form className="gm-card" style={{ marginBottom: '20px', padding: '20px' }} onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '14px', marginBottom: '16px' }}>
          {([
            { field: 'firstName', label: 'First Name',         type: 'text',  placeholder: 'First name' },
            { field: 'lastName',  label: 'Last Name',          type: 'text',  placeholder: 'Last name' },
            { field: 'username',  label: 'Username / Handle',  type: 'text',  placeholder: '@username or handle' },
            { field: 'email',     label: 'Email',              type: 'email', placeholder: 'email@example.com' },
            { field: 'domain',    label: 'Domain',             type: 'text',  placeholder: 'example.com' },
            { field: 'phone',     label: 'Phone',              type: 'tel',   placeholder: '+1 (555) 000-0000' },
            { field: 'location',  label: 'City / State / Country', type: 'text', placeholder: 'City, State or Country' },
          ] as const).map(({ field, label, type, placeholder }) => (
            <div key={field}>
              <label style={LABEL_STYLE}>{label}</label>
              <input
                className="gm-input"
                type={type}
                placeholder={placeholder}
                value={form[field]}
                onChange={e => handleChange(field, e.target.value)}
                autoComplete="off"
              />
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button type="submit" className="gm-btn gm-btn-primary" disabled={!anyFilled || loading}>
            {loading ? <Spinner size="sm" /> : <Search size={15} />}
            {loading ? 'Searching…' : 'Search'}
          </button>
          <button type="button" className="gm-btn gm-btn-secondary" onClick={handleClear} disabled={loading}>
            <X size={15} /> Clear
          </button>
          {loading && (
            <span style={{ fontSize: '12px', color: 'var(--gm-text-muted)' }}>
              Checking {20} platforms…
            </span>
          )}
        </div>
      </form>

      {/* Results */}
      {submitted && !loading && (
        <div style={{ animation: 'fadeIn 0.2s ease-out' }}>
          {apiOffline ? (
            <ErrorMessage
              title="Search API unavailable"
              message="The GhostMesh backend is not running. Start it with ghostmesh/backend/start.sh to enable real username lookups across 20+ platforms."
              onRetry={() => { setSubmitted(false); setApiOffline(false); }}
            />
          ) : results.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No results found"
              description="No public profiles matched your search. Try a different username or broaden your query."
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {results.map(r => (
                <ResultCard
                  key={r.id}
                  result={r}
                  isFlagged={flagged.has(r.id)}
                  onFlag={() => toggleFlag(r.id)}
                  onExport={() => exportJSON(r, `people-result-${r.id}`)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <p style={{ marginTop: '32px', fontSize: '12px', color: 'var(--gm-text-muted)', lineHeight: '1.5' }}>
        Source transparency: all results link to publicly accessible sources. GhostMesh does not store search history externally.
      </p>
    </div>
  );
}
