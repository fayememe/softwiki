'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiIngestUrl, apiIngestFile, apiRebuildIndex } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './IngestPanel.module.css';

type IngestMode = 'url' | 'file';
type Status = { type: 'success' | 'error' | 'warning'; message: string } | null;

/** One dropped PDF and where it is in the upload sequence. */
type QueueStatus = 'waiting' | 'uploading' | 'done' | 'skipped' | 'error';

interface QueueItem {
  id: string;
  file: File;
  status: QueueStatus;
  /** Title for done, skip reason, or the error text. */
  message?: string;
  claims?: number;
}

const MAX_BATCH = 200;

function isPdf(file: File): boolean {
  return file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
}

function fileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function newId(): string {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export default function IngestPanel() {
  const t = useT();
  const [mode, setMode] = useState<IngestMode>('url');
  const [url, setUrl] = useState('');
  const [sourceId, setSourceId] = useState('');
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [status, setStatus] = useState<Status>(null);
  const [log, setLog] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  // The uploader runs one file at a time; these refs keep the loop from being
  // restarted by every render and keep the current source id without making the
  // queue effect depend on it.
  const processingRef = useRef(false);
  const sourceIdRef = useRef('');
  useEffect(() => { sourceIdRef.current = sourceId; }, [sourceId]);

  const appendLog = useCallback(
    (msg: string) => setLog(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]),
    [],
  );

  const addFiles = useCallback((files: File[]) => {
    const pdfs = files.filter(isPdf);
    const rejected = files.length - pdfs.length;
    if (pdfs.length === 0) {
      setStatus({ type: 'error', message: t('ingest.errPdfOnly') });
      return;
    }
    if (rejected > 0) {
      setStatus({ type: 'warning', message: t('ingest.someNotPdf', { n: rejected }) });
    } else {
      setStatus(null);
    }
    const room = Math.max(0, MAX_BATCH - queue.length);
    const accepted = pdfs.slice(0, room);
    if (pdfs.length > accepted.length) {
      setStatus({ type: 'warning', message: t('ingest.batchLimit', { n: MAX_BATCH }) });
    }
    setQueue(prev => [
      ...prev,
      ...accepted.map(file => ({ id: newId(), file, status: 'waiting' as QueueStatus })),
    ]);
  }, [queue.length, t]);

  /**
   * Sequential uploader.
   *
   * Every pass picks the first `waiting` item, uploads it, then re-runs because
   * the queue changed. Dropping more files while it is busy simply appends to
   * the queue — nothing is uploaded in parallel and nothing is dropped.
   */
  useEffect(() => {
    if (processingRef.current) return;
    const next = queue.find(item => item.status === 'waiting');
    if (!next) return;

    processingRef.current = true;
    setLoading(true);
    setQueue(prev => prev.map(item => (item.id === next.id ? { ...item, status: 'uploading' } : item)));
    appendLog(t('ingest.logUpload', { name: next.file.name }));

    void (async () => {
      try {
        const result = await apiIngestFile(next.file, sourceIdRef.current || undefined);
        if (result.status === 'skipped') {
          setQueue(prev => prev.map(item => (
            item.id === next.id ? { ...item, status: 'skipped', message: result.reason ?? '' } : item
          )));
          appendLog(t('ingest.logSkipped', { reason: result.reason ?? '' }));
        } else {
          setQueue(prev => prev.map(item => (
            item.id === next.id
              ? { ...item, status: 'done', message: result.title ?? '', claims: result.claims_extracted ?? 0 }
              : item
          )));
          appendLog(t('ingest.logIngested', {
            id: result.document_id ?? '',
            title: result.title ?? '',
            n: result.claims_extracted ?? 0,
          }));
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : t('ingest.errIngest');
        setQueue(prev => prev.map(item => (
          item.id === next.id ? { ...item, status: 'error', message: msg } : item
        )));
        appendLog(t('ingest.logError', { msg }));
      } finally {
        processingRef.current = false;
        setLoading(false);
        // Force the next pass even when the item above already changed the
        // queue: the effect only runs on a new array identity.
        setQueue(prev => [...prev]);
      }
    })();
  }, [queue, appendLog, t]);

  const handleIngestUrl = async () => {
    if (loading) return;
    const trimmed = url.trim();
    if (!trimmed) {
      setStatus({ type: 'error', message: t('ingest.errNoUrl') });
      return;
    }
    try { new URL(trimmed); } catch {
      setStatus({ type: 'error', message: t('ingest.errBadUrl') });
      return;
    }
    setLoading(true);
    setStatus(null);
    appendLog(t('ingest.logStart', { mode }));
    try {
      appendLog(t('ingest.logFetch', { url: trimmed }));
      const result = await apiIngestUrl(trimmed, sourceId || undefined);
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
    addFiles(Array.from(e.dataTransfer.files ?? []));
  };

  const counts = queue.reduce(
    (acc, item) => { acc[item.status] = (acc[item.status] ?? 0) + 1; return acc; },
    {} as Record<QueueStatus, number>,
  );
  const finished = (counts.done ?? 0) + (counts.skipped ?? 0) + (counts.error ?? 0);

  const removeItem = (id: string) => setQueue(prev => prev.filter(item => item.id !== id));
  const retryItem = (id: string) => setQueue(prev => prev.map(item => (
    item.id === id ? { ...item, status: 'waiting', message: undefined } : item
  )));
  const retryFailed = () => setQueue(prev => prev.map(item => (
    item.status === 'error' ? { ...item, status: 'waiting', message: undefined } : item
  )));
  const clearFinished = () => setQueue(prev => prev.filter(item => item.status === 'waiting' || item.status === 'uploading'));

  const statusLabel = (s: QueueStatus) => t(`ingest.q_${s}`);

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
              onKeyDown={e => e.key === 'Enter' && handleIngestUrl()}
              disabled={loading}
            />
          </div>
        )}

        {/* File drop zone — accepts a batch, uploads one by one */}
        {mode === 'file' && (
          <>
            <div
              className={`${styles.dropZone} ${queue.length ? styles.dropZoneHasFile : ''}`}
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
                multiple
                className={styles.fileInput}
                onChange={e => {
                  addFiles(Array.from(e.target.files ?? []));
                  // Allow re-selecting the same file later.
                  e.target.value = '';
                }}
                id="ingest-file-input"
              />
              <div className={styles.dropPlaceholder}>
                <span className={styles.dropIcon}>↓</span>
                <span>{queue.length ? t('ingest.dropMore') : t('ingest.dropHint')}</span>
              </div>
            </div>

            {queue.length > 0 && (
              <div className={styles.queueBox}>
                <div className={styles.queueHead}>
                  <span className={styles.queueTitle}>
                    {t('ingest.queueTitle')} · {t('ingest.queueSummary', {
                      total: queue.length,
                      done: counts.done ?? 0,
                      skipped: counts.skipped ?? 0,
                      failed: counts.error ?? 0,
                    })}
                  </span>
                  <div className={styles.queueActions}>
                    {counts.error ? (
                      <button className={styles.linkAction} onClick={retryFailed}>{t('ingest.retryFailed')}</button>
                    ) : null}
                    {finished > 0 ? (
                      <button className={styles.linkAction} onClick={clearFinished}>{t('ingest.clearFinished')}</button>
                    ) : null}
                  </div>
                </div>
                <ul className={styles.queueList}>
                  {queue.map(item => (
                    <li key={item.id} className={`${styles.queueItem} ${styles[`q_${item.status}`]}`}>
                      <span className={styles.queueFile} title={item.file.name}>{item.file.name}</span>
                      <span className={styles.queueSize}>{fileSize(item.file.size)}</span>
                      <span className={styles.queueStatus}>{statusLabel(item.status)}</span>
                      {item.status === 'done' && item.message ? (
                        <span className={styles.queueMessage} title={item.message}>
                          {item.claims ? `${item.claims} ${t('ingest.claims')}` : item.message}
                        </span>
                      ) : null}
                      {item.status === 'error' || item.status === 'skipped' ? (
                        <span className={styles.queueError} title={item.message}>{item.message}</span>
                      ) : null}
                      {item.status === 'error' ? (
                        <button className={styles.queueBtn} onClick={() => retryItem(item.id)}>{t('ingest.retry')}</button>
                      ) : null}
                      {item.status === 'waiting' ? (
                        <button className={styles.queueBtn} onClick={() => removeItem(item.id)}>{t('ingest.remove')}</button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
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
          {mode === 'url' && (
            <button
              id="ingest-submit-btn"
              className={styles.primaryBtn}
              onClick={handleIngestUrl}
              disabled={loading}
              aria-busy={loading}
            >
              {loading ? <><span className={styles.spinner} /> {t('ingest.ingesting')}</> : `⊕ ${t('ingest.ingestBtn')}`}
            </button>
          )}
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
