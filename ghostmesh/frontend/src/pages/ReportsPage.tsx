import { useState, useEffect, useRef } from 'react';
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
} from 'lucide-react';
import { EmptyState } from '../components/EmptyState';
import { SectionHeader } from '../components/SectionHeader';
import type { Report } from '../types';

// ── helpers ────────────────────────────────────────────────────────────────

const LS_KEY = 'gm-reports';

const TYPE_META: Record<string, { label: string; color: string }> = {
  search:     { label: 'Search',     color: 'var(--gm-accent)' },
  people:     { label: 'People',     color: 'var(--gm-teal)' },
  tech_scan:  { label: 'Tech Scan',  color: 'var(--gm-yellow)' },
  extraction: { label: 'Extraction', color: '#c792ea' },
  archive:    { label: 'Archive',    color: 'var(--gm-text-secondary)' },
  graph:      { label: 'Graph',      color: '#82aaff' },
};

function typeIcon(type: string) {
  switch (type) {
    case 'search':     return <Search size={15} />;
    case 'people':     return <Users size={15} />;
    case 'tech_scan':  return <Cpu size={15} />;
    case 'extraction': return <Braces size={15} />;
    default:           return <FileText size={15} />;
  }
}

function typeColor(type: string): string {
  return TYPE_META[type]?.color ?? 'var(--gm-text-muted)';
}

function typeLabel(type: string): string {
  return TYPE_META[type]?.label ?? type;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function loadReports(): Report[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return JSON.parse(raw) as Report[];
  } catch { /* ignore */ }
  // seed demo data on first load
  const demo: Report[] = [
    {
      id: 'r-001',
      title: 'Search Report — "john.doe@example.com"',
      type: 'search',
      created_at: new Date(Date.now() - 3_600_000).toISOString(),
      query: 'john.doe@example.com',
      result_count: 12,
      size_bytes: 14_200,
    },
    {
      id: 'r-002',
      title: 'Tech Scan — example.com',
      type: 'tech_scan',
      created_at: new Date(Date.now() - 86_400_000).toISOString(),
      query: 'https://example.com',
      result_count: 7,
      size_bytes: 3_800,
    },
    {
      id: 'r-003',
      title: 'Entity Extraction — paste #42',
      type: 'extraction',
      created_at: new Date(Date.now() - 172_800_000).toISOString(),
      result_count: 23,
      size_bytes: 8_950,
    },
    {
      id: 'r-004',
      title: 'People Finder — "Jane Smith"',
      type: 'people',
      created_at: new Date(Date.now() - 259_200_000).toISOString(),
      query: 'Jane Smith',
      result_count: 4,
      size_bytes: 5_120,
    },
  ];
  localStorage.setItem(LS_KEY, JSON.stringify(demo));
  return demo;
}

function saveReports(reports: Report[]) {
  localStorage.setItem(LS_KEY, JSON.stringify(reports));
}

type SortMode = 'newest' | 'oldest' | 'type';

// ── component ──────────────────────────────────────────────────────────────

