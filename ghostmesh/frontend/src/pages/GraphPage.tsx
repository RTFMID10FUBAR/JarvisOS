import { useState, useRef, useCallback, useEffect } from 'react';
import {
  Network,
  Plus,
  Trash2,
  Download,
  RotateCcw,
  GitMerge,
  Import,
  X,
} from 'lucide-react';
import { SectionHeader, EmptyState } from '../components';
import { exportJSON } from '../utils/export';
import type { GraphNode, GraphEdge, Entity } from '../types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ENTITY_TYPES = [
  'email', 'phone', 'ip', 'url', 'domain', 'username', 'hash', 'name', 'other',
] as const;

type NodeType = (typeof ENTITY_TYPES)[number];

/** Hex colours for each node type */
const TYPE_COLORS: Record<string, string> = {
  email:    '#2f81f7',
  phone:    '#bc8cff',
  ip:       '#39d353',
  url:      '#f0a732',
  domain:   '#f0a732',
  username: '#58a6ff',
  hash:     '#8b949e',
  name:     '#e6edf3',
  other:    '#6e7681',
};

function nodeColor(type: string): string {
  return TYPE_COLORS[type] ?? '#6e7681';
}

const LS_KEY = 'gm-graph-entities';

// ---------------------------------------------------------------------------
// ID generators
// ---------------------------------------------------------------------------

let _nodeSeq = 0;
let _edgeSeq = 0;
function newNodeId(): string { return `n-${Date.now()}-${++_nodeSeq}`; }
function newEdgeId(): string { return `e-${Date.now()}-${++_edgeSeq}`; }

// ---------------------------------------------------------------------------
// Random position helpers
// ---------------------------------------------------------------------------

function randomPos(width = 700, height = 440): { x: number; y: number } {
  return {
    x: 60 + Math.random() * (width - 120),
    y: 60 + Math.random() * (height - 120),
  };
}

// ---------------------------------------------------------------------------
// Modal backdrop
// ---------------------------------------------------------------------------

