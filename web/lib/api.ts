// Central API client for all Softwiki REST endpoints

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export interface StatusResponse {
  workspace: string;
  database_url: string;
  counts: {
    documents: number;
    chunks: number;
    claims: number;
    entities: number;
    relationships: number;
    events: number;
  };
}

export interface GraphEntity {
  id: number;
  name: string;
  type: string | null;
  description: string | null;
}

export interface GraphRelationship {
  id: number;
  source_name: string;
  target_name: string;
  relation_type: string;
  description: string | null;
  confidence: number;
}

export interface GraphResponse {
  entities: GraphEntity[];
  relationships: GraphRelationship[];
}

export interface TimelineEvent {
  id: number;
  title: string;
  description: string | null;
  event_date: string;
  topic: string | null;
  confidence: number;
}

export interface Source {
  citation_num: number;
  title: string;
  url: string | null;
  source_name: string;
  published_at: string;
  page_start: number | null;
  page_end: number | null;
  text: string;
  score: number | null;
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
  mode?: string;
  workflow?: string | null;
}

export interface Workflow {
  name: string;
  description?: string;
  modes?: string[];
  steps?: Record<string, string>;
}

export interface WorkflowsResponse {
  workflows: Record<string, Workflow>;
}

export interface ReportResponse {
  status: string;
  report_id: string;
  report_path: string;
  manifest_path: string;
  manifest: Record<string, unknown>;
}

export interface Document {
  id: number;
  title: string;
  url: string | null;
  source_name: string;
  source_type: string;
  published_at: string;
  collected_at: string;
  author: string | null;
  trust_level: string;
}

export interface Claim {
  id: number;
  document_id: number;
  text: string;
  actor: string | null;
  topic: string | null;
  stance: string | null;
  confidence: number | null;
  published_at: string;
}

export interface WikiBuildResponse {
  status: string;
  filepath: string;
  content: string;
}

export interface WikiPageResponse {
  topic: string;
  content: string;
  filepath: string;
  built_at: string;
}

export interface IngestResult {
  status: string;
  reason?: string;
  document_id?: number;
  title?: string;
  claims_extracted?: number;
}

export interface IndexResult {
  status: string;
  indexed_chunks: number;
}

export interface WorkspaceListResponse {
  workspaces: string[];
  active: string;
}

export interface WorkspaceSwitchResponse {
  status: string;
  workspace: string;
}


export interface AgentTool {
  name: string;
  status: string;
  input: Record<string, unknown>;
  output: string;
}

export interface AgentAskResponse {
  session_id: string;
  answer: string;
  sources: Source[];
  tools: AgentTool[];
  message_id?: string;
  error?: string;
  detail?: string;
}

export interface AgentStatusResponse {
  available: boolean;
  url: string;
  agents?: { name: string; description?: string }[];
  default_agent?: string;
  model?: string;
  mcp?: Record<string, unknown>;
  error?: string;
}

export async function apiAgentStatus(): Promise<AgentStatusResponse> {
  const res = await fetch(`${API_BASE}/api/agent/status`);
  const data = await res.json().catch(() => ({ available: false, url: '', error: 'Invalid response' }));
  return data;
}

export async function apiAgentAsk(
  question: string,
  sessionId?: string,
  agent?: string,
): Promise<AgentAskResponse> {
  const res = await fetch(`${API_BASE}/api/agent/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId || null, agent: agent || null }),
  });
  const text = await res.text();
  let data: AgentAskResponse | null = null;
  try {
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed === 'object' && parsed !== null) {
      data = parsed as AgentAskResponse;
    }
  } catch {
    // Next/nginx may return an HTML timeout page; surface the status and body.
  }
  if (!res.ok) {
    const detail =
      data?.error ||
      data?.detail ||
      text.replace(/<[^>]+>/g, ' ').trim().slice(0, 300) ||
      `HTTP ${res.status}`;
    throw new Error(`Agent request failed (${res.status}): ${detail}`);
  }
  if (!data) throw new Error('Agent returned an empty response');
  return data;
}

export async function apiAgentAbort(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/api/agent/session/${encodeURIComponent(sessionId)}/abort`, {
    method: 'POST',
  });
}

// ─── API Functions ───────────────────────────────────────────────────────────