export function ReportsPage() {
  const [reports, setReports] = useState<Report[]>(() => loadReports());
  const [filterText, setFilterText] = useState('');
  const [sort, setSort] = useState<SortMode>('newest');
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const editRef = useRef<HTMLInputElement>(null);

  // persist on change
  useEffect(() => { saveReports(reports); }, [reports]);

  // focus edit input when it mounts
  useEffect(() => {
    if (editingId && editRef.current) editRef.current.focus();
  }, [editingId]);

  // ── actions ──

  function createReport() {
    const newReport: Report = {
      id: `r-${Date.now()}`,
      title: 'New Report',
      type: 'search',
      created_at: new Date().toISOString(),
    };
    setReports((prev) => [newReport, ...prev]);
    setEditingId(newReport.id);
    setEditValue(newReport.title);
  }

  function deleteReport(id: string) {
    setReports((prev) => prev.filter((r) => r.id !== id));
    setConfirmDelete(null);
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

  function startEdit(report: Report) {
    setEditingId(report.id);
    setEditValue(report.title);
  }

  function commitEdit(id: string) {
    const trimmed = editValue.trim();
    if (trimmed) {
      setReports((prev) =>
        prev.map((r) => (r.id === id ? { ...r, title: trimmed } : r)),
      );
    }
    setEditingId(null);
  }

  // ── derived ──

  const typeCounts = reports.reduce<Record<string, number>>((acc, r) => {
    acc[r.type] = (acc[r.type] ?? 0) + 1;
    return acc;
  }, {});

  const filtered = reports
    .filter((r) => {
      if (!filterText.trim()) return true;
      const q = filterText.toLowerCase();
      return (
        r.title.toLowerCase().includes(q) ||
        (r.query ?? '').toLowerCase().includes(q) ||
        r.type.toLowerCase().includes(q)
      );
    })
    .sort((a, b) => {
      if (sort === 'newest') return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      if (sort === 'oldest') return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      return a.type.localeCompare(b.type);
    });

  // ── render ──

  return (
    <div style={{ maxWidth: '820px' }}>
      <SectionHeader
        icon={FileText}
        title="Reports"
        subtitle="Exported search results and investigations"
        actions={
          <button className="gm-btn gm-btn-primary" style={{ fontSize: '13px' }} onClick={createReport}>
            <Plus size={14} />
            New Report
          </button>
        }
      />

      {/* Type stats row */}
      {reports.length > 0 && (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
          <div
            style={{
              padding: '4px 12px',
              borderRadius: '20px',
              background: 'var(--gm-bg-card)',
              border: '1px solid var(--gm-border)',
              fontSize: '12px',
              color: 'var(--gm-text-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
            }}
          >
            <span style={{ color: 'var(--gm-text-primary)', fontWeight: 600 }}>{reports.length}</span>
            total
          </div>
          {Object.entries(typeCounts).map(([type, count]) => (
            <div
              key={type}
              style={{
                padding: '4px 12px',
                borderRadius: '20px',
                background: 'var(--gm-bg-card)',
                border: '1px solid var(--gm-border)',
                fontSize: '12px',
                color: 'var(--gm-text-muted)',
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
              }}
            >
              <span style={{ color: typeColor(type) }}>{typeIcon(type)}</span>
              <span style={{ color: typeColor(type), fontWeight: 600 }}>{count}</span>
              {typeLabel(type)}
            </div>
          ))}
        </div>
      )}

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', alignItems: 'center' }}>
        {/* search filter */}
        <div style={{ position: 'relative', flex: 1 }}>
          <Search
            size={13}
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
            style={{ paddingLeft: '30px' }}
          />
        </div>

        {/* sort */}
        <div style={{ position: 'relative' }}>
          <select
            className="gm-input"
            value={sort}
            onChange={(e) => setSort(e.target.value as SortMode)}
            style={{ paddingRight: '28px', appearance: 'none', cursor: 'pointer', minWidth: '130px' }}
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="type">By type</option>
          </select>
          <ChevronDown
            size={13}
            style={{
              position: 'absolute',
              right: '8px',
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--gm-text-muted)',
              pointerEvents: 'none',
            }}
          />
        </div>
      </div>

      {/* Empty states */}
      {reports.length === 0 && (
        <EmptyState
          icon={FileText}
          title="No saved reports"
          description="Reports are created when you export search results."
          action={{ label: 'Create a report', onClick: createReport }}
        />
      )}

      {reports.length > 0 && filtered.length === 0 && (
        <EmptyState
          icon={Search}
          title="No matching reports"
          description="No reports match your filter."
          action={{ label: 'Clear filter', onClick: () => setFilterText('') }}
        />
      )}

      {/* Report list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {filtered.map((report) => {
          const meta = TYPE_META[report.type];
          const color = meta?.color ?? 'var(--gm-text-muted)';
          const isDeleting = confirmDelete === report.id;
          const isEditing = editingId === report.id;

          return (
            <div
              key={report.id}
              className="gm-card"
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
                padding: '12px 14px',
              }}
            >
              {/* Type icon */}
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '8px',
                  background: `${color}18`,
                  border: `1px solid ${color}30`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  color,
                }}
              >
                {typeIcon(report.type)}
              </div>

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Title row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', flexWrap: 'wrap' }}>
                  {isEditing ? (
                    <input
                      ref={editRef}
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={() => commitEdit(report.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') commitEdit(report.id);
                        if (e.key === 'Escape') setEditingId(null);
                      }}
                      style={{
                        background: 'var(--gm-bg-hover)',
                        border: '1px solid var(--gm-accent)',
                        borderRadius: '4px',
                        color: 'var(--gm-text-primary)',
                        fontSize: '13px',
                        fontWeight: 600,
                        padding: '2px 6px',
                        outline: 'none',
                        flex: 1,
                      }}
                    />
                  ) : (
                    <span
                      title="Double-click to rename"
                      onDoubleClick={() => startEdit(report)}
                      style={{
                        fontWeight: 600,
                        fontSize: '13px',
                        color: 'var(--gm-text-primary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        cursor: 'text',
                        maxWidth: '420px',
                      }}
                    >
                      {report.title}
                    </span>
                  )}

                  {/* Type badge */}
                  <span
                    style={{
                      fontSize: '10px',
                      padding: '2px 7px',
                      borderRadius: '4px',
                      background: `${color}18`,
                      color,
                      fontWeight: 600,
                      flexShrink: 0,
                      border: `1px solid ${color}30`,
                    }}
                  >
                    {typeLabel(report.type)}
                  </span>
                </div>

                {/* Meta row */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    fontSize: '11px',
                    color: 'var(--gm-text-muted)',
                    flexWrap: 'wrap',
                  }}
                >
                  <span>{formatDate(report.created_at)}</span>
                  {report.result_count !== undefined && (
                    <span>{report.result_count} results</span>
                  )}
                  {report.size_bytes !== undefined && (
                    <span>{formatBytes(report.size_bytes)}</span>
                  )}
                  {report.query && (
                    <span
                      style={{
                        fontFamily: 'monospace',
                        fontSize: '10px',
                        color: 'var(--gm-text-secondary)',
                        background: 'var(--gm-bg-hover)',
                        padding: '1px 5px',
                        borderRadius: '3px',
                        maxWidth: '200px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {report.query}
                    </span>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', gap: '5px', flexShrink: 0, alignItems: 'center' }}>
                {isDeleting ? (
                  <>
                    <span style={{ fontSize: '11px', color: 'var(--gm-text-muted)', marginRight: '4px' }}>
                      Delete?
                    </span>
                    <button
                      onClick={() => deleteReport(report.id)}
                      style={{
                        fontSize: '11px',
                        padding: '3px 10px',
                        background: 'var(--gm-red)',
                        color: '#fff',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontWeight: 600,
                      }}
                    >
                      Yes
                    </button>
                    <button
                      onClick={() => setConfirmDelete(null)}
                      style={{
                        fontSize: '11px',
                        padding: '3px 10px',
                        background: 'var(--gm-bg-hover)',
                        color: 'var(--gm-text-secondary)',
                        border: '1px solid var(--gm-border)',
                        borderRadius: '4px',
                        cursor: 'pointer',
                      }}
                    >
                      No
                    </button>
                  </>
                ) : (
                  <>
                    <IconBtn
                      title="Download JSON"
                      hoverColor="var(--gm-accent)"
                      onClick={() => downloadJson(report)}
                    >
                      <FileJson size={13} />
                    </IconBtn>
                    <IconBtn
                      title="Delete report"
                      hoverColor="var(--gm-red)"
                      onClick={() => setConfirmDelete(report.id)}
                    >
                      <Trash2 size={13} />
                    </IconBtn>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── small icon button ──────────────────────────────────────────────────────

function IconBtn({
  children,
  title,
  hoverColor,
  onClick,
}: {
  children: React.ReactNode;
  title: string;
  hoverColor: string;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      title={title}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '28px',
        height: '28px',
        background: 'transparent',
        border: `1px solid ${hovered ? hoverColor : 'var(--gm-border)'}`,
        borderRadius: '4px',
        cursor: 'pointer',
        color: hovered ? hoverColor : 'var(--gm-text-muted)',
        transition: 'border-color 0.15s, color 0.15s',
      }}
    >
      {children}
    </button>
  );
}
