'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiListDocuments, apiListDocumentsPaged, apiDeleteDocument } from '@/lib/api';
import type { Document } from '@/lib/api';
import { useT } from '@/lib/i18n';
import Pagination from './Pagination';
import styles from './DocumentsPanel.module.css';

import type { NavFocus, Navigate } from '@/lib/navigation';

interface DocumentsPanelProps {
  onRefreshStats?: () => void;
  focus?: NavFocus;
  onNavigate?: Navigate;
}

export default function DocumentsPanel({ onRefreshStats, focus, onNavigate }: DocumentsPanelProps) {
  const t = useT();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiListDocumentsPaged(pageSize, (page - 1) * pageSize);
      setDocuments(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('documents.fetchFailed'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, t]);

  useEffect(() => {
    void fetchDocs();
  }, [fetchDocs]);

  // Jump to the page that holds the document another panel linked to.
  useEffect(() => {
    if (!focus || focus.kind !== 'document') return;
    let cancelled = false;
    void (async () => {
      try {
        const all = await apiListDocuments();
        if (cancelled) return;
        const index = all.findIndex(doc => doc.id === focus.documentId);
        if (index >= 0) setPage(Math.floor(index / pageSize) + 1);
        setHighlight(focus.documentId);
      } catch {
        /* the table still works without the jump */
      }
    })();
    return () => { cancelled = true; };
  }, [focus, pageSize]);

  const handleDelete = async (id: number, title: string) => {
    if (!confirm(t('documents.deleteConfirm', { title }))) {
      return;
    }
    try {
      await apiDeleteDocument(id);
      if (onRefreshStats) onRefreshStats();
      await fetchDocs();
    } catch (err) {
      alert(t('documents.deleteFailed', { msg: err instanceof Error ? err.message : t('common.unknown') }));
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.topBar}>
        <span className={styles.title}>◉ {t('documents.title')}</span>
      </div>

      <div className={styles.body}>
        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <span>{t('documents.loading')}</span>
          </div>
        ) : error ? (
          <div className={styles.error}>
            <span className={styles.emptyIcon}>⚠️</span>
            <span>{t('common.error')}: {error}</span>
          </div>
        ) : documents.length === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>📄</span>
            <h3>{t('documents.emptyTitle')}</h3>
            <p>{t('documents.emptyDesc')}</p>
          </div>
        ) : (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>{t('documents.colTitle')}</th>
                  <th className={styles.th}>{t('documents.colSource')}</th>
                  <th className={styles.th}>{t('documents.colType')}</th>
                  <th className={styles.th}>{t('documents.colPublished')}</th>
                  <th className={styles.th}>{t('documents.colTrust')}</th>
                  <th className={styles.th}>{t('documents.colActions')}</th>
                </tr>
              </thead>
              <tbody>
                {documents.map(doc => (
                  <tr key={doc.id} className={`${styles.tr} ${highlight === doc.id ? styles.trFocus : ''}`}>
                    <td className={styles.td}>
                      <div className={styles.docTitleRow}>
                        <span className={styles.docTitle} title={doc.title}>
                          {doc.title}
                        </span>
                        {doc.url && (
                          <a
                            href={doc.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={styles.docUrl}
                            title={doc.url}
                          >
                            ↗
                          </a>
                        )}
                      </div>
                    </td>
                    <td className={styles.td}>{doc.source_name}</td>
                    <td className={styles.td}>
                      <span style={{ fontSize: '11px', opacity: 0.8 }}>
                        {doc.source_type || 'manual'}
                      </span>
                    </td>
                    <td className={styles.td}>{doc.published_at}</td>
                    <td className={styles.td}>
                      <span className={`${styles.badge} ${styles[(doc.trust_level || 'medium').toLowerCase()] || styles.medium}`}>
                        {doc.trust_level}
                      </span>
                    </td>
                    <td className={styles.td}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        {onNavigate && (
                          <button
                            className={styles.btnDelete}
                            onClick={() => onNavigate('claims', { kind: 'claims', documentId: doc.id })}
                          >
                            {t('documents.viewClaims')}
                          </button>
                        )}
                        <button
                          className={styles.btnDelete}
                          onClick={() => handleDelete(doc.id, doc.title)}
                        >
                          {t('common.delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!loading && !error && total > 0 && (
          <Pagination
            page={page}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
            onPageSizeChange={(n) => { setPageSize(n); setPage(1); }}
          />
        )}
      </div>
    </div>
  );
}
