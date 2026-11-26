'use client';

/**
 * Cross-kb overview.
 *
 * This is deliberately not "the current kb": the instance may serve several
 * knowledge bases (one directory each under WORKSPACES_ROOT), and the home page
 * is where you compare them. Counts come from `/api/kb/stats`, which reads each
 * kb's own database and marks ones this instance cannot serve as unavailable
 * instead of showing zeroes.
 */

import { useCallback, useEffect, useState } from 'react';
import { apiKbStats, apiSwitchKb } from '@/lib/api';
import type { KbStatsEntry, KbStatsResponse } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './DashboardPanel.module.css';

const COUNT_KEYS = ['documents', 'chunks', 'claims', 'entities', 'relationships', 'events'] as const;

export default function DashboardPanel() {
  const t = useT();
  const [data, setData] = useState<KbStatsResponse | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await apiKbStats());
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = setInterval(() => { void load(); }, 30000);
    return () => clearInterval(interval);
  }, [load]);

  const openKb = useCallback(async (kb: KbStatsEntry) => {
    if (!kb.available || kb.active || busy) return;
    setBusy(kb.name);
    try {
      if (await apiSwitchKb(kb.name)) {
        window.location.reload();
        return;
      }
      if (kb.web_url) {
        const target = new URL(kb.web_url, window.location.href);
        target.hostname = window.location.hostname;
        target.protocol = window.location.protocol;
        window.location.href = target.toString();
      }
    } finally {
      setBusy('');
    }
  }, [busy]);

  const kbs = data?.kbs ?? [];
  const available = kbs.filter(k => k.available).length;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{t('dashboard.title')}</h1>
          <p className={styles.subtitle}>
            {data
              ? t('dashboard.instanceSummary', { total: kbs.length, available })
              : t('dashboard.loading')}
          </p>
        </div>
        {data && (
          <div className={styles.total}>
            <span className={styles.totalNum}>{data.totals.documents.toLocaleString()}</span>
            <span className={styles.totalLabel}>{t('dashboard.documents')}</span>
          </div>
        )}
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {data && (
        <>
          <div className={styles.totalsRow}>
            {COUNT_KEYS.map(key => (
              <div key={key} className={styles.totalCell}>
                <span className={styles.totalCellNum}>{data.totals[key].toLocaleString()}</span>
                <span className={styles.totalCellLabel}>{t(`dashboard.item_${key}`)}</span>
              </div>
            ))}
          </div>

          <div className={styles.grid}>
            {kbs.map(kb => (
              <button
                key={kb.name}
                type="button"
                className={`${styles.card} ${kb.active ? styles.cardActive : ''} ${!kb.available ? styles.cardDisabled : ''}`}
                onClick={() => void openKb(kb)}
                title={kb.available ? kb.description : (kb.reason || t('dashboard.unavailable'))}
                disabled={!kb.available || kb.active || busy === kb.name}
              >
                <div className={styles.cardHead}>
                  <span className={styles.cardName}>{kb.name}</span>
                  {kb.active && <span className={styles.activePill}>{t('dashboard.current')}</span>}
                  {!kb.available && <span className={styles.badTag}>{t('dashboard.unavailable')}</span>}
                </div>
                <p className={styles.cardDesc}>{kb.description}</p>
                {kb.counts ? (
                  <div className={styles.cardCounts}>
                    {COUNT_KEYS.map(key => (
                      <div key={key}>
                        <span className={styles.cardNum}>{kb.counts![key].toLocaleString()}</span>
                        <span className={styles.cardLabel}>{t(`dashboard.item_${key}`)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  // The raw reason is often a driver message (missing column,
                  // refused connection). Keep it in the tooltip, show a stable
                  // label in the card.
                  <p className={styles.cardReason} title={kb.reason || ''}>
                    {t('dashboard.unavailable')}
                  </p>
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
