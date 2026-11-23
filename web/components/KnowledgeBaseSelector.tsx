'use client';

/**
 * Knowledge-base switcher.
 *
 * The list comes from `/api/kb?verify=true`, which probes each kb's database in
 * this instance. A kb directory can exist while its database was never created
 * here (two compose stacks sharing one workspace root but not one PostgreSQL),
 * and offering such a kb would send the user to a page that answers 500.
 *
 * Switching navigates to that kb's own WebUI (`meta.yaml: web_url`) because
 * with auth disabled the backend refuses to change the process-wide workspace
 * (design D4). When `web_url` is absent the entry is listed but not navigable.
 */

import { useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';

interface KbEntry {
  name: string;
  description?: string;
  web_url?: string | null;
  available?: boolean;
  unavailable_reason?: string | null;
  has_index?: boolean;
}

export default function KnowledgeBaseSelector() {
  const t = useT();
  const [kbs, setKbs] = useState<KbEntry[]>([]);
  const [active, setActive] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/kb?verify=true', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        setKbs(d.kbs || []);
        setActive(d.active || '');
      })
      .catch(() => setKbs([]))
      .finally(() => setLoading(false));
  }, []);

  const currentHost = typeof window === 'undefined' ? '' : window.location.hostname;

  const change = async (name: string) => {
    const kb = kbs.find((k) => k.name === name);
    if (!kb || kb.available === false) return;

    // An instance that serves several kbs switches in place and remembers the
    // choice per user. Only fall back to cross-port navigation when the kb is
    // not served here (separate stacks).
    try {
      const res = await fetch('/api/kb/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kb: name }),
      });
      if (res.ok) {
        window.location.reload();
        return;
      }
    } catch {
      /* fall through to navigation */
    }

    if (!kb.web_url) return;
    // Preserve the current host: web_url carries the port, not the hostname,
    // so the same config works whether reached by IP or by domain.
    try {
      const target = new URL(kb.web_url, window.location.href);
      target.hostname = currentHost;
      target.protocol = window.location.protocol;
      window.location.href = target.toString();
    } catch {
      window.location.href = kb.web_url;
    }
  };

  const unavailable = kbs.filter((k) => k.available === false).length;

  return (
    <div style={{ width: '100%' }}>
      <select
        aria-label={t('workspace.kbAria')}
        title={
          loading
            ? t('workspace.kbTitle')
            : unavailable > 0
              ? `${kbs.length} knowledge base(s), ${unavailable} unavailable in this instance`
              : t('workspace.kbTitle')
        }
        value={active}
        onChange={(e) => change(e.target.value)}
        disabled={loading || kbs.length === 0}
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
        {loading && <option value="">Loading…</option>}
        {!loading && kbs.length === 0 && <option value="">{t('workspace.current')}</option>}
        {kbs.map((k) => {
          const blocked = k.available === false;
          const suffix = blocked
            ? ' — unavailable'
            : k.web_url
              ? ''
              : ' — current instance';
          return (
            <option key={k.name} value={k.name} disabled={blocked} title={k.unavailable_reason || undefined}>
              {k.name}{suffix}
            </option>
          );
        })}
      </select>
      {!loading && unavailable > 0 && (
        <div
          style={{
            marginTop: 4,
            fontSize: 10,
            lineHeight: 1.4,
            color: '#ac6600',
          }}
          title={kbs.filter((k) => k.available === false).map((k) => `${k.name}: ${k.unavailable_reason || 'no database'}`).join('\n')}
        >
          {unavailable} kb not served by this instance
        </div>
      )}
    </div>
  );
}
