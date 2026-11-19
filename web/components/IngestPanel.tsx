'use client';

import { useState, useRef } from 'react';
import { apiIngestUrl, apiIngestFile, apiRebuildIndex } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './IngestPanel.module.css';

type IngestMode = 'url' | 'file';
type Status = { type: 'success' | 'error' | 'warning'; message: string } | null;

export default function IngestPanel() {
  const t = useT();
  const [mode, setMode] = useState<IngestMode>('url');
  const [url, setUrl] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [status, setStatus] = useState<Status>(null);
  const [log, setLog] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  const appendLog = (msg: string) => setLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);

  const handleIngest = async () => {
    if (loading) return;
    if (mode === 'url') {
      const trimmed = url.trim();
      if (!trimmed) {
        setStatus({ type: 'error', message: t('ingest.errNoUrl') });
        return;
      }
      try { new URL(trimmed); } catch {
        setStatus({ type: 'error', message: t('ingest.errBadUrl') });
        return;
      }
    }
    if (mode === 'file' && !file) {
      setStatus({ type: 'error', message: t('ingest.errNoFile') });
      return;
    }
    setLoading(true);
    setStatus(null);
    appendLog(t('ingest.logStart', { mode }));
    try {
      let result;
      if (mode === 'url') {
        appendLog(t('ingest.logFetch', { url }));
        result = await apiIngestUrl(url.trim(), sourceId || undefined);
      } else {
        appendLog(t('ingest.logUpload', { name: file!.name }));
        result = await apiIngestFile(file!, sourceId || undefined);
      }

      if (result.status === 'skipped') {
        setStatus({ type: 'warning', message: t('ingest.skipped', { reason: result.reason ?? '' }) });
        appendLog(t('ingest.logSkipped', { reason: result.reason ?? '' }));
      } else {
        setStatus({
          type: 'success',
          message: t('ingest.success', { title: result.title ?? '', n: result.claims_extracted ?? 0 }),
        });
        appendLog(t('ingest.logIngested', {
          id: result.document_id ?? '',
          title: result.title ?? '',
          n: result.claims_extracted ?? 0,
        }));
        setUrl('');
        setFile(null);
        if (fileRef.current) fileRef.current.value = '';
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('ingest.errIngest');
      setStatus({ type: 'error', message: msg });
      appendLog(t('ingest.logError', { msg }));
    } finally {
      setLoading(false);
    }
  };

  const handleRebuildIndex = async () => {
    if (indexing) return;
    setIndexing(true);
    appendLog(t('ingest.logRebuildStart'));
    try {
      const result = await apiRebuildIndex();
      setStatus({ type: 'success', message: t('ingest.indexRebuilt', { n: result.indexed_chunks }) });
      appendLog(t('ingest.logRebuildDone', { n: result.indexed_chunks }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : t('ingest.errRebuild');
      setStatus({ type: 'error', message: msg });
      appendLog(t('ingest.logError', { msg }));
    } finally {
      setIndexing(false);
    }
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.type === 'application/pdf') {
      setFile(dropped);
      setStatus(null);
    } else {
      setStatus({ type: 'error', message: t('ingest.errPdfOnly') });
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.topBar}>
        <span className={styles.title}>{t('ingest.title')}</span>
      </div>

      <div className={styles.body}>
        {/* Mode toggle */}
        <div className={styles.modeToggle}>
          <button
            id="ingest-mode-url"
            className={`${styles.modeBtn} ${mode === 'url' ? styles.active : ''}`}
            onClick={() => { setMode('url'); setStatus(null); }}
          >⊕ {t('ingest.modeUrl')}</button>
          <button
            id="ingest-mode-file"
            className={`${styles.modeBtn} ${mode === 'file' ? styles.active : ''}`}
            onClick={() => { setMode('file'); setStatus(null); }}
          >⊕ {t('ingest.modeFile')}</button>
        </div>

        {/* URL form */}
        {mode === 'url' && (
          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="ingest-url-input">{t('ingest.urlLabel')}</label>
            <input
              id="ingest-url-input"
              type="url"
              className={styles.input}
              placeholder="https://example.com/article"
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleIngest()}
              disabled={loading}
            />
          </div>
        )}

        {/* File drop zone */}
        {mode === 'file' && (
          <div
            className={`${styles.dropZone} ${file ? styles.dropZoneHasFile : ''}`}
            onDragOver={e => e.preventDefault()}
            onDrop={handleFileDrop}
            onClick={() => fileRef.current?.click()}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileRef.current?.click(); } }}
            role="button"
            tabIndex={0}
            aria-label={t('ingest.dropAria')}
            id="ingest-dropzone"
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,application/pdf"
              className={styles.fileInput}
              onChange={e => { setFile(e.target.files?.[0] || null); setStatus(null); }}
              id="ingest-file-input"
            />
            {file ? (
              <div className={styles.fileSelected}>
                <span className={styles.fileIcon}>📄</span>
                <span className={styles.fileName}>{file.name}</span>
                <span className={styles.fileSize}>({(file.size / 1024).toFixed(0)} KB)</span>
              </div>
            ) : (
              <div className={styles.dropPlaceholder}>
                <span className={styles.dropIcon}>↓</span>
                <span>{t('ingest.dropHint')}</span>
              </div>
            )}
          </div>
        )}

        {/* Source ID */}
        <div className={styles.formGroup}>
          <label className={styles.label} htmlFor="ingest-source-id">{t('ingest.sourceIdLabel')} <span className={styles.optional}>({t('common.optional')})</span></label>
          <input
            id="ingest-source-id"
            type="text"
            className={styles.input}
            placeholder={t('ingest.sourceIdPlaceholder')}
            value={sourceId}
            onChange={e => setSourceId(e.target.value)}
            disabled={loading}
          />
          <p className={styles.hint}>{t('ingest.sourceIdHint')} <code>configs/sources.yaml</code></p>
        </div>

        {/* Status message */}
        {status && (
          <div className={`${styles.status} ${styles[status.type]}`}>
            <span className={styles.statusIcon}>
              {status.type === 'success' ? '✓' : status.type === 'warning' ? '⚠' : '✗'}
            </span>
            {status.message}
          </div>
        )}

        {/* Action buttons */}
        <div className={styles.actions}>
          <button
            id="ingest-submit-btn"
            className={styles.primaryBtn}
            onClick={handleIngest}
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? <><span className={styles.spinner} /> {t('ingest.ingesting')}</> : `⊕ ${t('ingest.ingestBtn')}`}
          </button>
          <button
            id="ingest-index-btn"
            className={styles.secondaryBtn}
            onClick={handleRebuildIndex}
            disabled={indexing}
            aria-busy={indexing}
          >
            {indexing ? <><span className={styles.spinner} /> {t('ingest.indexing')}</> : `⟳ ${t('ingest.rebuildBtn')}`}
          </button>
        </div>

        {/* Activity log */}
        {log.length > 0 && (
          <div className={styles.logBox}>
            <div className={styles.logHeader}>{t('ingest.activityLog')}</div>
            <div className={styles.logEntries}>
              {log.map((entry, i) => (
                <div key={i} className={styles.logEntry}>{entry}</div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
