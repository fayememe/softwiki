'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  apiAdjudicateConflict,
  apiKnowledgeMetrics,
  apiCanonicalEvidence,
  apiListConflicts,
  apiScanConflicts,
} from '@/lib/api';
import type { CanonicalEvidence, ConflictClaim, KnowledgeConflict, KnowledgeMetrics } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './ConflictsPanel.module.css';

const ACTIONS: { id: string; label: string; danger?: boolean }[] = [
  { id: 'accept_a', label: 'conflicts.actionAcceptA' },
  { id: 'accept_b', label: 'conflicts.actionAcceptB' },
  { id: 'keep_both', label: 'conflicts.actionKeepBoth' },
  { id: 'mark_error_a', label: 'conflicts.actionErrorA', danger: true },
  { id: 'mark_error_b', label: 'conflicts.actionErrorB', danger: true },
  { id: 'needs_evidence', label: 'conflicts.actionNeedsEvidence' },
];

function ClaimSide({ label, claim, onEvidence }: { label: string; claim: ConflictClaim | null; onEvidence?: (c: ConflictClaim) => void }) {
  const t = useT();
  if (!claim) return <div className={styles.claimSide}><span className={styles.claimLabel}>{label}</span><div className={styles.claimMissing}>{t('conflicts.missingClaim')}</div></div>;
  const pages = claim.page_start != null
    ? `p.${claim.page_start}${claim.page_end != null && claim.page_end !== claim.page_start ? `-${claim.page_end}` : ''}`
    : t('conflicts.pageUnavailable');
  return (
    <div className={styles.claimSide}>
      <div className={styles.claimHead}>
        <span className={styles.claimLabel}>{label}</span>
        <span className={`${styles.claimStatus} ${claim.status === 'disputed' ? styles.statusDisputed : ''}`}>{claim.status}</span>
        {onEvidence && <button className={styles.evidenceBtn} onClick={() => onEvidence(claim)}>{t('conflicts.evidence')}</button>}
      </div>
      <div className={styles.claimText}>{claim.text}</div>
      <div className={styles.claimMeta}>
        <span>{claim.source_name || t('conflicts.unknownSource')}</span>
        <span>{claim.published_at || t('conflicts.unknownDate')}</span>
        {claim.revision && <span>{t('conflicts.rev', { n: claim.revision })}</span>}
        <span>{pages}</span>
        {claim.subject && <span>{claim.subject}{claim.predicate ? ` · ${claim.predicate}` : ''}</span>}
        {claim.object && <span className={styles.valueChip}>{claim.object}</span>}
      </div>
    </div>
  );
}

