import { useState } from 'react';
import type { FormEvent } from 'react';
import {
  Braces,
  Network,
  Copy,
  X,
  ChevronDown,
  ChevronRight,
  Link as LinkIcon,
  Clock,
} from 'lucide-react';
import { SectionHeader, EmptyState, CopyButton } from '../components';
import { exportJSON, exportCSV } from '../utils/export';
import type { Entity } from '../types';

// ---------------------------------------------------------------------------
// Entity type configuration
// ---------------------------------------------------------------------------

type ExtractableType =
  | 'email'
  | 'ip'
  | 'url'
  | 'domain'
  | 'username'
  | 'hash'
  | 'crypto'
  | 'name';

interface TypeConfig {
  label: string;
  color: string;
  bg: string;
  icon: string;
}

const TYPE_CONFIG: Record<ExtractableType, TypeConfig> = {
  email:    { label: 'Email',         color: 'var(--gm-accent)',  bg: 'rgba(47,129,247,0.12)',  icon: '@' },
  ip:       { label: 'IP Address',    color: 'var(--gm-teal)',    bg: 'rgba(57,211,83,0.12)',   icon: 'IP' },
  url:      { label: 'URL',           color: '#bc8cff',           bg: 'rgba(188,140,255,0.12)', icon: '://' },
  domain:   { label: 'Domain',        color: 'var(--gm-yellow)',  bg: 'rgba(240,167,50,0.12)',  icon: '.' },
  username: { label: 'Username',      color: 'var(--gm-accent)',  bg: 'rgba(47,129,247,0.12)',  icon: '@' },
  hash:     { label: 'Hash',          color: 'var(--gm-text-secondary)', bg: 'rgba(139,148,158,0.12)', icon: '#' },
  crypto:   { label: 'Crypto Addr.',  color: 'var(--gm-yellow)',  bg: 'rgba(240,167,50,0.12)',  icon: '₿' },
  name:     { label: 'Named Entity',  color: 'var(--gm-text-primary)', bg: 'rgba(230,237,243,0.08)', icon: 'N' },
};

const ALL_TYPES: ExtractableType[] = [
  'email', 'ip', 'url', 'domain', 'username', 'hash', 'crypto', 'name',
];

const TYPE_LABELS: Record<ExtractableType, string> = {
  email:    'Email',
  ip:       'IP Address',
  url:      'URL',
  domain:   'Domain',
  username: 'Username',
  hash:     'Hash',
  crypto:   'Crypto Address',
  name:     'Named Entity (NER)',
};

// ---------------------------------------------------------------------------
// Regex extraction engine
// ---------------------------------------------------------------------------

