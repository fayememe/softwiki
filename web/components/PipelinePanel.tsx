'use client';

/**
 * Pipeline status for the active knowledge base.
 *
 * The point is to make the generation chain explicit: a kb is not one thing
 * being "built", it is several artifacts with different triggers and staleness.
 *
 *   documents ──extract──> claims ──project──> graph / timeline
 *       │                     └──────compose──> wiki pages ──publish──> static portal
 *       └──chunk/embed──> retrieval index (chunks + vectors + BM25)
 *
 * Each card reports its own state and links to the action that moves it
 * forward. Buttons are only enabled when the action exists today.
 */

import { useCallback, useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';
import { API_BASE } from '@/lib/api';
import type { ActivePanel } from './Sidebar';
import styles from './PipelinePanel.module.css';

interface Pipeline {
  kb: string;
  documents: {
    total: number;
    by_status: Record<string, number>;
    unfinished: number;
    without_chunks: number;
    without_claims: number;
    without_relationships: number;
    oldest_unfinished: string | null;
  };
  index: {
    chunks: number;
    vectors: number | null;
    vector_backend: string;
    bm25_built_at: string | null;
    stale: boolean;
  };
  claims: { raw: number; canonical: number; disputed: number; running: boolean };
  graph: { entities: number; relationships: number; unprojected: number; stale: boolean };
  timeline: { events: number; unprojected: number; stale: boolean };
  wiki: {
    generated: boolean;
    subject_pages: number;
    stale: number;
    tasks: Record<string, number>;
    running: boolean;
    built_at: string | null;
  };
  portal: { exists: boolean; built_at: string | null; pages: number; stale: boolean };
  generated_at: string;
}

type StageState = 'ok' | 'running' | 'stale' | 'empty' | 'warn';

export default function PipelinePanel({ onNavigate }: { onNavigate?: (panel: ActivePanel) => void }) {
  const t = useT();
  const [data, setData] = useState<Pipeline | null>(null);
  const [error, setError] = useState('');
  const [rebuilding, setRebuilding] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/kb/pipeline`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Poll faster while something is actually generating.
  const busy = Boolean(data && (data.wiki.running || data.claims.running || data.documents.unfinished > 0));
  useEffect(() => {
    const timer = setInterval(() => { void load(); }, busy ? 5000 : 30000);
    return () => clearInterval(timer);
  }, [busy, load]);

  const rebuildIndex = useCallback(async () => {
    if (rebuilding) return;
    const ok = window.confirm(t('pipeline.rebuildConfirm'));
    if (!ok) return;
    setRebuilding(true);
    setNotice('');
    try {
      const res = await fetch(`${API_BASE}/api/index`, { method: 'POST' });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      setNotice(t('pipeline.rebuildDone', { n: body.indexed_chunks ?? 0 }));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRebuilding(false);
    }
  }, [load, rebuilding, t]);

  const resumeExtraction = useCallback(async () => {
    if (resuming) return;
    setResuming(true);
    setNotice('');
    try {
      const res = await fetch(`${API_BASE}/api/kb/extract-pending?limit=10`, { method: 'POST' });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      setNotice(t('pipeline.resumeDone', { n: body.count ?? 0 }));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setResuming(false);
    }
  }, [load, resuming, t]);

  const chip = (state: StageState, label?: string) => (
    <span className={`${styles.chip} ${styles[`chip_${state}`]}`}>{label ?? t(`pipeline.state_${state}`)}</span>
  );

  const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : t('pipeline.never'));

  if (error && !data) {
    return <div className={styles.panel}><p className={styles.error}>{error}</p></div>;
  }
  if (!data) {
    return <div className={styles.panel}><p className={styles.muted}>{t('pipeline.loading')}</p></div>;
  }

  const docState: StageState =
    data.documents.total === 0 ? 'empty'
      : data.documents.unfinished > 0 ? 'running'
        : 'ok';

  const indexState: StageState =
    data.index.stale ? 'stale' : data.index.chunks === 0 ? 'empty' : 'ok';

  const claimState: StageState =
    data.claims.running ? 'running'
      : data.claims.canonical === 0 ? (data.documents.total ? 'stale' : 'empty')
        : 'ok';

  const graphState: StageState =
    data.graph.stale ? 'stale' : data.graph.unprojected > 0 ? 'warn' : data.graph.relationships ? 'ok' : 'empty';

  const timelineState: StageState =
    data.timeline.stale ? 'stale' : data.timeline.unprojected > 0 ? 'warn' : data.timeline.events ? 'ok' : 'empty';

  const wikiState: StageState =
    data.wiki.running ? 'running' : data.wiki.stale > 0 ? 'stale' : data.wiki.generated ? 'ok' : 'empty';

  const portalState: StageState =
    data.portal.stale ? 'stale' : data.portal.exists ? 'ok' : 'empty';

  return (
    <div className={styles.panel}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>{t('pipeline.title')}</h1>
          <p className={styles.subtitle}>
            {data.kb} · {t('pipeline.subtitle')}
            {busy ? <span className={styles.live}> · {t('pipeline.live')}</span> : null}
          </p>
        </div>
        <button className={styles.ghostBtn} onClick={() => void load()}>{t('pipeline.refresh')}</button>
      </header>

      {error ? <p className={styles.error}>{error}</p> : null}
      {notice ? <p className={styles.notice}>{notice}</p> : null}

      {/* Branch 1 — retrieval */}
      <section className={styles.branch}>
        <div className={styles.branchLabel}>{t('pipeline.branchRetrieval')}</div>
        <div className={styles.branchHint}>{t('pipeline.branchRetrievalHint')}</div>
        <div className={styles.row}>
          <article className={`${styles.card} ${styles.cardDoc}`}>
            <div className={styles.cardHead}>
              <span className={styles.cardName}>{t('pipeline.documents')}</span>
              {chip(docState)}
            </div>
            <div className={styles.metrics}>
              <span><strong>{data.documents.total}</strong> {t('pipeline.docsTotal')}</span>
              {data.documents.unfinished > 0 && (
                <span className={styles.warnText}>{t('pipeline.docsPending', { n: data.documents.unfinished })}</span>
              )}
            </div>
            <div className={styles.cardActions}>
              <button className={styles.cardBtn} onClick={() => onNavigate?.('ingest')}>{t('pipeline.goIngest')}</button>
              {data.documents.unfinished > 0 && (
                <button className={styles.cardBtn} onClick={() => void resumeExtraction()} disabled={resuming}>
                  {resuming ? t('pipeline.resuming') : t('pipeline.resumeExtraction')}
                </button>
              )}
            </div>
          </article>

          <div className={styles.arrow}>
            <span>{t('pipeline.arrowChunk')}</span>
            <i>→</i>
          </div>

          <article className={`${styles.card} ${styles.cardIndex}`}>
            <div className={styles.cardHead}>
              <span className={styles.cardName}>{t('pipeline.index')}</span>
              {chip(indexState)}
            </div>
            <div className={styles.metrics}>
              <span><strong>{data.index.chunks.toLocaleString()}</strong> {t('pipeline.chunks')}</span>
              <span>
                {data.index.vector_backend === 'pg'
                  ? `${data.index.vectors?.toLocaleString() ?? '—'} ${t('pipeline.vectors')}`
                  : t('pipeline.vectorsFile')}
              </span>
              <span>{t('pipeline.bm25At')}: {fmtDate(data.index.bm25_built_at)}</span>
            </div>
            {data.index.stale && (
              <p className={styles.hint}>{t('pipeline.indexStaleHint', { n: data.documents.without_chunks })}</p>
            )}
            <button
              className={styles.cardBtn}
              onClick={() => void rebuildIndex()}
              disabled={rebuilding}
            >
              {rebuilding ? t('pipeline.rebuilding') : t('pipeline.rebuildIndex')}
            </button>
          </article>
        </div>
      </section>

      {/* Branch 2 — knowledge */}
      <section className={styles.branch}>
        <div className={styles.branchLabel}>{t('pipeline.branchKnowledge')}</div>
        <div className={styles.branchHint}>{t('pipeline.branchKnowledgeHint')}</div>
        <div className={styles.row}>
          <article className={`${styles.card} ${styles.cardClaims}`}>
            <div className={styles.cardHead}>
              <span className={styles.cardName}>{t('pipeline.claims')}</span>
              {chip(claimState)}
            </div>
            <div className={styles.metrics}>
              <span><strong>{data.claims.canonical.toLocaleString()}</strong> {t('pipeline.canonical')}</span>
              <span>{data.claims.raw.toLocaleString()} {t('pipeline.rawClaims')}</span>
              {data.claims.disputed > 0 && (
                <span className={styles.warnText}>{data.claims.disputed} {t('pipeline.disputed')}</span>
              )}
            </div>
            <button className={styles.cardBtn} onClick={() => onNavigate?.('claims')}>{t('pipeline.view')}</button>
          </article>

          <div className={styles.arrow}>
            <span>{t('pipeline.arrowProject')}</span>
            <i>→</i>
          </div>

          <div className={styles.dual}>
            <article className={`${styles.card} ${styles.cardGraph}`}>
              <div className={styles.cardHead}>
                <span className={styles.cardName}>{t('pipeline.graph')}</span>
                {chip(graphState)}
              </div>
              <div className={styles.metrics}>
                <span><strong>{data.graph.entities.toLocaleString()}</strong> {t('pipeline.entities')}</span>
                <span><strong>{data.graph.relationships.toLocaleString()}</strong> {t('pipeline.relationships')}</span>
                {data.graph.unprojected > 0 && (
                  <span className={styles.warnText}>{data.graph.unprojected} {t('pipeline.unprojected')}</span>
                )}
              </div>
              <button className={styles.cardBtn} onClick={() => onNavigate?.('graph')}>{t('pipeline.view')}</button>
            </article>

            <article className={`${styles.card} ${styles.cardTimeline}`}>
              <div className={styles.cardHead}>
                <span className={styles.cardName}>{t('pipeline.timeline')}</span>
                {chip(timelineState)}
              </div>
              <div className={styles.metrics}>
                <span><strong>{data.timeline.events.toLocaleString()}</strong> {t('pipeline.events')}</span>
                {data.timeline.unprojected > 0 && (
                  <span className={styles.warnText}>{data.timeline.unprojected} {t('pipeline.unprojected')}</span>
                )}
              </div>
              <button className={styles.cardBtn} onClick={() => onNavigate?.('timeline')}>{t('pipeline.view')}</button>
            </article>
          </div>
        </div>
      </section>

      {/* Branch 3 — publishing */}
      <section className={styles.branch}>
        <div className={styles.branchLabel}>{t('pipeline.branchPublish')}</div>
        <div className={styles.branchHint}>{t('pipeline.branchPublishHint')}</div>
        <div className={styles.row}>
          <article className={`${styles.card} ${styles.cardWiki}`}>
            <div className={styles.cardHead}>
              <span className={styles.cardName}>{t('pipeline.wiki')}</span>
              {chip(wikiState)}
            </div>
            <div className={styles.metrics}>
              <span><strong>{data.wiki.subject_pages.toLocaleString()}</strong> {t('pipeline.subjectPages')}</span>
              {data.wiki.stale > 0 && (
                <span className={styles.warnText}>{data.wiki.stale} {t('pipeline.wikiStale')}</span>
              )}
              {data.wiki.running && (
                <span className={styles.roomText}>
                  {t('pipeline.wikiQueue', {
                    pending: data.wiki.tasks.pending ?? 0,
                    running: data.wiki.tasks.running ?? 0,
                    failed: data.wiki.tasks.failed ?? 0,
                  })}
                </span>
              )}
              <span>{t('pipeline.builtAt')}: {fmtDate(data.wiki.built_at)}</span>
            </div>
            <button className={styles.cardBtn} onClick={() => onNavigate?.('wikiweb')}>{t('pipeline.goWiki')}</button>
          </article>

          <div className={styles.arrow}>
            <span>{t('pipeline.arrowPublish')}</span>
            <i>→</i>
          </div>

          <article className={`${styles.card} ${styles.cardPortal}`}>
            <div className={styles.cardHead}>
              <span className={styles.cardName}>{t('pipeline.portal')}</span>
              {chip(portalState)}
            </div>
            <div className={styles.metrics}>
              <span><strong>{data.portal.pages.toLocaleString()}</strong> {t('pipeline.portalPages')}</span>
              <span>{t('pipeline.builtAt')}: {fmtDate(data.portal.built_at)}</span>
            </div>
            {data.portal.stale && (
              <p className={styles.hint}>{t('pipeline.portalStaleHint')}</p>
            )}
            <button className={styles.cardBtn} onClick={() => onNavigate?.('wikiweb')}>{t('pipeline.openPortal')}</button>
          </article>
        </div>
      </section>

      <p className={styles.footer}>
        {t('pipeline.updatedAt')} {fmtDate(data.generated_at)}
      </p>
    </div>
  );
}