export async function apiListWorkspaces(): Promise<WorkspaceListResponse> {
  const res = await fetch(`${API_BASE}/api/workspaces`);
  if (!res.ok) throw new Error(`Failed to list workspaces: ${res.status}`);
  return res.json();
}

export async function apiSwitchWorkspace(workspace: string): Promise<WorkspaceSwitchResponse> {
  const res = await fetch(`${API_BASE}/api/workspace`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Switch workspace failed: ${res.status}`);
  }
  return res.json();
}

export async function apiStatus(workspace?: string): Promise<StatusResponse> {
  const url = workspace
    ? `${API_BASE}/api/status?workspace=${encodeURIComponent(workspace)}`
    : `${API_BASE}/api/status`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
  return res.json();
}

export async function apiAsk(question: string, history?: HistoryMessage[], mode?: string, workflow?: string): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history, mode, workflow: workflow || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Ask failed: ${res.status}`);
  }
  return res.json();
}

export async function apiIngestUrl(url: string, source_id?: string): Promise<IngestResult> {
  const res = await fetch(`${API_BASE}/api/ingest/url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, source_id }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Ingest failed: ${res.status}`);
  }
  return res.json();
}

export async function apiIngestFile(file: File, source_id?: string): Promise<IngestResult> {
  const form = new FormData();
  form.append('file', file);
  if (source_id) form.append('source_id', source_id);

  const res = await fetch(`${API_BASE}/api/ingest/file`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Ingest failed: ${res.status}`);
  }
  return res.json();
}

export async function apiRebuildIndex(): Promise<IndexResult> {
  const res = await fetch(`${API_BASE}/api/index`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Index rebuild failed: ${res.status}`);
  }
  return res.json();
}

export async function apiListDocuments(): Promise<Document[]> {
  const res = await fetch(`${API_BASE}/api/documents`);
  if (!res.ok) throw new Error(`Failed to list documents: ${res.status}`);
  return res.json();
}

export async function apiListClaims(): Promise<Claim[]> {
  const res = await fetch(`${API_BASE}/api/claims`);
  if (!res.ok) throw new Error(`Failed to list claims: ${res.status}`);
  return res.json();
}

export async function apiListWikiTopics(): Promise<{ topics: Record<string, unknown> }> {
  const res = await fetch(`${API_BASE}/api/wiki/topics`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to list topics: ${res.status}`);
  return res.json();
}

export async function apiBuildWikiPage(topic: string): Promise<WikiBuildResponse> {
  const res = await fetch(`${API_BASE}/api/wiki/build`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Wiki build failed: ${res.status}`);
  }
  return res.json();
}

export async function apiGetWikiPage(topic: string): Promise<WikiPageResponse> {
  const res = await fetch(`${API_BASE}/api/wiki/page/${encodeURIComponent(topic)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Not found' }));
    throw new Error(err.detail || `Wiki page not found: ${res.status}`);
  }
  return res.json();
}

export async function apiDeleteDocument(id: number): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/api/documents/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Delete failed: ${res.status}`);
  }
  return res.json();
}

export async function apiListGraph(): Promise<GraphResponse> {
  const res = await fetch(`${API_BASE}/api/graph`);
  if (!res.ok) throw new Error(`Failed to list graph: ${res.status}`);
  return res.json();
}

export async function apiListTimeline(): Promise<TimelineEvent[]> {
  const res = await fetch(`${API_BASE}/api/timeline`);
  if (!res.ok) throw new Error(`Failed to list timeline: ${res.status}`);
  return res.json();
}


export async function apiWorkflows(): Promise<WorkflowsResponse> {
  const res = await fetch(`${API_BASE}/api/workflows`);
  if (!res.ok) throw new Error(`Workflows failed: ${res.status}`);
  return res.json();
}

export async function apiReport(
  question: string,
  template: string = 'research-report',
  workflow?: string,
): Promise<ReportResponse> {
  const res = await fetch(`${API_BASE}/api/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, template, workflow: workflow || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Report failed: ${res.status}`);
  }
  return res.json();
}

export function apiReportDownloadUrl(reportId: string): string {
  return `${API_BASE}/api/report/${encodeURIComponent(reportId)}`;
}

// ─── Wiki prompt interventions ───────────────────────────────────────────────

export interface WikiIntervention {
  id: string;
  scope: string;
  text: string;
  enabled: boolean;
  priority: number;
  version: number;
  created_at?: string;
  updated_at?: string;
}

