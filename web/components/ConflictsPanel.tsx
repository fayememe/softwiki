'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  apiAdjudicateConflict,
  apiKnowledgeMetrics,
  apiListConflicts,
  apiScanConflicts,
} from '@/lib/api';
import type { ConflictClaim, KnowledgeConflict, KnowledgeMetrics } from '@/lib/api';
import styles from './ConflictsPanel.module.css';

const ACTIONS: { id: string; label: string; danger?: boolean }[] = [
  { id: 'accept_a', label: 'Accept A' },
  { id: 'accept_b', label: 'Accept B' },
  { id: 'keep_both', label: 'Keep both' },
  { id: 'mark_error_a', label: 'A is error', danger: true },
  { id: 'mark_error_b', label: 'B is error', danger: true },
  { id: 'needs_evidence', label: 'Needs evidence' },
];

function ClaimSide({ label, claim }: { label: string; claim: ConflictClaim | null }) {
  if (!claim) return <div className={styles.claimSide}><span className={styles.claimLabel}>{label}</span><div className={styles.claimMissing}>Missing claim</div></div>;
  const pages = claim.page_start != null
    ? `p.${claim.page_start}${claim.page_end != null && claim.page_end !== claim.page_start ? `-${claim.page_end}` : ''}`
    : 'page unavailable';
  return (
    <div className={styles.claimSide}>
      <div className={styles.claimHead}>
        <span className={styles.claimLabel}>{label}</span>
        <span className={`${styles.claimStatus} ${claim.status === 'disputed' ? styles.statusDisputed : ''}`}>{claim.status}</span>
      </div>
      <div className={styles.claimText}>{claim.text}</div>
      <div className={styles.claimMeta}>
        <span>{claim.source_name || 'Unknown source'}</span>
        <span>{claim.published_at || 'unknown date'}</span>
        {claim.revision && <span>rev {claim.revision}</span>}
        <span>{pages}</span>
        {claim.subject && <span>{claim.subject}{claim.predicate ? ` · ${claim.predicate}` : ''}</span>}
        {claim.object && <span className={styles.valueChip}>{claim.object}</span>}
      </div>
    </div>
  );
}

export default function ConflictsPanel() {
  const [conflicts, setConflicts] = useState<KnowledgeConflict[]>([]);
  const [metrics, setMetrics] = useState<KnowledgeMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [acting, setActing] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [c, m] = await Promise.all([
        apiListConflicts(showAll ? undefined : 'open'),
        apiKnowledgeMetrics(),
      ]);
      setConflicts(c.conflicts || []);
      setMetrics(m);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conflicts');
    } finally {
      setLoading(false);
    }
  }, [showAll]);

  useEffect(() => { load(); }, [load]);

  const handleScan = async () => {
    setScanning(true);
    setError('');
    setNotice('');
    try {
      const result = await apiScanConflicts();
      setNotice(`Scan complete: ${result.canonical_claims} claims, ${result.pairs} pairs, ${result.created} new conflicts.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed');
    } finally {
      setScanning(false);
    }
  };

  const handleAction = async (id: number, action: string) => {
    const reason = window.prompt('Reason (optional):', '') || '';
    setActing(id);
    setError('');
    setNotice('');
    try {
      const result = await apiAdjudicateConflict(id, action, reason);
      setNotice(`Conflict #${id} ${result.status}; A=${result.claim_a}, B=${result.claim_b}. Wiki pages marked stale.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Adjudication failed');
    } finally {
      setActing(null);
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Knowledge Conflicts</h1>
          <p className={styles.subtitle}>
            Version updates are auto-superseded. Source conflicts require human adjudication.
            Adjudication writes claim status and marks affected wiki pages stale.
          </p>
        </div>
        <div className={styles.headerActions}>
          <label className={styles.toggle}>
            <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />
            Show auto-resolved / all
          </label>
          <button className={styles.scanBtn} onClick={handleScan} disabled={scanning || loading}>
            {scanning ? 'Scanning…' : 'Scan now'}
          </button>
        </div>
      </div>

      {metrics && (
        <div className={styles.metrics}>
          <div className={styles.metric}><span>{metrics.raw_claims.toLocaleString()}</span>raw claims</div>
          <div className={styles.metric}><span>{metrics.canonical_claims.toLocaleString()}</span>canonical claims</div>
          <div className={styles.metric}><span>{metrics.evidence.toLocaleString()}</span>evidence links</div>
          <div className={styles.metric}><span>{metrics.contradictions.open || 0}</span>open conflicts</div>
          <div className={styles.metric}><span>{metrics.contradictions.auto_resolved || 0}</span>auto-resolved</div>
          <div className={styles.metric}><span>{metrics.stale_wiki_artifacts}</span>stale wiki pages</div>
          <div className={styles.metric}><span>{metrics.relationships_linked || 0}/{metrics.relationships || 0}</span>graph links</div>
          <div className={styles.metric}><span>{metrics.events_linked || 0}/{metrics.events || 0}</span>timeline links</div>
          <div className={styles.metric}><span>{metrics.wiki_rebuild_tasks?.pending || 0}</span>wiki queue</div>
        </div>
      )}

      {error && <div className={styles.error}>{error}</div>}
      {notice && <div className={styles.notice}>{notice}</div>}

      {loading ? (
        <div className={styles.empty}>Loading conflicts…</div>
      ) : conflicts.length === 0 ? (
        <div className={styles.empty}>
          No {showAll ? '' : 'open '}conflicts. Run a scan after new documents are extracted.
        </div>
      ) : (
        <div className={styles.list}>
          {conflicts.map(c => (
            <div key={c.id} className={styles.card}>
              <div className={styles.cardHead}>
                <div className={styles.badges}>
                  <span className={styles.typeBadge}>{c.type}</span>
                  <span className={`${styles.severity} ${c.severity === 'high' ? styles.high : ''}`}>{c.severity}</span>
                  <span className={`${styles.cardStatus} ${c.status === 'open' ? styles.open : ''}`}>{c.status}</span>
                  {c.auto_resolved && <span className={styles.autoBadge}>auto</span>}
                </div>
                <span className={styles.conflictId}>#{c.id}</span>
              </div>
              <div className={styles.claims}>
                <ClaimSide label="A" claim={c.claim_a} />
                <ClaimSide label="B" claim={c.claim_b} />
              </div>
              {c.resolution && <div className={styles.resolution}>Resolution: {c.resolution}</div>}
              {c.status !== 'resolved' && c.status !== 'auto_resolved' && (
                <div className={styles.actions}>
                  {ACTIONS.map(a => (
                    <button
                      key={a.id}
                      className={`${styles.actionBtn} ${a.danger ? styles.danger : ''}`}
                      onClick={() => handleAction(c.id, a.id)}
                      disabled={acting === c.id}
                    >
                      {a.label}
                    </button>
                  ))}
                  <button
                    className={styles.actionBtn}
                    onClick={() => handleAction(c.id, 'reopen')}
                    disabled={acting === c.id}
                  >
                    Reopen
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
