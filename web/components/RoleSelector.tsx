'use client';

/**
 * Role switcher.
 *
 * This is a **downgrade**, not a login: you can work as a lower role than the
 * one you were granted, never higher. It goes through /api/auth/downgrade,
 * which is the only thing the backend honours (the old `softwiki_role` cookie
 * was removed when identity moved to the identity layer).
 */

import { useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';

const ROLES = [
  { id: 'wiki-study', label: 'role.study' },
  { id: 'wiki-work', label: 'role.work' },
  { id: 'wiki-manage', label: 'role.manage' },
  { id: 'wiki-admin', label: 'role.admin' },
];

const LEVEL: Record<string, number> = {
  'wiki-study': 0,
  'wiki-work': 1,
  'wiki-manage': 2,
  'wiki-admin': 3,
};

export default function RoleSelector() {
  const t = useT();
  const [role, setRole] = useState('wiki-study');
  const [granted, setGranted] = useState('wiki-study');
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/permissions', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        setRole(d.role || 'wiki-study');
        setGranted(d.granted_role || d.role || 'wiki-study');
      })
      .catch(() => {
        /* leave the fail-closed default */
      })
      .finally(() => setReady(true));
  }, []);

  const change = async (next: string) => {
    setError('');
    try {
      if (LEVEL[next] >= LEVEL[granted]) {
        // Back to the granted role: clear the downgrade instead of asking for
        // a higher role, which the API refuses by design.
        await fetch('/api/auth/downgrade', { method: 'DELETE' });
      } else {
        // A downgraded session may not raise itself, so clear first, then set.
        await fetch('/api/auth/downgrade', { method: 'DELETE' });
        const res = await fetch('/api/auth/downgrade', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: next }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
      }
      setRole(next);
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'could not change role');
    }
  };

  const options = ROLES.filter((r) => LEVEL[r.id] <= LEVEL[granted]);

  return (
    <div style={{ width: '100%' }}>
      <select
        aria-label={t('role.aria')}
        title={t('role.title')}
        value={role}
        onChange={(e) => void change(e.target.value)}
        disabled={!ready}
        style={{
          width: '100%',
          marginTop: 6,
          padding: '5px 7px',
          borderRadius: 6,
          border: '1px solid var(--glass-border, #d8dde3)',
          background: 'var(--glass-bg, #fff)',
          color: 'var(--text-secondary, #54595d)',
          fontSize: 11,
        }}
      >
        {options.map((r) => (
          <option key={r.id} value={r.id}>
            {t(r.label)}{r.id !== granted ? ` ${t('role.workingAs')}` : ''}
          </option>
        ))}
      </select>
      {error && (
        <div style={{ marginTop: 4, fontSize: 10, color: '#b32424' }}>{error}</div>
      )}
    </div>
  );
}