function Backdrop({ onClose }: { onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        zIndex: 50,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Add Node Modal
// ---------------------------------------------------------------------------

interface AddNodeModalProps {
  onAdd: (label: string, type: string) => void;
  onClose: () => void;
}

function AddNodeModal({ onAdd, onClose }: AddNodeModalProps) {
  const [label, setLabel] = useState('');
  const [type, setType] = useState<string>('domain');

  function handleAdd() {
    if (!label.trim()) return;
    onAdd(label.trim(), type);
    onClose();
  }

  const LABEL_STYLE: React.CSSProperties = {
    display: 'block',
    fontSize: '11px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    color: 'var(--gm-text-muted)',
    marginBottom: '5px',
  };

  return (
    <>
      <Backdrop onClose={onClose} />
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 51,
          width: '360px',
          maxWidth: 'calc(100vw - 32px)',
        }}
      >
        <div className="gm-card" style={{ padding: '24px' }}>
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '20px',
            }}
          >
            <span
              style={{ fontSize: '15px', fontWeight: 700, color: 'var(--gm-text-primary)' }}
            >
              Add Node
            </span>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--gm-text-muted)',
                padding: '2px',
                display: 'flex',
              }}
            >
              <X size={18} />
            </button>
          </div>

          <div style={{ marginBottom: '14px' }}>
            <label style={LABEL_STYLE}>Label</label>
            <input
              className="gm-input"
              type="text"
              placeholder="e.g. admin@example.com"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              autoFocus
            />
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label style={LABEL_STYLE}>Type</label>
            <select
              className="gm-input"
              value={type}
              onChange={(e) => setType(e.target.value)}
              style={{ appearance: 'none' }}
            >
              {ENTITY_TYPES.map((t) => (
                <option key={t} value={t} style={{ background: 'var(--gm-bg-panel)' }}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            <button className="gm-btn gm-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              className="gm-btn gm-btn-primary"
              onClick={handleAdd}
              disabled={!label.trim()}
            >
              <Plus size={14} /> Add Node
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Add Relationship Modal
// ---------------------------------------------------------------------------

interface AddEdgeModalProps {
  nodes: GraphNode[];
  onAdd: (source: string, target: string, label: string) => void;
  onClose: () => void;
}

function AddEdgeModal({ nodes, onAdd, onClose }: AddEdgeModalProps) {
  const [source, setSource] = useState(nodes[0]?.id ?? '');
  const [target, setTarget] = useState(nodes[1]?.id ?? nodes[0]?.id ?? '');
  const [label, setLabel] = useState('related to');

  function handleAdd() {
    if (!source || !target || source === target) return;
    onAdd(source, target, label.trim());
    onClose();
  }

  const LABEL_STYLE: React.CSSProperties = {
    display: 'block',
    fontSize: '11px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    color: 'var(--gm-text-muted)',
    marginBottom: '5px',
  };

  const selectStyle: React.CSSProperties = {
    appearance: 'none',
  };

  return (
    <>
      <Backdrop onClose={onClose} />
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 51,
          width: '400px',
          maxWidth: 'calc(100vw - 32px)',
        }}
      >
        <div className="gm-card" style={{ padding: '24px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '20px',
            }}
          >
            <span
              style={{ fontSize: '15px', fontWeight: 700, color: 'var(--gm-text-primary)' }}
            >
              Add Relationship
            </span>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--gm-text-muted)',
                padding: '2px',
                display: 'flex',
              }}
            >
              <X size={18} />
            </button>
          </div>

          <div style={{ marginBottom: '14px' }}>
            <label style={LABEL_STYLE}>Source Node</label>
            <select
              className="gm-input"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              style={selectStyle}
            >
              {nodes.map((n) => (
                <option key={n.id} value={n.id} style={{ background: 'var(--gm-bg-panel)' }}>
                  [{n.type}] {n.label}
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginBottom: '14px' }}>
            <label style={LABEL_STYLE}>Target Node</label>
            <select
              className="gm-input"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              style={selectStyle}
            >
              {nodes.map((n) => (
                <option key={n.id} value={n.id} style={{ background: 'var(--gm-bg-panel)' }}>
                  [{n.type}] {n.label}
                </option>
              ))}
            </select>
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label style={LABEL_STYLE}>Relationship Label</label>
            <input
              className="gm-input"
              type="text"
              placeholder="e.g. hosts, registered with, resolves to"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            />
          </div>

          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            <button className="gm-btn gm-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              className="gm-btn gm-btn-primary"
              onClick={handleAdd}
              disabled={!source || !target || source === target}
            >
              <GitMerge size={14} /> Add Relationship
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Confirm Reset Modal
// ---------------------------------------------------------------------------

function ConfirmResetModal({ onConfirm, onClose }: { onConfirm: () => void; onClose: () => void }) {
  return (
    <>
      <Backdrop onClose={onClose} />
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 51,
          width: '340px',
          maxWidth: 'calc(100vw - 32px)',
        }}
      >
        <div className="gm-card" style={{ padding: '24px' }}>
          <p
            style={{
              margin: '0 0 8px 0',
              fontSize: '15px',
              fontWeight: 700,
              color: 'var(--gm-text-primary)',
            }}
          >
            Reset Graph?
          </p>
          <p style={{ margin: '0 0 20px 0', fontSize: '13px', color: 'var(--gm-text-secondary)' }}>
            This will remove all nodes and edges. This action cannot be undone.
          </p>
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            <button className="gm-btn gm-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              className="gm-btn gm-btn-danger"
              onClick={() => { onConfirm(); onClose(); }}
            >
              <RotateCcw size={14} /> Reset
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Node Legend
// ---------------------------------------------------------------------------

function NodeLegend() {
  const types: NodeType[] = ['email', 'phone', 'ip', 'url', 'domain', 'username', 'hash', 'name', 'other'];
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '8px',
        padding: '10px 14px',
        borderRadius: '6px',
        background: 'var(--gm-bg-card)',
        border: '1px solid var(--gm-border)',
        marginBottom: '12px',
      }}
    >
      {types.map((t) => (
        <span
          key={t}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            fontSize: '11px',
            color: 'var(--gm-text-secondary)',
          }}
        >
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: nodeColor(t),
              flexShrink: 0,
              display: 'inline-block',
            }}
          />
          {t}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SVG Graph Canvas
// ---------------------------------------------------------------------------

