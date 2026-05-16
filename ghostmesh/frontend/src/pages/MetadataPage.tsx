import { useState, FormEvent, useRef } from 'react';
import { FileSearch, Loader2, Upload, AlertCircle, Info } from 'lucide-react';
import { EmptyState } from '../components/EmptyState';

interface MetadataResult {
  filename: string;
  file_type: string;
  file_size_bytes: number;
  fields: Record<string, string | number | null>;
  gps?: { latitude: number; longitude: number };
}

export function MetadataPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<MetadataResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function processFile(file: File) {
    setIsLoading(true);
    setResult(null);
    setErrorMsg(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/recon/metadata', {
        method: 'POST',
        body: formData,
        signal: AbortSignal.timeout(30_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: MetadataResult = await res.json();
      setResult(data);
    } catch {
      setErrorMsg('Metadata API unavailable — backend not running.');
    } finally {
      setIsLoading(false);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) processFile(file);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processFile(file);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    fileInputRef.current?.click();
  }

  function formatBytes(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  return (
    <div style={{ maxWidth: '800px' }}>
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <FileSearch size={20} color="var(--gm-accent)" />
        <div>
          <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--gm-text-primary)' }}>
            Metadata Extractor
          </h1>
          <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-muted)' }}>
            Extract EXIF and document metadata from images, PDFs, and office files
          </p>
        </div>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? 'var(--gm-accent)' : 'var(--gm-border)'}`,
          borderRadius: '8px',
          padding: '32px',
          textAlign: 'center',
          cursor: 'pointer',
          background: dragging ? 'rgba(47,129,247,0.06)' : 'var(--gm-bg-card)',
          transition: 'border-color 0.15s, background 0.15s',
          marginBottom: '20px',
        }}
      >
        <Upload size={28} color={dragging ? 'var(--gm-accent)' : 'var(--gm-text-muted)'} style={{ margin: '0 auto 10px' }} />
        <p style={{ margin: '0 0 4px', fontSize: '14px', color: 'var(--gm-text-secondary)' }}>
          Drop a file here or <span style={{ color: 'var(--gm-accent)' }}>browse</span>
        </p>
        <p style={{ margin: 0, fontSize: '12px', color: 'var(--gm-text-muted)' }}>
          Supports JPEG, PNG, PDF, DOCX, XLSX and more
        </p>
        <input
          ref={fileInputRef}
          type="file"
          style={{ display: 'none' }}
          onChange={handleFileChange}
          accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx"
        />
      </div>

      {isLoading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--gm-text-muted)', fontSize: '13px' }}>
          <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
          Extracting metadata…
        </div>
      )}

      {errorMsg && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 12px',
            background: 'rgba(248,81,73,0.08)',
            border: '1px solid rgba(248,81,73,0.25)',
            borderRadius: '6px',
            marginBottom: '16px',
          }}
        >
          <AlertCircle size={14} color="var(--gm-red)" />
          <span style={{ fontSize: '13px', color: 'var(--gm-red)' }}>{errorMsg}</span>
        </div>
      )}

      {!result && !isLoading && !errorMsg && (
        <EmptyState
          icon={FileSearch}
          title="Upload a file to extract metadata"
          description="Drag and drop or click the zone above to select a file for metadata analysis."
        />
      )}

      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* File info */}
          <div className="gm-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
              <Info size={15} color="var(--gm-accent)" />
              <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)' }}>
                File Info
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <MetaRow label="Filename" value={result.filename} />
              <MetaRow label="Type" value={result.file_type} />
              <MetaRow label="Size" value={formatBytes(result.file_size_bytes)} />
            </div>
          </div>

          {/* GPS if present */}
          {result.gps && (
            <div
              className="gm-card"
              style={{ borderColor: 'rgba(248,81,73,0.35)' }}
            >
              <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-red)', marginBottom: '8px' }}>
                GPS Coordinates Found
              </div>
              <div style={{ fontFamily: 'monospace', fontSize: '13px', color: 'var(--gm-text-secondary)' }}>
                {result.gps.latitude.toFixed(6)}, {result.gps.longitude.toFixed(6)}
              </div>
              <a
                href={`https://maps.google.com/?q=${result.gps.latitude},${result.gps.longitude}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{ fontSize: '12px', color: 'var(--gm-accent)', marginTop: '6px', display: 'inline-block' }}
              >
                View on Google Maps →
              </a>
            </div>
          )}

          {/* All metadata fields */}
          <div className="gm-card">
            <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)', marginBottom: '12px' }}>
              Metadata Fields ({Object.keys(result.fields).length})
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {Object.entries(result.fields).map(([k, v]) => (
                <div
                  key={k}
                  style={{
                    display: 'flex',
                    gap: '12px',
                    padding: '4px 0',
                    borderBottom: '1px solid var(--gm-border-muted)',
                    fontSize: '12px',
                  }}
                >
                  <span style={{ color: 'var(--gm-text-muted)', minWidth: '160px', flexShrink: 0 }}>{k}</span>
                  <span style={{ color: 'var(--gm-text-secondary)', wordBreak: 'break-all' }}>
                    {v === null ? <em style={{ color: 'var(--gm-text-muted)' }}>null</em> : String(v)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', gap: '12px', fontSize: '12px' }}>
      <span style={{ color: 'var(--gm-text-muted)', minWidth: '80px', flexShrink: 0 }}>{label}</span>
      <span style={{ color: 'var(--gm-text-secondary)' }}>{value}</span>
    </div>
  );
}
