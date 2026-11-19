'use client';

import { useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';

const ROLES = [
  { id: 'wiki-study', label: 'role.study' },
  { id: 'wiki-work', label: 'role.work' },
  { id: 'wiki-manage', label: 'role.manage' },
  { id: 'wiki-admin', label: 'role.admin' },
];

export default function RoleSelector() {
  const t = useT();
  const [role, setRole] = useState('wiki-study');
  const [ready, setReady] = useState(false);

  useEffect(() => {
    fetch('/api/permissions', { cache: 'no-store' })
      .then(r => r.json())
      .then(d => { setRole(d.role || 'wiki-study'); setReady(true); })
      .catch(() => setReady(true));
  }, []);

  const change = (next: string) => {
    document.cookie = `softwiki_role=${encodeURIComponent(next)}; path=/; max-age=604800; SameSite=Lax`;
    setRole(next);
    window.location.reload();
  };

  return (
    <select
      aria-label={t('role.aria')}
      title={t('role.title')}
      value={role}
      onChange={e => change(e.target.value)}
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
      {ROLES.map(r => <option key={r.id} value={r.id}>{t(r.label)}</option>)}
    </select>
  );
}
