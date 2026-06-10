'use client';

import { useState, useEffect } from 'react';
import { apiListClaims } from '@/lib/api';
import type { Claim } from '@/lib/api';
import styles from './ClaimsPanel.module.css';

export default function ClaimsPanel() {
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
      setError(err instanceof Error ? err.message : 'Failed to fetch claims');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClaims();
  }, []);

  // Compute unique actors for filter
  const actors = Array.from(new Set(claims.map(c => c.actor).filter(Boolean))) as string[];

  // Filtered claims
  const filteredClaims = claims.filter(c => {
    const matchActor = selectedActor === 'all' || c.actor === selectedActor;
    const matchStance = selectedStance === 'all' || (c.stance || 'unclear').toLowerCase() === selectedStance.toLowerCase();
    return matchActor && matchStance;
  });

  return (
    <div className={styles.panel}>
      <div className={styles.topBar}>
        <span className={styles.title}>◈ Extracted Claims & Assertions</span>
      </div>

      {/* Filter controls */}
      {!loading && !error && claims.length > 0 && (
        <div className={styles.filters}>
          <div className={styles.filterGroup}>
            <label className={styles.filterLabel} htmlFor="actor-filter">Actor:</label>
            <select
              id="actor-filter"
              className={styles.select}
              value={selectedActor}
              onChange={e => setSelectedActor(e.target.value)}
            >
              <option value="all">All Actors</option>
              {actors.map(actor => (
                <option key={actor} value={actor}>{actor}</option>
              ))}
            </select>
          </div>

          <div className={styles.filterGroup}>
            <label className={styles.filterLabel} htmlFor="stance-filter">Stance:</label>
            <select
              id="stance-filter"
              className={styles.select}
              value={selectedStance}
              onChange={e => setSelectedStance(e.target.value)}
            >
              <option value="all">All Stances</option>
              <option value="supportive">Supportive</option>
              <option value="cautious">Cautious</option>
              <option value="opposed">Opposed</option>
              <option value="unclear">Unclear</option>
            </select>
          </div>
        </div>
      )}

      <div className={styles.body}>
        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <span>Loading claims database…</span>
          </div>
        ) : error ? (
          <div className={styles.error}>
            <span className={styles.emptyIcon}>⚠️</span>
            <span>Error: {error}</span>
          </div>
        ) : claims.length === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>◈</span>
            <h3>No claims found</h3>
            <p>Ingest documents containing source text, and claims will be automatically extracted.</p>
          </div>
        ) : filteredClaims.length === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>🔍</span>
            <h3>No matching claims</h3>
            <p>Try resetting your filter options above.</p>
          </div>
        ) : (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>Actor</th>
                  <th className={styles.th}>Topic</th>
                  <th className={styles.th}>Stance</th>
                  <th className={styles.th}>Confidence</th>
                  <th className={styles.th}>Claim Description</th>
                  <th className={styles.th}>Date</th>
                </tr>
              </thead>
              <tbody>
                {filteredClaims.map(c => (
                  <tr key={c.id} className={styles.tr}>
                    <td className={`${styles.td} ${styles.actor}`}>{c.actor || 'Unknown'}</td>
                    <td className={styles.td}>
                      <span style={{ fontWeight: 500 }}>{c.topic || 'general'}</span>
                    </td>
                    <td className={styles.td}>
                      <span className={`${styles.badge} ${styles[(c.stance || 'unclear').toLowerCase()]}`}>
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
