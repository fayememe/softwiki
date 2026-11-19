'use client';

import { useState, useEffect } from 'react';
import { apiListClaims } from '@/lib/api';
import type { Claim } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './ClaimsPanel.module.css';

const STANCES = ['supportive', 'cautious', 'opposed', 'unclear'];

export default function ClaimsPanel() {
  const t = useT();
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter states
  const [selectedActor, setSelectedActor] = useState('all');
  const [selectedStance, setSelectedStance] = useState('all');

  const fetchClaims = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiListClaims();
      setClaims(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('claims.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClaims();
  }, []);

  // Compute unique actors for filter
  const actors = Array.from(new Set(claims.map(c => c.actor).filter(a => a && a.trim()))) as string[];

  // Filtered claims
  const filteredClaims = claims.filter(c => {
    const matchActor = selectedActor === 'all' || c.actor === selectedActor;
    const matchStance = selectedStance === 'all' || (c.stance || 'unclear').toLowerCase() === selectedStance.toLowerCase();
    return matchActor && matchStance;
  });

  return (
    <div className={styles.panel}>
      <div className={styles.topBar}>
        <span className={styles.title}>◈ {t('claims.title')}</span>
      </div>

      {/* Filter controls */}
      {!loading && !error && claims.length > 0 && (
        <div className={styles.filters}>
          <div className={styles.filterGroup}>
            <label className={styles.filterLabel} htmlFor="actor-filter">{t('claims.actorLabel')}</label>
            <select
              id="actor-filter"
              className={styles.select}
              value={selectedActor}
              onChange={e => setSelectedActor(e.target.value)}
            >
              <option value="all">{t('claims.allActors')}</option>
              {actors.map(actor => (
                <option key={actor} value={actor}>{actor}</option>
              ))}
            </select>
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel} htmlFor="stance-filter">{t('claims.stanceLabel')}</label>
            <select
              id="stance-filter"
              className={styles.select}
              value={selectedStance}
              onChange={e => setSelectedStance(e.target.value)}
            >
              <option value="all">{t('claims.allStances')}</option>
              {STANCES.map(stance => (
                <option key={stance} value={stance}>{t(`claims.stance_${stance}`)}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className={styles.body}>
        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <span>{t('claims.loading')}</span>
          </div>
        ) : error ? (
          <div className={styles.error}>
            <span className={styles.emptyIcon}>⚠️</span>
            <span>{t('common.error')}: {error}</span>
          </div>
        ) : claims.length === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>◈</span>
            <h3>{t('claims.emptyTitle')}</h3>
            <p>{t('claims.emptyDesc')}</p>
          </div>
        ) : filteredClaims.length === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>🔍</span>
            <h3>{t('claims.noMatchTitle')}</h3>
            <p>{t('claims.noMatchDesc')}</p>
          </div>
        ) : (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>{t('claims.colActor')}</th>
                  <th className={styles.th}>{t('claims.colTopic')}</th>
                  <th className={styles.th}>{t('claims.colStance')}</th>
                  <th className={styles.th}>{t('claims.colConfidence')}</th>
                  <th className={styles.th}>{t('claims.colText')}</th>
                  <th className={styles.th}>{t('claims.colDate')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredClaims.map(c => (
                  <tr key={c.id} className={styles.tr}>
                    <td className={`${styles.td} ${styles.actor}`}>{c.actor || t('common.unknown')}</td>
                    <td className={styles.td}>
                      <span style={{ fontWeight: 500 }}>{c.topic || 'general'}</span>
                    </td>
                    <td className={styles.td}>
                      <span className={`${styles.badge} ${styles[(c.stance || 'unclear').toLowerCase()] || styles.unclear}`}>
                        {c.stance || 'unclear'}
                      </span>
                    </td>
                    <td className={`${styles.td} ${styles.confidence}`}>
                      {c.confidence !== null ? `${(c.confidence * 100).toFixed(0)}%` : '-'}
                    </td>
                    <td className={`${styles.td} ${styles.claimText}`}>
                      {c.text}
                    </td>
                    <td className={styles.td} style={{ fontSize: '12px', whiteSpace: 'nowrap' }}>
                      {c.published_at}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