const CANVAS_HEIGHT = 480;
const NODE_RADIUS = 24;

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: string | null;
  onSelectNode: (id: string | null) => void;
  onMoveNode: (id: string, x: number, y: number) => void;
}

function GraphCanvas({ nodes, edges, selectedId, onSelectNode, onMoveNode }: GraphCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const draggingRef = useRef<{ id: string; ox: number; oy: number } | null>(null);

  const handleNodeMouseDown = useCallback(
    (e: React.MouseEvent, nodeId: string) => {
      e.stopPropagation();
      const node = nodes.find((n) => n.id === nodeId);
      if (!node) return;
      const svgRect = svgRef.current?.getBoundingClientRect();
      if (!svgRect) return;
      const mx = e.clientX - svgRect.left;
      const my = e.clientY - svgRect.top;
      draggingRef.current = {
        id: nodeId,
        ox: mx - (node.x ?? 0),
        oy: my - (node.y ?? 0),
      };
      onSelectNode(nodeId);
    },
    [nodes, onSelectNode],
  );

  const handleSvgMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      const d = draggingRef.current;
      if (!d) return;
      const svgRect = svgRef.current?.getBoundingClientRect();
      if (!svgRect) return;
      const mx = e.clientX - svgRect.left;
      const my = e.clientY - svgRect.top;
      onMoveNode(d.id, mx - d.ox, my - d.oy);
    },
    [onMoveNode],
  );

  const handleSvgMouseUp = useCallback(() => {
    draggingRef.current = null;
  }, []);

  return (
    <div
      style={{
        borderRadius: '8px',
        border: '1px solid var(--gm-border)',
        background: 'var(--gm-bg-card)',
        overflow: 'hidden',
        height: `${CANVAS_HEIGHT}px`,
      }}
    >
      <svg
        ref={svgRef}
        width="100%"
        height="100%"
        style={{ cursor: draggingRef.current ? 'grabbing' : 'default', display: 'block' }}
        onMouseMove={handleSvgMouseMove}
        onMouseUp={handleSvgMouseUp}
        onMouseLeave={handleSvgMouseUp}
        onClick={() => onSelectNode(null)}
      >
        {/* Arrow marker def */}
        <defs>
          <marker
            id="arrowhead"
            markerWidth="8"
            markerHeight="6"
            refX="8"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 8 3, 0 6" fill="var(--gm-border)" />
          </marker>
        </defs>

        {/* Edges */}
        {edges.map((edge) => {
          const src = nodes.find((n) => n.id === edge.source);
          const tgt = nodes.find((n) => n.id === edge.target);
          if (!src || !tgt) return null;
          const x1 = src.x ?? 0;
          const y1 = src.y ?? 0;
          const x2 = tgt.x ?? 0;
          const y2 = tgt.y ?? 0;

          // Shorten line to node radius so arrow touches circle edge
          const dx = x2 - x1;
          const dy = y2 - y1;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const ex1 = x1 + (dx / dist) * NODE_RADIUS;
          const ey1 = y1 + (dy / dist) * NODE_RADIUS;
          const ex2 = x2 - (dx / dist) * (NODE_RADIUS + 8); // room for arrowhead

          const mx = (x1 + x2) / 2;
          const my = (y1 + y2) / 2;

          return (
            <g key={edge.id}>
              <line
                x1={ex1}
                y1={ey1}
                x2={ex2}
                y2={ey2}
                stroke="var(--gm-border)"
                strokeWidth={1.5}
                markerEnd="url(#arrowhead)"
              />
              {edge.label && (
                <text
                  x={mx}
                  y={my - 6}
                  textAnchor="middle"
                  fill="var(--gm-text-muted)"
                  fontSize={10}
                  style={{ userSelect: 'none', pointerEvents: 'none' }}
                >
                  {edge.label}
                </text>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map((node) => {
          const cx = node.x ?? 100;
          const cy = node.y ?? 100;
          const color = nodeColor(node.type);
          const selected = selectedId === node.id;
          const shortLabel =
            node.label.length > 16 ? node.label.slice(0, 14) + '…' : node.label;

          return (
            <g
              key={node.id}
              transform={`translate(${cx},${cy})`}
              style={{ cursor: 'grab' }}
              onMouseDown={(e) => handleNodeMouseDown(e, node.id)}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Glow ring when selected */}
              {selected && (
                <circle
                  r={NODE_RADIUS + 5}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                  opacity={0.4}
                />
              )}
              {/* Main circle */}
              <circle
                r={NODE_RADIUS}
                fill={selected ? `${color}22` : 'var(--gm-bg-panel)'}
                stroke={color}
                strokeWidth={selected ? 2.5 : 1.5}
              />
              {/* Type abbreviation inside */}
              <text
                y={5}
                textAnchor="middle"
                fill={color}
                fontSize={10}
                fontWeight={700}
                fontFamily="monospace"
                style={{ userSelect: 'none', pointerEvents: 'none' }}
              >
                {node.type.slice(0, 3).toUpperCase()}
              </text>
              {/* Label below */}
              <text
                y={NODE_RADIUS + 14}
                textAnchor="middle"
                fill="var(--gm-text-secondary)"
                fontSize={10}
                style={{ userSelect: 'none', pointerEvents: 'none' }}
              >
                {shortLabel}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// Extend SVG line to accept ey2 (workaround for shortening calculation)
const ey2 = 0; // will be overridden inside the render

// ---------------------------------------------------------------------------
// GraphPage
// ---------------------------------------------------------------------------

export function GraphPage() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Modal state
  const [showAddNode, setShowAddNode] = useState(false);
  const [showAddEdge, setShowAddEdge] = useState(false);
  const [showReset, setShowReset] = useState(false);

  // Import feedback
  const [importMsg, setImportMsg] = useState<string | null>(null);

  // Dismiss import message after 3s
  useEffect(() => {
    if (!importMsg) return;
    const t = setTimeout(() => setImportMsg(null), 3000);
    return () => clearTimeout(t);
  }, [importMsg]);

  // ---------------------------------------------------------------------------
  // Node operations
  // ---------------------------------------------------------------------------

  function addNode(label: string, type: string) {
    const id = newNodeId();
    setNodes((prev) => [...prev, { id, label, type, ...randomPos() }]);
  }

  function moveNode(id: string, x: number, y: number) {
    setNodes((prev) => prev.map((n) => (n.id === id ? { ...n, x, y } : n)));
  }

  function deleteSelected() {
    if (!selectedId) return;
    setNodes((prev) => prev.filter((n) => n.id !== selectedId));
    setEdges((prev) => prev.filter((e) => e.source !== selectedId && e.target !== selectedId));
    setSelectedId(null);
  }

  // ---------------------------------------------------------------------------
  // Edge operations
  // ---------------------------------------------------------------------------

  function addEdge(source: string, target: string, label: string) {
    const id = newEdgeId();
    setEdges((prev) => [...prev, { id, source, target, label }]);
  }

  // ---------------------------------------------------------------------------
  // Import from Extract
  // ---------------------------------------------------------------------------

  function handleImport() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (!raw) {
        setImportMsg('No entities found in Extract cache.');
        return;
      }
      const stored: Entity[] = JSON.parse(raw);
      const slice = stored.slice(0, 20);
      let added = 0;
      const existingValues = new Set(nodes.map((n) => n.label));
      const newNodes: GraphNode[] = [];
      for (const entity of slice) {
        if (existingValues.has(entity.value)) continue;
        existingValues.add(entity.value);
        newNodes.push({
          id: newNodeId(),
          label: entity.value,
          type: entity.type,
          confidence: entity.confidence,
          ...randomPos(),
        });
        added++;
      }
      setNodes((prev) => [...prev, ...newNodes]);
      setImportMsg(added > 0 ? `Imported ${added} entities from Extract.` : 'No new entities to import.');
    } catch {
      setImportMsg('Failed to read Extract cache.');
    }
  }

  // ---------------------------------------------------------------------------
  // Export / Reset
  // ---------------------------------------------------------------------------

  function handleExport() {
    exportJSON({ nodes, edges }, 'entity-graph');
  }

  function handleReset() {
    setNodes([]);
    setEdges([]);
    setSelectedId(null);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const selectedNode = nodes.find((n) => n.id === selectedId);

  return (
    <div style={{ maxWidth: '100%' }}>
      <SectionHeader
        icon={Network}
        title="Entity Graph"
        subtitle="Visualize and explore entity relationships"
        actions={
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            <button
              className="gm-btn gm-btn-primary"
              style={{ fontSize: '12px', padding: '5px 12px' }}
              onClick={() => setShowAddNode(true)}
            >
              <Plus size={13} /> Add Node
            </button>
            <button
              className="gm-btn gm-btn-secondary"
              style={{ fontSize: '12px', padding: '5px 12px' }}
              disabled={nodes.length < 2}
              onClick={() => setShowAddEdge(true)}
            >
              <GitMerge size={13} /> Add Relationship
            </button>
            <button
              className="gm-btn gm-btn-secondary"
              style={{ fontSize: '12px', padding: '5px 12px' }}
              onClick={handleImport}
            >
              <Import size={13} /> Import from Extract
            </button>
            <button
              className="gm-btn gm-btn-secondary"
              style={{ fontSize: '12px', padding: '5px 12px' }}
              disabled={nodes.length === 0}
              onClick={handleExport}
            >
              <Download size={13} /> Export Graph
            </button>
            <button
              className="gm-btn gm-btn-danger"
              style={{ fontSize: '12px', padding: '5px 12px' }}
              disabled={nodes.length === 0}
              onClick={() => setShowReset(true)}
            >
              <RotateCcw size={13} /> Reset
            </button>
          </div>
        }
      />

      {/* Import feedback */}
      {importMsg && (
        <div
          style={{
            padding: '8px 14px',
            borderRadius: '6px',
            background: 'rgba(47,129,247,0.1)',
            border: '1px solid rgba(47,129,247,0.3)',
            marginBottom: '12px',
            fontSize: '13px',
            color: 'var(--gm-accent)',
          }}
        >
          {importMsg}
        </div>
      )}

      {/* Legend */}
      <NodeLegend />

      {/* Graph or empty state */}
      {nodes.length === 0 ? (
        <EmptyState
          icon={Network}
          title="No entities in graph"
          description="Add nodes manually, import from Entity Extract, or create relationships between entities."
          action={{ label: 'Add Node', onClick: () => setShowAddNode(true) }}
        />
      ) : (
        <>
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            selectedId={selectedId}
            onSelectNode={setSelectedId}
            onMoveNode={moveNode}
          />

          {/* Selected node panel */}
          {selectedNode && (
            <div
              className="gm-card animate-fade-in"
              style={{
                marginTop: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '12px 16px',
              }}
            >
              <div
                style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  background: nodeColor(selectedNode.type),
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <span
                  style={{
                    fontFamily: 'monospace',
                    fontSize: '13px',
                    color: 'var(--gm-text-primary)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    display: 'block',
                  }}
                >
                  {selectedNode.label}
                </span>
                <span style={{ fontSize: '11px', color: 'var(--gm-text-muted)' }}>
                  {selectedNode.type}
                  {selectedNode.confidence != null && ` · ${selectedNode.confidence}% confidence`}
                </span>
              </div>
              <button
                className="gm-btn gm-btn-danger"
                style={{ fontSize: '12px', padding: '4px 10px', flexShrink: 0 }}
                onClick={deleteSelected}
              >
                <Trash2 size={13} /> Delete selected
              </button>
            </div>
          )}

          {/* Graph stats */}
          <p
            style={{
              marginTop: '10px',
              fontSize: '12px',
              color: 'var(--gm-text-muted)',
            }}
          >
            {nodes.length} node{nodes.length !== 1 ? 's' : ''} · {edges.length}{' '}
            edge{edges.length !== 1 ? 's' : ''}
            {' '}· Drag nodes to reposition
          </p>
        </>
      )}

      {/* Modals */}
      {showAddNode && (
        <AddNodeModal onAdd={addNode} onClose={() => setShowAddNode(false)} />
      )}
      {showAddEdge && nodes.length >= 2 && (
        <AddEdgeModal
          nodes={nodes}
          onAdd={addEdge}
          onClose={() => setShowAddEdge(false)}
        />
      )}
      {showReset && (
        <ConfirmResetModal onConfirm={handleReset} onClose={() => setShowReset(false)} />
      )}
    </div>
  );
}
