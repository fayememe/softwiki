'use client';

/**
 * Admin panel: users (role overrides, kb_scope, pending approvals) and the
 * audit log. Backed by /api/admin/*, which is fail-closed on role — a non-admin
 * gets 403 and this panel shows the reason instead of pretending to work.
 *
 * Design: docs/02-design/auth-oidc.md
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import styles from './AdminPanel.module.css';

interface AdminUser {
  issuer: string;
  subject: string;
  display_name?: string;
  role_override?: string | null;
  resolved_role: string;
  pending: boolean;
  kb_scope?: unknown;
  visible_kbs: string[];
  kb_scope_empty: boolean;
  is_active: boolean;
  last_seen?: string;
}

interface AuditRecord {
  ts?: string;
  action?: string;
  actor?: string;
  target?: string;
  result?: string;
  source_ip?: string;
  detail?: string;
}

const ROLES = ['wiki-study', 'wiki-work', 'wiki-manage', 'wiki-admin'];

const ROLE_LABEL: Record<string, string> = {
  'wiki-study': 'Study',
  'wiki-work': 'Work',
  'wiki-manage': 'Manage',
  'wiki-admin': 'Admin',
};

async function jfetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: 'no-store', ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export default function AdminPanel() {
  const [tab, setTab] = useState<'users' | 'audit'>('users');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [allKbs, setAllKbs] = useState<string[]>([]);
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [filter, setFilter] = useState('');

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const d = await jfetch<{ users: AdminUser[]; all_kbs: string[] }>('/api/admin/users');
      setUsers(d.users || []);
      setAllKbs(d.all_kbs || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadAudit = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const d = await jfetch<{ records: AuditRecord[] }>('/api/admin/audit?limit=200');
      setRecords(d.records || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load audit log');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'users') void loadUsers();
    else void loadAudit();
  }, [tab, loadUsers, loadAudit]);

  const patchUser = useCallback(async (u: AdminUser, patch: Record<string, unknown>) => {
    const key = `${u.issuer}:${u.subject}`;
    setBusy(key);
    setError('');
    setNotice('');
    try {
      await jfetch(`/api/admin/users/${encodeURIComponent(u.issuer)}/${encodeURIComponent(u.subject)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      setNotice(`Updated ${u.display_name || u.subject}.`);
      await loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed');
    } finally {
      setBusy(null);
    }
  }, [loadUsers]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) =>
      `${u.display_name || ''} ${u.subject} ${u.issuer} ${u.resolved_role}`.toLowerCase().includes(q),
    );
  }, [users, filter]);

  const pendingCount = users.filter((u) => u.pending).length;

  return (
    <div className={styles.panel}>
      <header className={styles.head}>
        <h2 className={styles.title}>Administration</h2>
        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${tab === 'users' ? styles.tabActive : ''}`}
            onClick={() => setTab('users')}
          >
            Users {pendingCount > 0 && <span className={styles.pendingDot}>{pendingCount}</span>}
          </button>
          <button
            className={`${styles.tab} ${tab === 'audit' ? styles.tabActive : ''}`}
            onClick={() => setTab('audit')}
          >
            Audit log
          </button>
        </div>
        {tab === 'users' && (
          <input
            className={styles.search}
            type="search"
            placeholder="Filter users…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        )}
      </header>

      {error && <div className={styles.error}>{error}</div>}
      {notice && <div className={styles.notice}>{notice}</div>}

      {tab === 'users' && (
        <div className={styles.body}>
          {loading && <div className={styles.empty}>Loading users…</div>}
          {!loading && visible.length === 0 && (
            <div className={styles.empty}>
              No users yet. External identities appear here after their first sign-in
              through the configured provider.
            </div>
          )}
          {!loading && visible.length > 0 && (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.colUser}>User</th>
                  <th className={styles.colRole}>Role</th>
                  <th className={styles.colKb}>Knowledge bases</th>
                  <th className={styles.colStatus}>Status</th>
                  <th className={styles.colActions}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((u) => {
                  const key = `${u.issuer}:${u.subject}`;
                  return (
                    <tr key={key} className={u.pending ? styles.rowPending : undefined}>
                      <td className={styles.colUser}>
                        <div className={styles.userName}>{u.display_name || u.subject}</div>
                        <div className={styles.userId}>{u.issuer} · {u.subject}</div>
                      </td>
                      <td>
                        <select
                          className={styles.select}
                          value={u.role_override || ''}
                          disabled={busy === key}
                          onChange={(e) =>
                            void patchUser(u, { role_override: e.target.value || null })
                          }
                        >
                          <option value="">auto ({ROLE_LABEL[u.resolved_role] || u.resolved_role})</option>
                          {ROLES.map((r) => (
                            <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        {u.kb_scope_empty ? (
                          <span className={styles.warn}>visible 0 / {allKbs.length}</span>
                        ) : u.visible_kbs.includes('*') || u.visible_kbs.length === allKbs.length ? (
                          <span className={styles.muted}>all ({allKbs.length})</span>
                        ) : (
                          <span className={styles.muted}>{u.visible_kbs.join(', ') || '—'}</span>
                        )}
                      </td>
                      <td>
                        {u.pending ? (
                          <span className={styles.badgePending}>pending</span>
                        ) : u.is_active ? (
                          <span className={styles.badgeOk}>active</span>
                        ) : (
                          <span className={styles.badgeOff}>inactive</span>
                        )}
                      </td>
                      <td>
                        {u.pending ? (
                          <button
                            className={styles.btn}
                            disabled={busy === key}
                            onClick={() => void patchUser(u, { is_active: true, role_override: 'wiki-study' })}
                          >
                            Approve
                          </button>
                        ) : (
                          <button
                            className={styles.btnGhost}
                            disabled={busy === key}
                            onClick={() => void patchUser(u, { is_active: false })}
                          >
                            Deactivate
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'audit' && (
        <div className={styles.body}>
          {loading && <div className={styles.empty}>Loading audit log…</div>}
          {!loading && records.length === 0 && (
            <div className={styles.empty}>No audit records yet. Writes and sensitive actions are logged here.</div>
          )}
          {!loading && records.length > 0 && (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.colTime}>Time</th>
                  <th>Action</th>
                  <th>Actor</th>
                  <th>Target</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <tr key={`${r.ts}-${i}`}>
                    <td className={styles.colTime}>{(r.ts || '').replace('T', ' ').slice(0, 19)}</td>
                    <td><code>{r.action}</code></td>
                    <td className={styles.muted}>{r.actor || '—'}</td>
                    <td className={styles.muted}>{r.target || '—'}</td>
                    <td>
                      <span className={r.result === 'ok' ? styles.badgeOk : styles.badgeOff}>
                        {r.result || '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
