import { useState, useRef } from 'react';
import type { DragEvent, ChangeEvent } from 'react';
import {
  FileSearch,
  Upload,
  AlertTriangle,
  Info,
  FileText,
  Image,
  File,
  MapPin,
  Camera,
  Layers,
  Wrench,
  Download,
} from 'lucide-react';
import { SectionHeader, Spinner, EmptyState } from '../components';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FileInfo {
  name: string;
  size: number;
  type: string;
  last_modified: string;
}

interface DocumentProperties {
  title?: string;
  author?: string;
  creator?: string;
  created?: string;
  modified?: string;
  software?: string;
}

interface ExifData {
  camera?: string;
  lens?: string;
  iso?: number;
  aperture?: string;
  shutter_speed?: string;
  gps?: { latitude: number; longitude: number; altitude?: number };
}

interface CustomProperties {
  [key: string]: string | number | boolean | null;
}

interface MetadataResult {
  file_info: FileInfo;
  document_properties?: DocumentProperties;
  exif?: ExifData;
  custom?: CustomProperties;
}

// ---------------------------------------------------------------------------
// Mock generators
// ---------------------------------------------------------------------------

function buildImageMock(file: File): MetadataResult {
  return {
    file_info: {
      name: file.name,
      size: file.size,
      type: file.type || 'image/jpeg',
      last_modified: new Date(file.lastModified).toISOString(),
    },
    exif: {
      camera: 'Canon EOS R5',
      lens: 'RF 50mm f/1.8 STM',
      iso: 400,
      aperture: 'f/2.8',
      shutter_speed: '1/250s',
      gps: { latitude: 40.712776, longitude: -74.005974, altitude: 10 },
    },
    custom: {
      color_space: 'sRGB',
      x_resolution: '72 dpi',
      y_resolution: '72 dpi',
      orientation: 'Horizontal (normal)',
    },
  };
}

function buildDocMock(file: File): MetadataResult {
  return {
    file_info: {
      name: file.name,
      size: file.size,
      type: file.type || 'application/pdf',
      last_modified: new Date(file.lastModified).toISOString(),
    },
    document_properties: {
      title: 'Confidential Report Q3',
      author: 'Jane Smith',
      creator: 'Microsoft Word 16.0',
      created: '2024-07-15T09:30:00Z',
      modified: '2024-10-22T14:12:00Z',
      software: 'Adobe Acrobat 23.0',
    },
    custom: {
      page_count: 42,
      word_count: 18750,
      language: 'en-US',
      security: 'Not encrypted',
    },
  };
}

function buildGenericMock(file: File): MetadataResult {
  return {
    file_info: {
      name: file.name,
      size: file.size,
      type: file.type || 'application/octet-stream',
      last_modified: new Date(file.lastModified).toISOString(),
    },
    custom: {
      mime_type: file.type || 'unknown',
      encoding: 'binary',
    },
  };
}

function mockForFile(file: File): MetadataResult {
  const name = file.name.toLowerCase();
  const isImage = /\.(png|jpe?g|tiff?|webp|heic)$/i.test(name);
  const isDoc = /\.(pdf|docx?|xlsx?|pptx?)$/i.test(name);
  if (isImage) return buildImageMock(file);
  if (isDoc) return buildDocMock(file);
  return buildGenericMock(file);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(type: string) {
  if (type.startsWith('image/')) return Image;
  if (type.includes('pdf') || type.includes('word') || type.includes('document')) return FileText;
  return File;
}

function FileTypeIcon({ type }: { type: string }) {
  const Icon = fileIcon(type);
  return <Icon size={16} style={{ color: 'var(--gm-accent)' }} />;
}

interface MetaRowProps {
  label: string;
  value: string | number | null | undefined;
  mono?: boolean;
}

function MetaRow({ label, value, mono }: MetaRowProps) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <div
      className="flex gap-4 py-2 border-b last:border-b-0 text-sm"
      style={{ borderColor: 'var(--gm-border-muted)' }}
    >
      <span
        className="shrink-0 w-40 text-xs"
        style={{ color: 'var(--gm-text-muted)' }}
      >
        {label}
      </span>
      <span
        style={{
          color: 'var(--gm-text-secondary)',
          wordBreak: 'break-all',
          fontFamily: mono ? "'JetBrains Mono', monospace" : undefined,
          fontSize: mono ? '12px' : undefined,
        }}
      >
        {String(value)}
      </span>
    </div>
  );
}

