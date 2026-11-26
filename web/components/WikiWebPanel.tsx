'use client';

/**
 * Wiki portal panel.
 *
 * The generated portal is a static snapshot served from
 * `<workspace>/exports/wikiweb/` under `/wikiweb`. It is shown inline so the
 * user never loses the app chrome, with an explicit "open in new tab" escape
 * hatch for full-screen browsing.
 *
 * The right rail is the control surface for regenerating it. It is deliberately
 * honest about what is wired up: page generation and prompts exist, rebuilding
 * the static portal is a script today (see `scripts/wikiweb_build.py`) and stays
 * disabled until there is a job API for it.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useT } from '@/lib/i18n';
import styles from './WikiWebPanel.module.css';

interface PortalState {
  lastBuilt: string | null;
  stale: boolean | null;
}

export default function WikiWebPanel() {
  const t = useT();
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const [kb, setKb] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [portal, setPortal] = useState<PortalState>({ lastBuilt: null, stale: null });

  useEffect(() => {
    fetch('/api/kb', { cache: 'no-store' })
      .then(r => r.json())
      .then(d => setKb(d.active || d.kbs?.[0]?.name || ''))
      .catch(() => setKb(''));
  }, []);

  useEffect(() => {
    if (!kb) return;
    fetch(`/api/wiki/pages?limit=1&kb=${encodeURIComponent(kb)}`, { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (!d) return;
        setPortal({
          lastBuilt: d.generated_at ?? d.last_built ?? null,
          stale: typeof d.stale === 'number' ? d.stale > 0 : null,
        });
      })
      .catch(() => {});
  }, [kb]);

  const reload = useCallback(() => setReloadKey(k => k + 1), []);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>{t('wikiweb.title')}</h1>
          <p className={styles.subtitle}>
            {kb ? `${kb} · ` : ''}
            {t('wikiweb.subtitle')}
          </p>
        </div>
        <div className={styles.actions}>
          <button className={styles.ghostBtn} onClick={reload} title={t('wikiweb.reload')}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12a9 9 0 1 1-3-6.7" /><polyline points="21 3 21 9 15 9" />
            </svg>
            {t('wikiweb.reload')}
          </button>
          <a
            className={styles.primaryBtn}
            href="/wikiweb"
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('wikiweb.openExternal')}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
        </div>
      </header>

      <div className={styles.body}>
        <div className={styles.frameWrap}>
          <iframe
            key={reloadKey}
            ref={frameRef}
            className={styles.frame}
            src="/wikiweb"
            title={t('wikiweb.title')}
          />
        </div>

        {/* ── Wiki assistant rail (skeleton; wired in the next step) ── */}
        <aside className={styles.rail}>
          <div className={styles.railSection}>
            <h2 className={styles.railTitle}>{t('wikiweb.generate')}</h2>
            <button className={styles.railBtn} disabled title={t('wikiweb.rebuildUnavailable')}>
              {t('wikiweb.rebuild')}
            </button>
            <p className={styles.railHint}>{t('wikiweb.rebuildUnavailable')}</p>
          </div>

          <div className={styles.railSection}>
            <h2 className={styles.railTitle}>{t('wikiweb.assistant')}</h2>
            <textarea
              className={styles.railInput}
              placeholder={t('wikiweb.assistantPlaceholder')}
              rows={3}
              disabled
            />
            <button className={styles.railBtn} disabled>{t('wikiweb.send')}</button>
            <p className={styles.railHint}>{t('wikiweb.assistantHint')}</p>
          </div>

          <div className={styles.railSection}>
            <h2 className={styles.railTitle}>{t('wikiweb.status')}</h2>
            <p className={styles.railHint}>
              {portal.lastBuilt ?? t('wikiweb.statusUnknown')}
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}