const REGEXES: Record<ExtractableType, RegExp[]> = {
  email: [/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g],
  ip: [/\b(?:\d{1,3}\.){3}\d{1,3}\b/g],
  url: [/https?:\/\/[^\s<>"{}|\\^`[\]]+/g],
  domain: [/(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}/g],
  hash: [/\b[a-fA-F0-9]{64}\b/g, /\b[a-fA-F0-9]{32}\b/g],
  crypto: [/\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b/g],
  username: [/@[a-zA-Z0-9_]{3,30}/g],
  // NER is not regexable without a model; omit from extraction
  name: [],
};

function extractEntities(
  text: string,
  enabledTypes: Set<ExtractableType>,
): Entity[] {
  const results: Entity[] = [];
  const seen = new Set<string>();

  // Extract URLs first so we can subtract them from domain matches
  const urlMatches = new Set<string>();
  if (enabledTypes.has('url')) {
    const re = new RegExp(REGEXES.url[0].source, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      urlMatches.add(m[0]);
    }
  }

  // Extract emails first so we can subtract them from domain matches
  const emailMatches = new Set<string>();
  if (enabledTypes.has('email')) {
    const re = new RegExp(REGEXES.email[0].source, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      emailMatches.add(m[0]);
    }
  }

  for (const type of ALL_TYPES) {
    if (!enabledTypes.has(type)) continue;
    const patterns = REGEXES[type];
    if (patterns.length === 0) continue;

    for (const pattern of patterns) {
      const re = new RegExp(pattern.source, pattern.flags.includes('g') ? 'g' : 'g');
      let m: RegExpExecArray | null;
      while ((m = re.exec(text)) !== null) {
        const value = m[0];

        // Skip domain matches that are part of a URL or email
        if (type === 'domain') {
          const partOfUrl = [...urlMatches].some((u) => u.includes(value));
          const partOfEmail = [...emailMatches].some((e) => e.includes(value));
          if (partOfUrl || partOfEmail) continue;
        }

        const key = `${type}::${value}`;
        if (seen.has(key)) continue;
        seen.add(key);

        results.push({
          id: `${type}-${results.length}-${Math.random().toString(36).slice(2, 7)}`,
          type: type as Entity['type'],
          value,
          confidence: type === 'email' ? 95 : type === 'ip' ? 90 : type === 'url' ? 92 : 75,
          source: 'client-regex',
        });
      }
    }
  }

  return results;
}

// ---------------------------------------------------------------------------
// localStorage helper
// ---------------------------------------------------------------------------

const LS_KEY = 'gm-graph-entities';

function sendToGraph(entity: Entity) {
  try {
    const existing: Entity[] = JSON.parse(localStorage.getItem(LS_KEY) ?? '[]');
    const alreadyIn = existing.some((e) => e.value === entity.value && e.type === entity.type);
    if (!alreadyIn) {
      existing.push(entity);
      localStorage.setItem(LS_KEY, JSON.stringify(existing.slice(-200)));
    }
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const LABEL_STYLE: React.CSSProperties = {
  display: 'block',
  fontSize: '11px',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: 'var(--gm-text-muted)',
  marginBottom: '6px',
};

interface GroupProps {
  type: ExtractableType;
  entities: Entity[];
}

function EntityGroup({ type, entities }: GroupProps) {
  const [open, setOpen] = useState(true);
  const [sentIds, setSentIds] = useState<Set<string>>(new Set());
  const cfg = TYPE_CONFIG[type];

  function handleSendToGraph(entity: Entity) {
    sendToGraph(entity);
    setSentIds((prev) => new Set(prev).add(entity.id));
  }

  function handleCopyAll() {
    const text = entities.map((e) => e.value).join('\n');
    navigator.clipboard.writeText(text).catch(() => {});
  }

  function handleExportGroup() {
    exportCSV(
      entities.map((e) => ({ type: e.type, value: e.value, confidence: e.confidence })),
      `entities-${type}`,
    );
  }

  return (
    <div className="gm-card" style={{ padding: '14px', marginBottom: '12px' }}>
      {/* Group header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          marginBottom: open ? '12px' : '0',
          cursor: 'pointer',
        }}
        onClick={() => setOpen((o) => !o)}
      >
        <div
          style={{
            width: '28px',
            height: '28px',
            borderRadius: '6px',
            background: cfg.bg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '11px',
            fontWeight: 700,
            color: cfg.color,
            flexShrink: 0,
            fontFamily: 'monospace',
          }}
        >
          {cfg.icon}
        </div>
        <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--gm-text-primary)', flex: 1 }}>
          {cfg.label}
        </span>
        <span
          className="gm-badge"
          style={{
            background: cfg.bg,
            color: cfg.color,
            fontSize: '12px',
            fontWeight: 700,
          }}
        >
          {entities.length}
        </span>

        {/* Actions */}
        <button
          onClick={(e) => { e.stopPropagation(); handleCopyAll(); }}
          className="gm-btn gm-btn-secondary"
          style={{ fontSize: '11px', padding: '3px 8px' }}
          title="Copy all values"
        >
          <Copy size={11} /> Copy all
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); handleExportGroup(); }}
          className="gm-btn gm-btn-secondary"
          style={{ fontSize: '11px', padding: '3px 8px' }}
          title="Export group"
        >
          Export
        </button>

        {open ? (
          <ChevronDown size={15} style={{ color: 'var(--gm-text-muted)', flexShrink: 0 }} />
        ) : (
          <ChevronRight size={15} style={{ color: 'var(--gm-text-muted)', flexShrink: 0 }} />
        )}
      </div>

      {/* Entity rows */}
      {open && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {entities.map((entity) => {
            const sent = sentIds.has(entity.id);
            return (
              <div
                key={entity.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '7px 10px',
                  borderRadius: '6px',
                  background: 'var(--gm-bg-panel)',
                  border: '1px solid var(--gm-border)',
                }}
              >
                <code
                  style={{
                    flex: 1,
                    fontFamily: 'monospace',
                    fontSize: '12px',
                    color: 'var(--gm-text-primary)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {entity.value}
                </code>
                <CopyButton value={entity.value} size={13} />
                <button
                  onClick={() => handleSendToGraph(entity)}
                  className="gm-btn gm-btn-secondary"
                  style={{
                    fontSize: '11px',
                    padding: '3px 8px',
                    color: sent ? 'var(--gm-teal)' : undefined,
                    flexShrink: 0,
                  }}
                  title="Send to Entity Graph"
                >
                  <Network size={11} /> {sent ? 'Sent' : 'Graph'}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ExtractPage
// ---------------------------------------------------------------------------

export function ExtractPage() {
  const [text, setText] = useState('');
  const [urlMode, setUrlMode] = useState(false);
  const [urlInput, setUrlInput] = useState('');

  // Enabled types (all on by default)
  const [enabledTypes, setEnabledTypes] = useState<Set<ExtractableType>>(new Set(ALL_TYPES));

  // Results
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [extractTime, setExtractTime] = useState<number | null>(null);
  const [extracted, setExtracted] = useState(false);

  // ---------------------------------------------------------------------------

  function toggleType(t: ExtractableType) {
    setEnabledTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  function handleExtract(e: FormEvent) {
    e.preventDefault();
    const input = text.trim();
    if (!input && !urlInput.trim()) return;

    const t0 = performance.now();
    const result = extractEntities(urlMode ? urlInput : input, enabledTypes);
    const t1 = performance.now();

    setEntities(result);
    setExtractTime(Math.round(t1 - t0));
    setExtracted(true);
  }

  function handleClear() {
    setText('');
    setUrlInput('');
    setEntities(null);
    setExtractTime(null);
    setExtracted(false);
  }

  function handleExportAll() {
    if (!entities) return;
    exportJSON(entities, 'extracted-entities');
  }

  // Group entities by type
  const grouped: Partial<Record<ExtractableType, Entity[]>> = {};
  if (entities) {
    for (const entity of entities) {
      const t = entity.type as ExtractableType;
      if (!grouped[t]) grouped[t] = [];
      grouped[t]!.push(entity);
    }
  }

  const typeCount = Object.keys(grouped).length;
  const totalCount = entities?.length ?? 0;

  return (
    <div style={{ maxWidth: '860px' }}>
      <SectionHeader
        icon={Braces}
        title="Entity Extract"
        subtitle="Extract structured entities from unstructured text"
      />

      {/* Input card */}
      <form className="gm-card" style={{ marginBottom: '16px', padding: '20px' }} onSubmit={handleExtract}>
        {/* Textarea */}
        <label style={LABEL_STYLE}>Input Text</label>
        <textarea
          className="gm-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste text, URLs, HTML, or paste any content to extract entities..."
          rows={8}
          disabled={urlMode}
          style={{
            resize: 'vertical',
            fontFamily: 'monospace',
            fontSize: '12px',
            lineHeight: 1.6,
            marginBottom: '12px',
            opacity: urlMode ? 0.4 : 1,
          }}
        />

        {/* URL mode toggle */}
        <label
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            cursor: 'pointer',
            marginBottom: urlMode ? '10px' : '16px',
            width: 'fit-content',
          }}
        >
          <div
            style={{
              width: '32px',
              height: '18px',
              borderRadius: '9px',
              background: urlMode ? 'var(--gm-accent)' : 'var(--gm-bg-hover)',
              border: '1px solid var(--gm-border)',
              position: 'relative',
              transition: 'background 0.2s',
              cursor: 'pointer',
            }}
            onClick={() => setUrlMode((v) => !v)}
          >
            <div
              style={{
                position: 'absolute',
                top: '2px',
                left: urlMode ? '14px' : '2px',
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                background: 'white',
                transition: 'left 0.2s',
              }}
            />
          </div>
          <span style={{ fontSize: '13px', color: 'var(--gm-text-secondary)' }}>
            <LinkIcon size={13} style={{ display: 'inline', marginRight: '4px', verticalAlign: 'middle' }} />
            Extract from URL
          </span>
        </label>

        {urlMode && (
          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
            <input
              className="gm-input"
              type="url"
              placeholder="https://example.com/page-to-extract"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
            />
          </div>
        )}

        {/* Entity type filter */}
        <div style={{ marginBottom: '16px' }}>
          <div style={LABEL_STYLE}>Entity Types</div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
              gap: '8px',
            }}
          >
            {ALL_TYPES.map((t) => {
              const checked = enabledTypes.has(t);
              const cfg = TYPE_CONFIG[t];
              return (
                <label
                  key={t}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                    padding: '6px 10px',
                    borderRadius: '6px',
                    border: `1px solid ${checked ? cfg.color : 'var(--gm-border)'}`,
                    background: checked ? cfg.bg : 'transparent',
                    transition: 'all 0.15s',
                  }}
                  onClick={() => toggleType(t)}
                >
                  <div
                    style={{
                      width: '14px',
                      height: '14px',
                      borderRadius: '3px',
                      border: `2px solid ${checked ? cfg.color : 'var(--gm-text-muted)'}`,
                      background: checked ? cfg.color : 'transparent',
                      flexShrink: 0,
                      transition: 'all 0.15s',
                    }}
                  />
                  <span
                    style={{
                      fontSize: '12px',
                      color: checked ? 'var(--gm-text-primary)' : 'var(--gm-text-secondary)',
                      fontWeight: checked ? 500 : 400,
                    }}
                  >
                    {TYPE_LABELS[t]}
                  </span>
                </label>
              );
            })}
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            type="submit"
            className="gm-btn gm-btn-primary"
            disabled={(!text.trim() && !urlInput.trim()) || enabledTypes.size === 0}
          >
            <Braces size={15} />
            Extract
          </button>
          {extracted && (
            <button
              type="button"
              className="gm-btn gm-btn-secondary"
              onClick={handleClear}
            >
              <X size={15} />
              Clear
            </button>
          )}
          {entities && entities.length > 0 && (
            <button
              type="button"
              className="gm-btn gm-btn-secondary"
              onClick={handleExportAll}
              style={{ marginLeft: 'auto' }}
            >
              Export JSON
            </button>
          )}
        </div>
      </form>

      {/* Results */}
      {extracted && (
        <div className="animate-fade-in">
          {entities === null || entities.length === 0 ? (
            <EmptyState
              icon={Braces}
              title="No entities found"
              description="No recognizable entities were detected. Try adjusting the entity type filters or providing more content."
            />
          ) : (
            <>
              {/* Summary bar */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '16px',
                  padding: '10px 14px',
                  borderRadius: '6px',
                  background: 'var(--gm-bg-card)',
                  border: '1px solid var(--gm-border)',
                  marginBottom: '16px',
                  flexWrap: 'wrap',
                }}
              >
                <span style={{ fontSize: '13px', color: 'var(--gm-text-secondary)' }}>
                  Found{' '}
                  <strong style={{ color: 'var(--gm-text-primary)' }}>{totalCount}</strong>{' '}
                  {totalCount === 1 ? 'entity' : 'entities'} across{' '}
                  <strong style={{ color: 'var(--gm-text-primary)' }}>{typeCount}</strong>{' '}
                  {typeCount === 1 ? 'type' : 'types'}
                </span>
                {extractTime !== null && (
                  <span
                    style={{
                      fontSize: '12px',
                      color: 'var(--gm-text-muted)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <Clock size={12} />
                    {extractTime}ms
                  </span>
                )}
              </div>

              {/* Groups */}
              {ALL_TYPES.filter((t) => grouped[t]?.length).map((t) => (
                <EntityGroup key={t} type={t} entities={grouped[t]!} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
