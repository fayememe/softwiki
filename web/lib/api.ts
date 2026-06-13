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
  text: string;
  score: number;
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
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

export async function apiAsk(question: string, history?: HistoryMessage[], mode?: string): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history, mode }),
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
  const res = await fetch(`${API_BASE}/api/wiki/topics`);
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
