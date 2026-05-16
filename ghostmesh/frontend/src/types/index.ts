export type ServiceStatus = 'online' | 'offline' | 'degraded' | 'unknown';
export type EngineStatus = 'configured' | 'unconfigured' | 'failed' | 'missing_key';
export type ReconMode = 'passive' | 'active';

export interface HealthData {
  ui_status: ServiceStatus;
  api_status: ServiceStatus;
  engine_registry_status: ServiceStatus;
  configured_engines: string[];
  unavailable_engines: UnavailableEngine[];
  missing_env_vars: string[];
  last_query_time: string | null;
  service_versions: Record<string, string>;
  uptime_seconds: number;
  timestamp: string;
}

export interface UnavailableEngine {
  name: string;
  reason: string;
  missing_key?: string;
}

export interface SearchResult {
  id: string;
  title: string;
  snippet: string;
  url: string;
  source_engine: string;
  timestamp?: string;
  confidence: number;
  tags: string[];
  category?: string;
  archived?: boolean;
}

export interface SearchQuery {
  query: string;
  engines: string[];
  mode: ReconMode;
  max_results?: number;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  engines_used: string[];
  engines_failed: string[];
  total: number;
  duration_ms: number;
}

export interface Entity {
  id: string;
  type: 'email' | 'phone' | 'ip' | 'url' | 'domain' | 'username' | 'hash' | 'crypto' | 'name';
  value: string;
  context?: string;
  confidence: number;
  source?: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  confidence?: number;
  source?: string;
  x?: number;
  y?: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
}

export interface PeopleResult {
  id: string;
  name: string;
  confidence: number;
  matched_fields: string[];
  profiles: PublicProfile[];
  last_checked: string;
}

export interface PublicProfile {
  platform: string;
  url: string;
  username?: string;
  bio?: string;
  verified: boolean;
}

export interface TechDetection {
  name: string;
  category: string;
  confidence: number;
  evidence: string[];
  version?: string;
}

export interface TechScanResult {
  url: string;
  technologies: TechDetection[];
  headers: Record<string, string>;
  security_headers: SecurityHeaderCheck[];
  scan_mode: ReconMode;
  timestamp: string;
}

export interface SecurityHeaderCheck {
  header: string;
  present: boolean;
  value?: string;
  risk: 'low' | 'medium' | 'high';
  recommendation?: string;
}

export interface OsintCategory {
  id: string;
  name: string;
  icon: string;
  tools: OsintTool[];
}

export interface OsintTool {
  id: string;
  name: string;
  description: string;
  url: string;
  requires_key: boolean;
  mode: ReconMode;
  status: 'available' | 'key_required' | 'unavailable';
  legal_note?: string;
}

export interface Report {
  id: string;
  title: string;
  type: string;
  created_at: string;
  query?: string;
  result_count?: number;
  size_bytes?: number;
}

export interface Alert {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  action?: string;
  timestamp: string;
  dismissed: boolean;
}
