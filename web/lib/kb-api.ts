// Knowledge base wizard API client. Kept separate from lib/api.ts so the
// wizard's types stay next to the calls that produce them.

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export interface KbTemplate {
  name: string;
  has_files: boolean;
}

export interface KbPlanStep {
  kind: string;
  description: string;
  path: string | null;
  exists: boolean;
}

export interface KbCreatePlan {
  name: string;
  template: string;
  description: string;
  language: string | null;
  steps: KbPlanStep[];
  warnings: string[];
}

export interface KbProvisionResult {
  created: boolean;
  error: string | null;
  database: string | null;
}

export interface KbCreateResponse {
  dry_run: boolean;
  plan: KbCreatePlan;
  result?: { name: string; written: string[]; database?: KbProvisionResult };
}

export interface KbRegistryRow {
  name: string;
  status: 'registered' | 'unregistered';
  description: string;
  template: string;
  language: string | null;
  created_at: string | null;
  created_by: string | null;
  unregistered_at: string | null;
  unregistered_by: string | null;
  notes: string;
}

export async function apiKbTemplates(): Promise<{ templates: KbTemplate[] }> {
  const res = await fetch(`${API_BASE}/api/kb/templates`);
  if (!res.ok) throw new Error(`Failed to list kb templates: ${res.status}`);
  return res.json();
}

/** Create the database behind an existing kb directory (idempotent). */
export async function apiProvisionKb(name: string): Promise<KbProvisionResult> {
  const res = await fetch(`${API_BASE}/api/kb/${encodeURIComponent(name)}/provision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Failed to provision: ${res.status}`);
  return body as KbProvisionResult;
}

export async function apiCreateKb(input: {
  name: string;
  template: string;
  description: string;
  language: string;
  dry_run: boolean;
  reauth_token?: string;
}): Promise<KbCreateResponse> {
  const res = await fetch(`${API_BASE}/api/kb/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to create kb: ${res.status}`);
  }
  return res.json();
}

export async function apiKbRegistry(): Promise<{ kbs: KbRegistryRow[] }> {
  const res = await fetch(`${API_BASE}/api/kb/registry`);
  if (!res.ok) throw new Error(`Failed to read kb registry: ${res.status}`);
  return res.json();
}

export async function apiUnregisterKb(name: string): Promise<KbRegistryRow> {
  const res = await fetch(`${API_BASE}/api/kb/${encodeURIComponent(name)}/unregister`, {
    method: 'POST',
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to unhook ${name}: ${res.status}`);
  }
  return res.json();
}

export async function apiRegisterKb(name: string): Promise<KbRegistryRow> {
  const res = await fetch(`${API_BASE}/api/kb/${encodeURIComponent(name)}/register`, {
    method: 'POST',
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to register ${name}: ${res.status}`);
  }
  return res.json();
}
