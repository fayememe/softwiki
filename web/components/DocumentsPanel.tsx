'use client';

import { useState, useEffect } from 'react';
import { apiListDocuments, apiDeleteDocument } from '@/lib/api';
import type { Document } from '@/lib/api';
import styles from './DocumentsPanel.module.css';

interface DocumentsPanelProps {
  onRefreshStats?: () => void;
}

export default function DocumentsPanel({ onRefreshStats }: DocumentsPanelProps) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiListDocuments();
      setDocuments(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch documents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocs();
  }, []);

  const handleDelete = async (id: number, title: string) => {
    if (!confirm(`Are you sure you want to delete the document "${title}"? This will also delete all associated chunks, claims, events, and relationships.`)) {
      return;
    }
    try {
      await apiDeleteDocument(id);
      setDocuments(prev => prev.filter(d => d.id !== id));
      if (onRefreshStats) onRefreshStats();
    } catch (err) {
      alert(`Delete failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.topBar}>
        <span className={styles.title}>◉ Ingested Documents</span>
      </div>

      <div className={styles.body}>
        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <span>Loading documents…</span>
          </div>
        ) : error ? (
          <div className={styles.error}>
            <span className={styles.emptyIcon}>⚠️</span>
            <span>Error: {error}</span>
          </div>
        ) : documents.length === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>📄</span>
            <h3>No documents found</h3>
            <p>Ingest some research sources via the Ingest Sources tab.</p>
          </div>
        ) : (
          <div className={styles.tableWrapper}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>Title</th>
                  <th className={styles.th}>Source</th>
                  <th className={styles.th}>Type</th>
                  <th className={styles.th}>Published</th>
                  <th className={styles.th}>Trust Level</th>
                  <th className={styles.th}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.map(doc => (
                  <tr key={doc.id} className={styles.tr}>
                    <td className={styles.td}>
                      <div className={styles.docTitle} title={doc.title}>
                        {doc.title}
                      </div>
                      {doc.url && (
                        <a
                          href={doc.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={styles.docUrl}
                        >
                          Link ↗
                        </a>
                      )}
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
                      <button
                        className={styles.btnDelete}
                        onClick={() => handleDelete(doc.id, doc.title)}
                      >
                        Delete
                      </button>
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
