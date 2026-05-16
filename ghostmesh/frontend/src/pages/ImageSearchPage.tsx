import { useState, useRef } from 'react';
import type { DragEvent, ChangeEvent } from 'react';
import {
  Eye,
  Upload,
  Link as LinkIcon,
  X,
  Search,
  ExternalLink,
  AlertTriangle,
  Download,
  Image as ImageIcon,
  CheckSquare,
  Square,
} from 'lucide-react';
import { SectionHeader, ConfidenceBadge, EmptyState } from '../components';
import { exportJSON, exportCSV } from '../utils/export';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ActiveTab = 'upload' | 'url';

interface Engine {
  id: string;
  name: string;
  status: 'redirect' | 'key_required';
  statusNote: string;
}

interface ImageMatch {
  id: string;
  title: string;
  sourceUrl: string;
  pageUrl: string;
  engine: string;
  confidence: number;
  thumbnailColor: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ENGINES: Engine[] = [
  {
    id: 'google',
    name: 'Google Images',
    status: 'redirect',
    statusNote: 'redirect only — no API',
  },
  {
    id: 'tineye',
    name: 'TinEye',
    status: 'key_required',
    statusNote: 'key required',
  },
  {
    id: 'bing',
    name: 'Bing Visual',
    status: 'redirect',
    statusNote: 'redirect only — no API',
  },
];

const MOCK_RESULTS: ImageMatch[] = [
  {
    id: 'r1',
    title: 'Similar image found on example.com',
    sourceUrl: 'https://example.com/images/photo.jpg',
    pageUrl: 'https://example.com/article/2024',
    engine: 'Google Images',
    confidence: 87,
    thumbnailColor: '#1c4a6e',
  },
  {
    id: 'r2',
    title: 'Matching image — news archive',
    sourceUrl: 'https://newsarchive.org/media/img_0042.jpg',
    pageUrl: 'https://newsarchive.org/story/42',
    engine: 'TinEye',
    confidence: 72,
    thumbnailColor: '#2d4a2d',
  },
  {
    id: 'r3',
    title: 'Low confidence visual match',
    sourceUrl: 'https://images.target.org/vis/img.png',
    pageUrl: 'https://target.org/gallery',
    engine: 'Bing Visual',
    confidence: 38,
    thumbnailColor: '#4a3020',
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isValidUrl(s: string): boolean {
  try {
    const u = new URL(s);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}

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
// Sub-components
// ---------------------------------------------------------------------------

function EngineStatusPill({ status, note }: { status: string; note: string }) {
  if (status === 'key_required') {
    return (
      <span
        className="gm-badge"
        style={{
          fontSize: '11px',
          background: 'rgba(240,167,50,0.15)',
          color: 'var(--gm-yellow)',
        }}
      >
        {note}
      </span>
    );
  }
  return (
    <span
      className="gm-badge"
      style={{
        fontSize: '11px',
        background: 'rgba(110,118,129,0.2)',
        color: 'var(--gm-text-muted)',
      }}
    >
      {note}
    </span>
  );
}

function MatchCard({ match }: { match: ImageMatch }) {
  const lowConf = match.confidence < 50;
  return (
    <div className="gm-card" style={{ padding: '14px' }}>
      {lowConf && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 10px',
            borderRadius: '6px',
            background: 'rgba(248,81,73,0.08)',
            border: '1px solid rgba(248,81,73,0.25)',
            marginBottom: '12px',
          }}
        >
          <AlertTriangle size={13} style={{ color: 'var(--gm-red)', flexShrink: 0 }} />
          <span style={{ fontSize: '12px', color: 'var(--gm-red)' }}>
            Low confidence — manual verification recommended
          </span>
        </div>
      )}

      <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
        {/* Mock thumbnail */}
        <div
          style={{
            width: '64px',
            height: '64px',
            borderRadius: '6px',
            flexShrink: 0,
            background: match.thumbnailColor,
            border: '1px solid var(--gm-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <ImageIcon size={20} style={{ color: 'rgba(255,255,255,0.3)' }} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: '14px',
              fontWeight: 600,
              color: 'var(--gm-text-primary)',
              marginBottom: '4px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {match.title}
          </div>

          <div
            style={{
              fontSize: '12px',
              color: 'var(--gm-text-muted)',
              fontFamily: 'monospace',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              marginBottom: '10px',
            }}
          >
            {match.sourceUrl}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <ConfidenceBadge score={match.confidence} size="sm" />
            <span
              className="gm-badge"
              style={{
                background: 'var(--gm-bg-hover)',
                color: 'var(--gm-text-secondary)',
                fontSize: '11px',
              }}
            >
              {match.engine}
            </span>
            <a
              href={match.pageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="gm-btn gm-btn-secondary"
              style={{ fontSize: '12px', padding: '3px 10px', textDecoration: 'none' }}
            >
              Open source <ExternalLink size={11} />
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ImageSearchPage
// ---------------------------------------------------------------------------

export function ImageSearchPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('upload');

  // Upload tab state
  const [file, setFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // URL tab state
  const [imageUrl, setImageUrl] = useState('');
  const [urlPreviewSrc, setUrlPreviewSrc] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);

  // Engine selection
  const [selectedEngines, setSelectedEngines] = useState<Set<string>>(
    new Set(ENGINES.map((e) => e.id)),
  );

  // Results
  const [results, setResults] = useState<ImageMatch[] | null>(null);
  const [searched, setSearched] = useState(false);

  // ---------------------------------------------------------------------------
  // File handling
  // ---------------------------------------------------------------------------

  function acceptFile(f: File) {
    if (!f.type.startsWith('image/')) return;
    setFile(f);
    const reader = new FileReader();
    reader.onload = (ev) => setFilePreview(ev.target?.result as string);
    reader.readAsDataURL(f);
  }

  function handleFileInput(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) acceptFile(f);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) acceptFile(f);
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(true);
  }

  function clearFile() {
    setFile(null);
    setFilePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  // ---------------------------------------------------------------------------
  // URL handling
  // ---------------------------------------------------------------------------

  function handleLoadPreview() {
    if (!imageUrl.trim()) return;
    if (!isValidUrl(imageUrl)) {
      setUrlError('Invalid URL — must start with http:// or https://');
      setUrlPreviewSrc(null);
      return;
    }
    setUrlError(null);
    setUrlPreviewSrc(imageUrl);
  }

  // ---------------------------------------------------------------------------
  // Engine toggle
  // ---------------------------------------------------------------------------

  function toggleEngine(id: string) {
    setSelectedEngines((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // ---------------------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------------------

  const hasImage = activeTab === 'upload' ? !!file : !!urlPreviewSrc;
  const canSearch = hasImage && selectedEngines.size > 0;

  function getDisabledReason(): string | null {
    if (!hasImage)
      return activeTab === 'upload'
        ? 'Upload or drop an image first'
        : 'Load a valid image URL first';
    if (selectedEngines.size === 0) return 'Select at least one search engine';
    return null;
  }

  function handleSearch() {
    if (!canSearch) return;
    setSearched(true);
    setResults(MOCK_RESULTS);
  }

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------

  function handleExportJSON() {
    if (!results) return;
    exportJSON(results, 'image-search-results');
  }

  function handleExportCSV() {
    if (!results) return;
    exportCSV(
      results.map((r) => ({
        title: r.title,
        source_url: r.sourceUrl,
        page_url: r.pageUrl,
        engine: r.engine,
        confidence: r.confidence,
      })),
      'image-search-results',
    );
  }

  const disabledReason = getDisabledReason();

  return (
    <div style={{ maxWidth: '860px' }}>
      <SectionHeader
        icon={Eye}
        title="Image Search"
        subtitle="Reverse image search using public engines"
      />

      {/* Upload / URL card */}
      <div className="gm-card" style={{ marginBottom: '16px', padding: '20px' }}>
        {/* Tab bar */}
        <div
          style={{
            display: 'flex',
            gap: '4px',
            marginBottom: '20px',
            background: 'var(--gm-bg-panel)',
            borderRadius: '6px',
            padding: '3px',
            width: 'fit-content',
          }}
        >
          {(['upload', 'url'] as ActiveTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="gm-btn"
              style={{
                padding: '5px 14px',
                fontSize: '13px',
                background: activeTab === tab ? 'var(--gm-bg-card)' : 'transparent',
                color: activeTab === tab ? 'var(--gm-text-primary)' : 'var(--gm-text-muted)',
                border:
                  activeTab === tab ? '1px solid var(--gm-border)' : '1px solid transparent',
                borderRadius: '4px',
              }}
            >
              {tab === 'upload' ? (
                <>
                  <Upload size={13} /> Upload Image
                </>
              ) : (
                <>
                  <LinkIcon size={13} /> Search by URL
                </>
              )}
            </button>
          ))}
        </div>

        {/* Upload tab */}
        {activeTab === 'upload' && (
          <>
            {!file ? (
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={() => setIsDragging(false)}
                onClick={() => fileInputRef.current?.click()}
                style={{
                  border: `2px dashed ${isDragging ? 'var(--gm-accent)' : 'var(--gm-border)'}`,
                  borderRadius: '8px',
                  padding: '40px 20px',
                  textAlign: 'center',
                  cursor: 'pointer',
                  background: isDragging ? 'rgba(47,129,247,0.05)' : 'var(--gm-bg-panel)',
                  transition: 'border-color 0.15s, background 0.15s',
                }}
              >
                <Upload
                  size={28}
                  style={{ color: 'var(--gm-text-muted)', marginBottom: '10px' }}
                />
                <p
                  style={{
                    margin: '0 0 4px 0',
                    fontSize: '14px',
                    color: 'var(--gm-text-primary)',
                  }}
                >
                  Drop image here or click to browse
                </p>
                <p style={{ margin: 0, fontSize: '12px', color: 'var(--gm-text-muted)' }}>
                  Accepts PNG, JPG, WEBP, GIF
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  style={{ display: 'none' }}
                  onChange={handleFileInput}
                />
              </div>
            ) : (
              <div
                style={{
                  display: 'flex',
                  gap: '16px',
                  alignItems: 'flex-start',
                  padding: '14px',
                  borderRadius: '8px',
                  background: 'var(--gm-bg-panel)',
                  border: '1px solid var(--gm-border)',
                }}
              >
                {filePreview && (
                  <img
                    src={filePreview}
                    alt="Preview"
                    style={{
                      width: '80px',
                      height: '80px',
                      objectFit: 'cover',
                      borderRadius: '6px',
                      border: '1px solid var(--gm-border)',
                      flexShrink: 0,
                    }}
                  />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p
                    style={{
                      margin: '0 0 2px 0',
                      fontSize: '14px',
                      fontWeight: 600,
                      color: 'var(--gm-text-primary)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {file.name}
                  </p>
                  <p style={{ margin: 0, fontSize: '12px', color: 'var(--gm-text-muted)' }}>
                    {formatBytes(file.size)} · {file.type}
                  </p>
                </div>
                <button
                  onClick={clearFile}
                  className="gm-btn gm-btn-secondary"
                  style={{ fontSize: '12px', padding: '4px 10px', flexShrink: 0 }}
                >
                  <X size={13} /> Remove
                </button>
              </div>
            )}
          </>
        )}

        {/* URL tab */}
        {activeTab === 'url' && (
          <>
            <label style={LABEL_STYLE}>Image URL</label>
            <div
              style={{
                display: 'flex',
                gap: '8px',
                marginBottom: urlPreviewSrc ? '16px' : '0',
              }}
            >
              <input
                className="gm-input"
                type="url"
                placeholder="https://example.com/image.jpg"
                value={imageUrl}
                onChange={(e) => {
                  setImageUrl(e.target.value);
                  setUrlError(null);
                }}
                onKeyDown={(e) => e.key === 'Enter' && handleLoadPreview()}
              />
              <button
                className="gm-btn gm-btn-secondary"
                onClick={handleLoadPreview}
                style={{ flexShrink: 0 }}
              >
                Load Preview
              </button>
            </div>

            {urlError && (
              <p style={{ fontSize: '12px', color: 'var(--gm-red)', margin: '6px 0 0 0' }}>
                {urlError}
              </p>
            )}

            {urlPreviewSrc && (
              <div
                style={{
                  padding: '12px',
                  borderRadius: '8px',
                  background: 'var(--gm-bg-panel)',
                  border: '1px solid var(--gm-border)',
                  display: 'flex',
                  gap: '12px',
                  alignItems: 'center',
                }}
              >
                <img
                  src={urlPreviewSrc}
                  alt="URL preview"
                  style={{
                    maxWidth: '120px',
                    maxHeight: '80px',
                    objectFit: 'contain',
                    borderRadius: '4px',
                    border: '1px solid var(--gm-border)',
                  }}
                  onError={() => setUrlError('Could not load image from this URL')}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p
                    style={{
                      margin: '0 0 4px 0',
                      fontSize: '12px',
                      color: 'var(--gm-text-primary)',
                      fontFamily: 'monospace',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {urlPreviewSrc}
                  </p>
                  <p style={{ margin: 0, fontSize: '11px', color: 'var(--gm-text-muted)' }}>
                    Image loaded from URL
                  </p>
                </div>
                <button
                  onClick={() => {
                    setUrlPreviewSrc(null);
                    setImageUrl('');
                  }}
                  className="gm-btn gm-btn-secondary"
                  style={{ fontSize: '12px', padding: '4px 10px', flexShrink: 0 }}
                >
                  <X size={13} /> Clear
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Engine selection */}
      <div className="gm-card" style={{ marginBottom: '16px', padding: '20px' }}>
        <div style={{ ...LABEL_STYLE, marginBottom: '12px' }}>Search Engines</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {ENGINES.map((engine) => {
            const checked = selectedEngines.has(engine.id);
            return (
              <label
                key={engine.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  cursor: 'pointer',
                }}
              >
                <button
                  type="button"
                  onClick={() => toggleEngine(engine.id)}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    cursor: 'pointer',
                    color: checked ? 'var(--gm-accent)' : 'var(--gm-text-muted)',
                    display: 'flex',
                    alignItems: 'center',
                  }}
                  aria-checked={checked}
                  role="checkbox"
                  aria-label={`Toggle ${engine.name}`}
                >
                  {checked ? <CheckSquare size={17} /> : <Square size={17} />}
                </button>
                <span
                  style={{ fontSize: '14px', color: 'var(--gm-text-primary)', fontWeight: 500 }}
                >
                  {engine.name}
                </span>
                <EngineStatusPill status={engine.status} note={engine.statusNote} />
              </label>
            );
          })}
        </div>
      </div>

      {/* Search action */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
        <button
          className="gm-btn gm-btn-primary"
          disabled={!canSearch}
          onClick={handleSearch}
          title={disabledReason ?? ''}
        >
          <Search size={15} />
          Search
        </button>
        {disabledReason && (
          <span style={{ fontSize: '12px', color: 'var(--gm-text-muted)' }}>
            {disabledReason}
          </span>
        )}
      </div>

      {/* Results */}
      {searched && results !== null && (
        <div className="animate-fade-in">
          {results.length === 0 ? (
            <EmptyState
              icon={ImageIcon}
              title="No matches found"
              description="No visually similar images were found across the selected engines."
            />
          ) : (
            <>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '12px',
                  gap: '12px',
                }}
              >
                <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-secondary)' }}>
                  {results.length} match{results.length !== 1 ? 'es' : ''} found
                </p>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    className="gm-btn gm-btn-secondary"
                    style={{ fontSize: '12px', padding: '5px 10px' }}
                    onClick={handleExportJSON}
                  >
                    <Download size={13} /> JSON
                  </button>
                  <button
                    className="gm-btn gm-btn-secondary"
                    style={{ fontSize: '12px', padding: '5px 10px' }}
                    onClick={handleExportCSV}
                  >
                    <Download size={13} /> CSV
                  </button>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {results.map((match) => (
                  <MatchCard key={match.id} match={match} />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Disclaimer */}
      <p
        style={{
          marginTop: '32px',
          fontSize: '12px',
          color: 'var(--gm-text-muted)',
          lineHeight: '1.5',
        }}
      >
        Face recognition is not performed. This tool finds visually similar images using public
        search engines.
      </p>
    </div>
  );
}