export interface WikiPreviewResult {
  topic: string;
  preview_path?: string;
  content?: string;
  headings?: { level: number; text: string }[];
  citation_count?: number;
  warnings?: string[];
  model?: string | null;
  fallback?: boolean;
  elapsed_ms?: number;
  claims_total?: number;
  claims_used?: number;
  intervention_applied?: boolean;
  intervention_chars?: number;
  error?: string;
}

export interface WikiPreviewResponse {
  run_id: string;
  preview_dir: string;
  results: WikiPreviewResult[];
}

export async function apiListWikiInterventions(): Promise<{ interventions: WikiIntervention[] }> {
  const res = await fetch(`${API_BASE}/api/wiki/interventions`);
  if (!res.ok) throw new Error(`Failed to list interventions: ${res.status}`);
  return res.json();
}

export async function apiSaveWikiIntervention(payload: {
  id?: string;
  scope: string;
  text: string;
  enabled?: boolean;
  priority?: number;
}): Promise<{ status: string; intervention: WikiIntervention }> {
  const res = await fetch(`${API_BASE}/api/wiki/interventions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Save intervention failed: ${res.status}`);
  }
  return res.json();
}

export async function apiDeleteWikiIntervention(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/wiki/interventions/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Delete intervention failed: ${res.status}`);
}

export async function apiPreviewWiki(
  topics: string[],
  intervention?: string,
  includeSaved: boolean = true,
): Promise<WikiPreviewResponse> {
  const res = await fetch(`${API_BASE}/api/wiki/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topics, intervention: intervention || null, include_saved: includeSaved }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Preview failed: ${res.status}`);
  }
  return res.json();
}

export async function apiApplyWiki(
  topics: string[],
  intervention?: string,
  includeSaved: boolean = true,
): Promise<{ status: string; results: WikiPreviewResult[] }> {
  const res = await fetch(`${API_BASE}/api/wiki/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topics, intervention: intervention || null, include_saved: includeSaved }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Apply failed: ${res.status}`);
  }
  return res.json();
}

// ─── Knowledge v2: conflicts / canonical claims ──────────────────────────────

export interface ConflictClaim {
  id: string;
  text: string;
  actor: string;
  topic: string;
  stance: string;
  status: string;
  confidence: number;
  value_normalized: string | null;
  document_id: number | null;
  title: string | null;
  source_name: string | null;
  published_at: string | null;
  revision: string | null;
  page_start: number | null;
  page_end: number | null;
}

export interface KnowledgeConflict {
  id: number;
  type: string;
  severity: string;
  status: string;
  auto_resolved: boolean;
  resolution: string | null;
  created_at: string | null;
  claim_a: ConflictClaim | null;
  claim_b: ConflictClaim | null;
}

export interface KnowledgeMetrics {
  raw_claims: number;
  canonical_claims: number;
  evidence: number;
  canonical_status: Record<string, number>;
  contradictions: Record<string, number>;
  contradictions_by_type: Record<string, number>;
  stale_wiki_artifacts: number;
}

export async function apiListConflicts(status?: string): Promise<{ conflicts: KnowledgeConflict[] }> {
  const url = status
    ? `${API_BASE}/api/conflicts?status=${encodeURIComponent(status)}`
    : `${API_BASE}/api/conflicts`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to list conflicts: ${res.status}`);
  return res.json();
}

export async function apiScanConflicts(topic?: string): Promise<{ canonical_claims: number; pairs: number; created: number }> {
  const res = await fetch(`${API_BASE}/api/conflicts/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic: topic || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Conflict scan failed: ${res.status}`);
  }
  return res.json();
}

export async function apiAdjudicateConflict(
  id: number,
  action: string,
  reason: string = '',
): Promise<{ id: number; status: string; claim_a: string; claim_b: string }> {
  const res = await fetch(`${API_BASE}/api/conflicts/${id}/adjudicate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, actor: 'wiki-admin', reason }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `Adjudication failed: ${res.status}`);
  }
  return res.json();
}

export async function apiKnowledgeMetrics(): Promise<KnowledgeMetrics> {
  const res = await fetch(`${API_BASE}/api/knowledge/metrics`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to load knowledge metrics: ${res.status}`);
  return res.json();
}
