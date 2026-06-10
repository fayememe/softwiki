'use client';

import { useState, useRef } from 'react';
import { apiIngestUrl, apiIngestFile, apiRebuildIndex } from '@/lib/api';
import styles from './IngestPanel.module.css';

type IngestMode = 'url' | 'file';
type Status = { type: 'success' | 'error' | 'warning'; message: string } | null;

export default function IngestPanel() {
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
    if (mode === 'url' && !url.trim()) {
      setStatus({ type: 'error', message: 'Please enter a URL.' });
      return;
    }
    if (mode === 'file' && !file) {
      setStatus({ type: 'error', message: 'Please select a PDF file.' });
      return;
    }
    setLoading(true);
    setStatus(null);
    appendLog(`Starting ingest (mode: ${mode})…`);
    try {
      let result;
      if (mode === 'url') {
        appendLog(`Fetching URL: ${url}`);
        result = await apiIngestUrl(url.trim(), sourceId || undefined);
      } else {
        appendLog(`Uploading file: ${file!.name}`);
        result = await apiIngestFile(file!, sourceId || undefined);
      }

      if (result.status === 'skipped') {
        setStatus({ type: 'warning', message: `Skipped: ${result.reason}` });
        appendLog(`Skipped — ${result.reason}`);
      } else {
        setStatus({ type: 'success', message: `Ingested: "${result.title}" — ${result.claims_extracted} claims extracted` });
        appendLog(`✓ Document ID ${result.document_id}: "${result.title}" (${result.claims_extracted} claims)`);
        setUrl('');
        setFile(null);
        if (fileRef.current) fileRef.current.value = '';
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Ingestion failed';
      setStatus({ type: 'error', message: msg });
      appendLog(`✗ Error: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRebuildIndex = async () => {
    if (indexing) return;
    setIndexing(true);
    appendLog('Rebuilding vector + BM25 index…');
    try {
      const result = await apiRebuildIndex();
      setStatus({ type: 'success', message: `Index rebuilt — ${result.indexed_chunks} chunks indexed.` });
      appendLog(`✓ Index rebuilt: ${result.indexed_chunks} chunks.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Index rebuild failed';
      setStatus({ type: 'error', message: msg });
      appendLog(`✗ Error: ${msg}`);
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
      setStatus({ type: 'error', message: 'Only PDF files are supported.' });
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.topBar}>
        <span className={styles.title}>Ingest Sources</span>
      </div>

      <div className={styles.body}>
        {/* Mode toggle */}
        <div className={styles.modeToggle}>
          <button
            id="ingest-mode-url"
            className={`${styles.modeBtn} ${mode === 'url' ? styles.active : ''}`}
            onClick={() => { setMode('url'); setStatus(null); }}
          >⊕ Web URL</button>
          <button
            id="ingest-mode-file"
            className={`${styles.modeBtn} ${mode === 'file' ? styles.active : ''}`}
            onClick={() => { setMode('file'); setStatus(null); }}
          >⊕ PDF File</button>
        </div>

        {/* URL form */}
        {mode === 'url' && (
          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="ingest-url-input">Web URL</label>
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
            role="button"
            tabIndex={0}
            aria-label="PDF drop zone"
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
                <span>Drop PDF here or click to browse</span>
              </div>
            )}
          </div>
        )}

        {/* Source ID */}
        <div className={styles.formGroup}>
          <label className={styles.label} htmlFor="ingest-source-id">Source ID <span className={styles.optional}>(optional)</span></label>
          <input
            id="ingest-source-id"
            type="text"
            className={styles.input}
            placeholder="e.g. wikipedia, reuters, bloomberg"
            value={sourceId}
            onChange={e => setSourceId(e.target.value)}
            disabled={loading}
          />
          <p className={styles.hint}>Must match an ID in <code>configs/sources.yaml</code></p>
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
            {loading ? <><span className={styles.spinner} /> Ingesting…</> : '⊕ Ingest Document'}
          </button>
          <button
            id="ingest-index-btn"
            className={styles.secondaryBtn}
            onClick={handleRebuildIndex}
            disabled={indexing}
            aria-busy={indexing}
          >
            {indexing ? <><span className={styles.spinner} /> Indexing…</> : '⟳ Rebuild Index'}
          </button>
        </div>

        {/* Activity log */}
        {log.length > 0 && (
          <div className={styles.logBox}>
            <div className={styles.logHeader}>Activity Log</div>
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