export default function ConflictsPanel() {
  const t = useT();
  const [conflicts, setConflicts] = useState<KnowledgeConflict[]>([]);
  const [metrics, setMetrics] = useState<KnowledgeMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [acting, setActing] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showAll, setShowAll] = useState(false);
  const [evidence, setEvidence] = useState<{ claimId: string; rows: CanonicalEvidence[] } | null>(null);

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
      setError(err instanceof Error ? err.message : t('conflicts.errLoad'));
    } finally {
      setLoading(false);
    }
  }, [showAll, t]);

  useEffect(() => { load(); }, [load]);

  const handleScan = async () => {
    setScanning(true);
    setError('');
    setNotice('');
    try {
      const result = await apiScanConflicts();
      setNotice(t('conflicts.scanDone', {
        claims: result.canonical_claims,
        pairs: result.pairs,
        created: result.created,
      }));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('conflicts.errScan'));
    } finally {
      setScanning(false);
    }
  };

  const showEvidence = async (claim: ConflictClaim) => {
    try {
      const data = await apiCanonicalEvidence(claim.id);
      setEvidence({ claimId: claim.id, rows: data.evidence || [] });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('conflicts.errEvidence'));
    }
  };

  const handleAction = async (id: number, action: string) => {
    const reason = window.prompt(t('conflicts.reasonPrompt'), '') || '';
    setActing(id);
    setError('');
    setNotice('');
    try {
      const result = await apiAdjudicateConflict(id, action, reason);
      setNotice(t('conflicts.adjudicated', {
        id,
        status: result.status,
        a: result.claim_a,
        b: result.claim_b,
      }));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('conflicts.errAdjudicate'));
    } finally {
      setActing(null);
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{t('conflicts.title')}</h1>
          <p className={styles.subtitle}>
            {t('conflicts.subtitle')}
          </p>
        </div>
        <div className={styles.headerActions}>
          <label className={styles.toggle}>
            <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />
            {t('conflicts.showAll')}
          </label>
          <button className={styles.scanBtn} onClick={handleScan} disabled={scanning || loading}>
            {scanning ? t('conflicts.scanning') : t('conflicts.scan')}
          </button>
        </div>
      </div>

      {metrics && (
        <div className={styles.metrics}>
          <div className={styles.metric}><span>{metrics.raw_claims.toLocaleString()}</span>{t('conflicts.metricRawClaims')}</div>
          <div className={styles.metric}><span>{metrics.canonical_claims.toLocaleString()}</span>{t('conflicts.metricCanonicalClaims')}</div>
          <div className={styles.metric}><span>{metrics.evidence.toLocaleString()}</span>{t('conflicts.metricEvidence')}</div>
          <div className={styles.metric}><span>{metrics.contradictions.open || 0}</span>{t('conflicts.metricOpen')}</div>
          <div className={styles.metric}><span>{metrics.contradictions.auto_resolved || 0}</span>{t('conflicts.metricAutoResolved')}</div>
          <div className={styles.metric}><span>{metrics.stale_wiki_artifacts}</span>{t('conflicts.metricStaleWiki')}</div>
          <div className={styles.metric}><span>{metrics.relationships_linked || 0}/{metrics.relationships || 0}</span>{t('conflicts.metricGraphLinks')}</div>
          <div className={styles.metric}><span>{metrics.events_linked || 0}/{metrics.events || 0}</span>{t('conflicts.metricTimelineLinks')}</div>
          <div className={styles.metric}><span>{metrics.wiki_rebuild_tasks?.pending || 0}</span>{t('conflicts.metricWikiQueue')}</div>
        </div>
      )}

      {error && <div className={styles.error}>{error}</div>}
      {notice && <div className={styles.notice}>{notice}</div>}

      {loading ? (
        <div className={styles.empty}>{t('conflicts.loading')}</div>
      ) : conflicts.length === 0 ? (
        <div className={styles.empty}>
          {showAll ? t('conflicts.emptyAll') : t('conflicts.emptyOpen')}
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
                  {c.auto_resolved && <span className={styles.autoBadge}>{t('conflicts.auto')}</span>}
                </div>
                <span className={styles.conflictId}>#{c.id}</span>
              </div>
              <div className={styles.claims}>
                <ClaimSide label="A" claim={c.claim_a} onEvidence={showEvidence} />
                <ClaimSide label="B" claim={c.claim_b} onEvidence={showEvidence} />
              </div>
              {evidence && (c.claim_a?.id === evidence.claimId || c.claim_b?.id === evidence.claimId) && (
                <div className={styles.evidenceBox}>
                  <div className={styles.evidenceHead}>{t('conflicts.evidenceFor', { id: evidence.claimId })}</div>
                  {evidence.rows.length === 0 ? <div className={styles.claimMeta}>{t('conflicts.noEvidence')}</div> : evidence.rows.map(e => (
                    <div key={e.id} className={styles.evidenceRow}>
                      <div className={styles.claimMeta}>
                        <span>{e.source_name || t('conflicts.unknownSource')}</span>
                        <span>{e.published_at || t('conflicts.unknownDate')}</span>
                        {e.source_revision && <span>{t('conflicts.rev', { n: e.source_revision })}</span>}
                        <span>{e.page_start != null ? `p.${e.page_start}${e.page_end && e.page_end !== e.page_start ? `-${e.page_end}` : ''}` : t('conflicts.pageUnavailable')}</span>
                      </div>
                      {e.quote && <div className={styles.evidenceQuote}>{e.quote}</div>}
                    </div>
                  ))}
                </div>
              )}
              {c.resolution && <div className={styles.resolution}>{t('conflicts.resolution', { text: c.resolution })}</div>}
              {c.status !== 'resolved' && c.status !== 'auto_resolved' && (
                <div className={styles.actions}>
                  {ACTIONS.map(a => (
                    <button
                      key={a.id}
                      className={`${styles.actionBtn} ${a.danger ? styles.danger : ''}`}
                      onClick={() => handleAction(c.id, a.id)}
                      disabled={acting === c.id}
                    >
                      {t(a.label)}
                    </button>
                  ))}
                  <button
                    className={styles.actionBtn}
                    onClick={() => handleAction(c.id, 'reopen')}
                    disabled={acting === c.id}
                  >
                    {t('conflicts.reopen')}
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
