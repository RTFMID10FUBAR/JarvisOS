import { useState, useEffect, useRef, useCallback } from 'react';
import {
  FileText,
  Search,
  Users,
  Cpu,
  Braces,
  Trash2,
  FileJson,
  Plus,
  ChevronDown,
  CheckCircle,
} from 'lucide-react';
import { EmptyState } from '../components/EmptyState';
import { SectionHeader } from '../components/SectionHeader';
import { cn } from '../utils/cn';
import type { Report } from '../types';

// Seed some demo reports
const DEMO_REPORTS: Report[] = [
  {
    id: 'r-001',
    title: 'Search Report — "john.doe@example.com"',
    type: 'search',
    created_at: new Date(Date.now() - 3600_000).toISOString(),
    query: 'john.doe@example.com',
    result_count: 12,
    size_bytes: 14200,
  },
  {
    id: 'r-002',
    title: 'Tech Scan — example.com',
    type: 'tech_scan',
    created_at: new Date(Date.now() - 86400_000).toISOString(),
    query: 'https://example.com',
    result_count: 7,
    size_bytes: 3800,
  },
  {
    id: 'r-003',
    title: 'Entity Extraction — paste #42',
    type: 'extraction',
    created_at: new Date(Date.now() - 172800_000).toISOString(),
    query: undefined,
    result_count: 23,
    size_bytes: 8950,
  },
];

const TYPE_LABELS: Record<string, string> = {
  search:     'Search',
  tech_scan:  'Tech Scan',
  extraction: 'Extraction',
  archive:    'Archive',
  people:     'People',
  graph:      'Graph',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function ReportsPage() {
  const [reports, setReports] = useState<Report[]>(DEMO_REPORTS);
  const [filterText, setFilterText] = useState('');

  function deleteReport(id: string) {
    setReports((prev) => prev.filter((r) => r.id !== id));
  }

  function downloadJson(report: Report) {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ghostmesh-report-${report.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadCsv(report: Report) {
    const headers = ['id', 'title', 'type', 'created_at', 'result_count', 'size_bytes'];
    const row = headers.map((h) => JSON.stringify((report as Record<string, unknown>)[h] ?? '')).join(',');
    const csv = [headers.join(','), row].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ghostmesh-report-${report.id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const filtered = reports.filter(
    (r) =>
      filterText.trim() === '' ||
      r.title.toLowerCase().includes(filterText.toLowerCase()) ||
      (r.query ?? '').toLowerCase().includes(filterText.toLowerCase()),
  );

  return (
    <div style={{ maxWidth: '800px' }}>
      <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <FileText size={20} color="var(--gm-accent)" />
        <div style={{ flex: 1 }}>
          <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: 'var(--gm-text-primary)' }}>
            Reports
          </h1>
          <p style={{ margin: 0, fontSize: '13px', color: 'var(--gm-text-muted)' }}>
            Saved investigation reports and exports
          </p>
        </div>
        <span
          style={{
            fontSize: '12px',
            color: 'var(--gm-text-muted)',
            fontFamily: 'monospace',
          }}
        >
          {reports.length} saved
        </span>
      </div>

      {/* Filter */}
      <div style={{ position: 'relative', marginBottom: '16px' }}>
        <Search
          size={14}
          style={{
            position: 'absolute',
            left: '10px',
            top: '50%',
            transform: 'translateY(-50%)',
            color: 'var(--gm-text-muted)',
            pointerEvents: 'none',
          }}
        />
        <input
          className="gm-input"
          type="text"
          placeholder="Filter reports…"
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          style={{ paddingLeft: '32px' }}
        />
      </div>

      {reports.length === 0 && (
        <EmptyState
          icon={FileText}
          title="No reports saved"
          description="Reports are saved automatically when you export results from Search, Recon, or Entity pages."
        />
      )}

      {reports.length > 0 && filtered.length === 0 && (
        <EmptyState
          icon={Search}
          title="No matching reports"
          description="No reports match your filter. Try a different search term."
          action={{ label: 'Clear filter', onClick: () => setFilterText('') }}
        />
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {filtered.map((report) => (
          <div
            key={report.id}
            className="gm-card"
            style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}
          >
            {/* Type icon */}
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '8px',
                background: 'rgba(47,129,247,0.12)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <FileText size={16} color="var(--gm-accent)" />
            </div>

            {/* Content */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '4px' }}>
                <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--gm-text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {report.title}
                </span>
                <span
                  style={{
                    fontSize: '10px',
                    padding: '1px 6px',
                    borderRadius: '4px',
                    background: 'rgba(47,129,247,0.1)',
                    color: 'var(--gm-accent)',
                    fontWeight: 600,
                    flexShrink: 0,
                  }}
                >
                  {TYPE_LABELS[report.type] ?? report.type}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '11px', color: 'var(--gm-text-muted)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={11} />
                  {timeAgo(report.created_at)}
                </span>
                {report.result_count !== undefined && (
                  <span>{report.result_count} results</span>
                )}
                {report.size_bytes !== undefined && (
                  <span>{formatBytes(report.size_bytes)}</span>
                )}
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
              <button
                title="Download JSON"
                onClick={() => downloadJson(report)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '30px',
                  height: '30px',
                  background: 'transparent',
                  border: '1px solid var(--gm-border)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  color: 'var(--gm-text-muted)',
                  transition: 'border-color 0.15s, color 0.15s',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-accent)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--gm-accent)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-text-muted)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--gm-border)';
                }}
              >
                <FileCode2 size={13} />
              </button>
              <button
                title="Download CSV"
                onClick={() => downloadCsv(report)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '30px',
                  height: '30px',
                  background: 'transparent',
                  border: '1px solid var(--gm-border)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  color: 'var(--gm-text-muted)',
                  transition: 'border-color 0.15s, color 0.15s',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-teal)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--gm-teal)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-text-muted)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--gm-border)';
                }}
              >
                <Download size={13} />
              </button>
              <button
                title="Delete report"
                onClick={() => deleteReport(report.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '30px',
                  height: '30px',
                  background: 'transparent',
                  border: '1px solid var(--gm-border)',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  color: 'var(--gm-text-muted)',
                  transition: 'border-color 0.15s, color 0.15s',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-red)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--gm-red)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--gm-text-muted)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--gm-border)';
                }}
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
