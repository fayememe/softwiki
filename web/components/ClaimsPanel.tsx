'use client';

import { useState, useEffect, useMemo } from 'react';
import { apiListClaims } from '@/lib/api';
import type { Claim } from '@/lib/api';
import { useT } from '@/lib/i18n';
import Pagination from './Pagination';
import type { NavFocus, Navigate } from '@/lib/navigation';
import styles from './ClaimsPanel.module.css';

const STANCES = ['supportive', 'cautious', 'opposed', 'unclear'];

export default function ClaimsPanel({
  focus,
  onNavigate,
}: {
  focus?: NavFocus;
  onNavigate?: Navigate;
}) {
  const t = useT();
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter states
  const [selectedActor, setSelectedActor] = useState('all');
  const [selectedStance, setSelectedStance] = useState('all');
  const [query, setQuery] = useState('');
  const [docFilter, setDocFilter] = useState<number | null>(null);
  const [topicFilter, setTopicFilter] = useState<string | null>(null);
  const [claimFilter, setClaimFilter] = useState<number | null>(null);

  // Paging is applied after filtering, so the page always shows full rows.
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

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

  // Apply the focus payload handed over by another panel (graph claim, document
  // row, wiki subject, timeline topic...).
  useEffect(() => {
    if (!focus || focus.kind !== 'claims') return;
    setSelectedActor(focus.actor ?? 'all');
    setSelectedStance('all');
    setQuery(focus.q ?? '');
    setDocFilter(focus.documentId ?? null);
    setTopicFilter(focus.topic ?? null);
    setClaimFilter(focus.claimId ?? null);
  }, [focus]);

  // Compute unique actors for filter
  const actors = Array.from(new Set(claims.map(c => c.actor).filter(a => a && a.trim()))) as string[];

  // Filtered claims
  const needle = query.trim().toLowerCase();
  const filteredClaims = claims.filter(c => {
    const matchActor = selectedActor === 'all' || c.actor === selectedActor;
    const matchStance = selectedStance === 'all' || (c.stance || 'unclear').toLowerCase() === selectedStance.toLowerCase();
    const matchDoc = docFilter === null || c.document_id === docFilter;
    const matchTopic = !topicFilter || (c.topic || '').toLowerCase() === topicFilter.toLowerCase();
    const matchClaim = claimFilter === null || c.id === claimFilter;
    const matchQuery = !needle
      || c.text.toLowerCase().includes(needle)
      || (c.actor || '').toLowerCase().includes(needle)
      || (c.topic || '').toLowerCase().includes(needle);
    return matchActor && matchStance && matchDoc && matchTopic && matchClaim && matchQuery;
  });

  // Reset to the first page whenever the filter result set changes shape.
  useEffect(() => { setPage(1); }, [selectedActor, selectedStance, query, docFilter, topicFilter, claimFilter]);

  const pageCount = Math.max(1, Math.ceil(filteredClaims.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pagedClaims = useMemo(
    () => filteredClaims.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [filteredClaims, currentPage, pageSize],
  );

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
          <div className={styles.filterGroup}>
            <label className={styles.filterLabel} htmlFor="claim-search">{t('claims.searchLabel')}</label>
            <input
              id="claim-search"
              className={styles.select}
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder={t('claims.searchPlaceholder')}
            />
          </div>
          {(docFilter !== null || topicFilter || claimFilter !== null) && (
            <div className={styles.filterGroup}>
              <span className={styles.filterLabel}>{t('claims.focusFilter')}</span>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {docFilter !== null && (
                  <button className={styles.focusChip} onClick={() => setDocFilter(null)}>
                    {t('claims.byDocument', { id: docFilter })} ✕
                  </button>
                )}
                {topicFilter && (
                  <button className={styles.focusChip} onClick={() => setTopicFilter(null)}>
                    {t('claims.byTopic', { topic: topicFilter })} ✕
                  </button>
                )}
                {claimFilter !== null && (
                  <button className={styles.focusChip} onClick={() => setClaimFilter(null)}>
                    {t('claims.byClaim', { id: claimFilter })} ✕
                  </button>
                )}
              </div>
            </div>
          )}
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
                  <th className={styles.th}>{t('claims.colActions')}</th>
                </tr>
              </thead>
              <tbody>
                {pagedClaims.map(c => (
                  <tr key={c.id} className={styles.tr}>
                    <td className={`${styles.td} ${styles.actor}`}>{c.actor || t('common.unknown')}</td>
                    <td className={`${styles.td} ${styles.topic}`}>
                      <span style={{ fontWeight: 500 }}>{c.topic || 'general'}</span>
                    </td>
                    <td className={`${styles.td} ${styles.stance}`}>
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
                    <td className={`${styles.td} ${styles.claimDate}`}>
                      {c.published_at}
                    </td>
                    <td className={styles.td}>
                      {onNavigate && c.document_id ? (
                        <button
                          className={styles.focusChip}
                          onClick={() => onNavigate('documents', { kind: 'document', documentId: c.document_id })}
                          title={t('claims.openDocument')}
                        >
                          {t('claims.sourceDoc')}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && !error && filteredClaims.length > 0 && (
          <Pagination
            page={currentPage}
            pageSize={pageSize}
            total={filteredClaims.length}
            onPageChange={setPage}
            onPageSizeChange={(n) => { setPageSize(n); setPage(1); }}
          />
        )}
      </div>
    </div>
  );
}