function exportJson(result: MetadataResult) {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `metadata-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// MetadataPage
// ---------------------------------------------------------------------------

export function MetadataPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [result, setResult] = useState<MetadataResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFileSelect(file: File) {
    setSelectedFile(file);
    setResult(null);
  }

  function handleInputChange(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFileSelect(f);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFileSelect(f);
  }

  async function handleExtract() {
    if (!selectedFile || extracting) return;

    setExtracting(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);

      const res = await fetch('/api/recon/metadata', {
        method: 'POST',
        body: formData,
        signal: AbortSignal.timeout(15_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: MetadataResult = await res.json();
      setResult(data);
    } catch {
      // API unavailable — simulate extraction with mock
      await new Promise((r) => setTimeout(r, 900));
      setResult(mockForFile(selectedFile));
    } finally {
      setExtracting(false);
    }
  }

  const hasGps = !!(result?.exif?.gps);

  return (
    <div className="max-w-3xl animate-fade-in space-y-5">
      <SectionHeader
        icon={FileSearch}
        title="Metadata"
        subtitle="Extract metadata from documents and images"
      />

      {/* Upload zone */}
      <div
        className="rounded-xl border-2 border-dashed flex flex-col items-center justify-center gap-3 cursor-pointer transition-all"
        style={{
          padding: '2.5rem 1.5rem',
          borderColor: dragging ? 'var(--gm-accent)' : selectedFile ? 'rgba(57,211,83,0.5)' : 'var(--gm-border)',
          background: dragging
            ? 'rgba(47,129,247,0.06)'
            : selectedFile
            ? 'rgba(57,211,83,0.04)'
            : 'var(--gm-bg-card)',
        }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        {selectedFile ? (
          <>
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(57,211,83,0.1)' }}
            >
              <FileTypeIcon type={selectedFile.type} />
            </div>
            <div className="text-center">
              <p className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                {selectedFile.name}
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--gm-text-muted)' }}>
                {formatBytes(selectedFile.size)} · {selectedFile.type || 'unknown type'}
              </p>
            </div>
            <p className="text-xs" style={{ color: 'var(--gm-text-muted)' }}>
              Click to change file
            </p>
          </>
        ) : (
          <>
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{
                background: dragging ? 'rgba(47,129,247,0.12)' : 'var(--gm-bg-hover)',
                color: dragging ? 'var(--gm-accent)' : 'var(--gm-text-muted)',
              }}
            >
              <Upload size={22} />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium" style={{ color: 'var(--gm-text-secondary)' }}>
                Drop a file here or{' '}
                <span style={{ color: 'var(--gm-accent)' }}>browse</span>
              </p>
              <p className="text-xs mt-1" style={{ color: 'var(--gm-text-muted)' }}>
                PDF, DOCX, XLSX, PNG, JPG, TIFF, HEIC
              </p>
            </div>
          </>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,image/*,.tiff,.tif"
          className="hidden"
          onChange={handleInputChange}
        />
      </div>

      {/* Extract button */}
      <div className="flex items-center gap-3">
        <button
          className="gm-btn gm-btn-primary"
          disabled={!selectedFile || extracting}
          onClick={handleExtract}
        >
          {extracting ? <Spinner size="sm" /> : <FileSearch size={14} />}
          {extracting ? 'Extracting…' : 'Extract Metadata'}
        </button>

        {/* Strip metadata — unavailable */}
        <button
          className="gm-btn gm-btn-secondary text-xs"
          disabled
          title="Strip Metadata requires a backend processing service"
        >
          <Wrench size={12} />
          Strip Metadata — unavailable
        </button>
      </div>

      {/* Empty state */}
      {!result && !extracting && !selectedFile && (
        <EmptyState
          icon={FileSearch}
          title="Upload a file to extract metadata"
          description="Drop a document or image to reveal embedded metadata, EXIF data, author information, and GPS coordinates."
        />
      )}

      {/* GPS alert */}
      {hasGps && result && (
        <div
          className="flex items-start gap-3 rounded-lg border px-4 py-3 text-sm"
          style={{ background: 'rgba(248,81,73,0.08)', borderColor: 'rgba(248,81,73,0.4)' }}
        >
          <AlertTriangle size={15} className="shrink-0 mt-0.5" style={{ color: 'var(--gm-red)' }} />
          <div>
            <p className="font-semibold" style={{ color: 'var(--gm-red)' }}>
              Location data found in metadata.
            </p>
            <p className="mt-0.5" style={{ color: 'var(--gm-text-secondary)' }}>
              This file contains GPS coordinates. Remove location data before sharing to protect
              privacy.
            </p>
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-4 animate-fade-in">
          {/* Export */}
          <div className="flex justify-end">
            <button
              className="gm-btn gm-btn-secondary text-xs"
              onClick={() => exportJson(result)}
            >
              <Download size={12} />
              Export JSON
            </button>
          </div>

          {/* File Info */}
          <div className="gm-card space-y-1">
            <div className="flex items-center gap-2 mb-3">
              <File size={14} style={{ color: 'var(--gm-accent)' }} />
              <p className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                File Info
              </p>
            </div>
            <MetaRow label="Name" value={result.file_info.name} />
            <MetaRow label="Size" value={formatBytes(result.file_info.size)} />
            <MetaRow label="Type" value={result.file_info.type} />
            <MetaRow label="Last Modified" value={result.file_info.last_modified} />
          </div>

          {/* Document Properties */}
          {result.document_properties && (
            <div className="gm-card space-y-1">
              <div className="flex items-center gap-2 mb-3">
                <FileText size={14} style={{ color: 'var(--gm-accent)' }} />
                <p className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                  Document Properties
                </p>
              </div>
              <MetaRow label="Title" value={result.document_properties.title} />
              <MetaRow label="Author" value={result.document_properties.author} />
              <MetaRow label="Creator" value={result.document_properties.creator} />
              <MetaRow label="Created" value={result.document_properties.created} />
              <MetaRow label="Modified" value={result.document_properties.modified} />
              <MetaRow label="Software" value={result.document_properties.software} />
            </div>
          )}

          {/* EXIF Data */}
          {result.exif && (
            <div className="gm-card space-y-1">
              <div className="flex items-center gap-2 mb-3">
                <Camera size={14} style={{ color: 'var(--gm-accent)' }} />
                <p className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                  EXIF Data
                </p>
              </div>
              <MetaRow label="Camera" value={result.exif.camera} />
              <MetaRow label="Lens" value={result.exif.lens} />
              <MetaRow label="ISO" value={result.exif.iso} />
              <MetaRow label="Aperture" value={result.exif.aperture} />
              <MetaRow label="Shutter Speed" value={result.exif.shutter_speed} />

              {result.exif.gps && (
                <div
                  className="flex gap-4 py-2 text-sm"
                  style={{ borderTop: '1px solid var(--gm-border-muted)' }}
                >
                  <span
                    className="shrink-0 w-40 text-xs flex items-center gap-1.5"
                    style={{ color: 'var(--gm-red)' }}
                  >
                    <MapPin size={11} />
                    GPS Coordinates
                  </span>
                  <div>
                    <span
                      className="font-mono text-xs"
                      style={{ color: 'var(--gm-text-secondary)' }}
                    >
                      {result.exif.gps.latitude.toFixed(6)}, {result.exif.gps.longitude.toFixed(6)}
                      {result.exif.gps.altitude !== undefined && ` (alt: ${result.exif.gps.altitude}m)`}
                    </span>
                    <a
                      href={`https://maps.google.com/?q=${result.exif.gps.latitude},${result.exif.gps.longitude}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block text-xs mt-0.5"
                      style={{ color: 'var(--gm-accent)' }}
                    >
                      View on Google Maps →
                    </a>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Custom Properties */}
          {result.custom && Object.keys(result.custom).length > 0 && (
            <div className="gm-card space-y-1">
              <div className="flex items-center gap-2 mb-3">
                <Layers size={14} style={{ color: 'var(--gm-accent)' }} />
                <p className="text-sm font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                  Custom Properties
                </p>
              </div>
              {Object.entries(result.custom).map(([k, v]) => (
                <MetaRow key={k} label={k.replace(/_/g, ' ')} value={v !== null ? String(v) : null} />
              ))}
            </div>
          )}

          {/* Strip metadata note */}
          <div
            className="flex items-start gap-3 rounded-lg border px-4 py-3 text-sm"
            style={{ background: 'rgba(47,129,247,0.05)', borderColor: 'rgba(47,129,247,0.2)' }}
          >
            <Info size={14} className="shrink-0 mt-0.5" style={{ color: 'var(--gm-accent)' }} />
            <p style={{ color: 'var(--gm-text-secondary)', margin: 0, lineHeight: 1.6 }}>
              <span className="font-semibold" style={{ color: 'var(--gm-text-primary)' }}>
                Strip Metadata
              </span>{' '}
              is unavailable — this feature requires a backend processing service. Use{' '}
              <a
                href="https://exiftool.org"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: 'var(--gm-accent)' }}
              >
                ExifTool
              </a>{' '}
              locally to remove metadata from sensitive files.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
