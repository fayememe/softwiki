'use client';

/**
 * One-subject-per-page wiki browser.
 *
 * Renders the pages produced by softwiki/wiki/subject_pages.py: a searchable
 * index on the left, the generated markdown on the right. Subjects that exceed
 * the fixed page cap are split by the backend, and the split is shown, never
 * silently hidden — a page that covers 25 of 60 claims must say so.
 *
 * Design: docs/02-design/wiki-page-granularity.md
 */

import { useMemo, useState, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  apiBuildSubjectPage,
  apiGetSubjectPage,
  apiListSubjectPages,
} from '@/lib/api';
import type { SubjectPageEntry } from '@/lib/api';
import Pagination from './Pagination';
import styles from './WikiPagesPanel.module.css';

const TYPE_LABELS: Record<string, string> = {
  concept: 'Concept',
  organization: 'Organization',
  location: 'Location',
  person: 'Person',
  project: 'Project',
  country: 'Country',
  product: 'Product',
  event: 'Event',
};

function humanType(t?: string): string {
  if (!t) return 'Other';
  return TYPE_LABELS[t] || t.charAt(0).toUpperCase() + t.slice(1);
}

/** Strip the leading generator comment so it never reaches the rendered page. */
function stripMeta(raw: string): { body: string; meta: Record<string, string> } {
  const meta: Record<string, string> = {};
  if (!raw.startsWith('<!--')) return { body: raw, meta };
  const end = raw.indexOf('-->');
  if (end < 0) return { body: raw, meta };
  const head = raw.slice(4, end);
  for (const token of head.trim().split(/\s+/)) {
    const eq = token.indexOf('=');
    if (eq > 0) meta[token.slice(0, eq)] = token.slice(eq + 1);
  }
  return { body: raw.slice(end + 3).replace(/^\n+/, ''), meta };
}

export default function WikiPagesPanel() {
  const [subjects, setSubjects] = useState<SubjectPageEntry[]>([]);
  const [candidates, setCandidates] = useState<SubjectPageEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [limit, setLimit] = useState(25);
  const [generated, setGenerated] = useState(false);

  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const [selected, setSelected] = useState<SubjectPageEntry | null>(null);
  const [activeSlug, setActiveSlug] = useState('');
  const [body, setBody] = useState('');
  const [meta, setMeta] = useState<Record<string, string>>({});
  const [pageLoading, setPageLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [reconciling, setReconciling] = useState(false);
  const [queuePending, setQueuePending] = useState<number | null>(null);

  const loadIndex = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiListSubjectPages(false);
      setLimit(data.limit);
      setGenerated(data.generated);
      const list = data.subjects?.length ? data.subjects : (data.candidates || []);
      setSubjects(list);
      setCandidates(data.candidates || []);
      if (!data.generated && (data.candidates?.length ?? 0) > 0) {
        setNotice(
          `No pages generated yet. ${data.candidate_count} subjects are ready — ` +
          `pick one and press Generate.`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load wiki pages');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadIndex();
  }, [loadIndex]);

  /** Ask the backend to queue the first batch (or the changed subjects). */
  const startGeneration = useCallback(async () => {
    setReconciling(true);
    setError('');
    setNotice('');
    try {
      const res = await fetch('/api/wiki/reconcile', { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      const n = data.enqueued ?? 0;
      setNotice(
        n > 0
          ? `Queued ${n} page(s). They appear here as they finish.`
          : 'Nothing to queue — every subject is already up to date.',
      );
      // Poll the queue so the list fills in without the user reloading.
      for (let i = 0; i < 60 && n > 0; i += 1) {
        await new Promise((r) => setTimeout(r, 3000));
        const q = await fetch('/api/wiki/rebuild-tasks', { cache: 'no-store' })
          .then((r) => r.json())
          .catch(() => null);
        const pending = q?.counts?.pending;
        if (typeof pending === 'number') {
          setQueuePending(pending);
          if (pending === 0) break;
        }
        await loadIndex();
      }
      await loadIndex();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start generation');
    } finally {
      setReconciling(false);
      setQueuePending(null);
    }
  }, [loadIndex]);

  const openPage = useCallback(async (slug: string) => {
    setPageLoading(true);
    setError('');
    setActiveSlug(slug);
    try {
      const page = await apiGetSubjectPage(slug);
      const parsed = stripMeta(page.content);
      setBody(parsed.body);
      setMeta({ ...page.meta, ...parsed.meta });
    } catch (e) {
      setBody('');
      setError(e instanceof Error ? e.message : 'Failed to open page');
    } finally {
      setPageLoading(false);
    }
  }, []);

  const selectSubject = useCallback((entry: SubjectPageEntry) => {
    setSelected(entry);
    setNotice('');
    if (entry.pages?.length) {
      void openPage(entry.pages[0]);
    } else {
      setBody('');
      setMeta({});
      setActiveSlug('');
    }
  }, [openPage]);

  const handleBuild = useCallback(async () => {
    if (!selected) return;
    setBuilding(true);
    setError('');
    setNotice('');
    try {
      const res = await apiBuildSubjectPage(selected.subject);
      setNotice(
        `Generated ${res.pages.length} page(s) for "${res.subject}" ` +
        `covering ${res.claims_total} claims.`,
      );
      await loadIndex();
      const first = res.pages[0] as unknown as SubjectPageEntry;
      if (first?.slug) await openPage(first.slug);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setBuilding(false);
    }
  }, [selected, loadIndex, openPage]);

  const types = useMemo(() => {
    const seen = new Map<string, number>();
    for (const s of subjects) {
      const t = humanType(s.type);
      seen.set(t, (seen.get(t) || 0) + 1);
    }
    return [...seen.entries()].sort((a, b) => b[1] - a[1]);
  }, [subjects]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return subjects
      .filter((s) => (typeFilter ? humanType(s.type) === typeFilter : true))
      .filter((s) => (q ? s.subject.toLowerCase().includes(q) : true))
      .sort((a, b) => (b.claims_total || 0) - (a.claims_total || 0));
  }, [subjects, query, typeFilter]);

  // The index can hold hundreds of subjects: page it so the sidebar stays fast.
  useEffect(() => { setPage(1); }, [query, typeFilter]);
  const pagedSubjects = useMemo(() => {
    const start = (page - 1) * pageSize;
    return visible.slice(start, start + pageSize);
  }, [visible, page, pageSize]);

  const covered = meta.claims_covered ? Number(meta.claims_covered) : null;
  const total = meta.claims_total ? Number(meta.claims_total) : null;
  const isPartial = covered !== null && total !== null && covered < total;

  return (
    <div className={styles.panel}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHead}>
          <h2 className={styles.title}>Wiki Pages</h2>
          <div className={styles.subtitle}>
            {loading ? 'Loading…' : `${subjects.length} subject${subjects.length === 1 ? '' : 's'}`}
            {!generated && !loading ? ' · not generated yet' : ''}
          </div>
          <span className={styles.limitPill}>{limit} claims / page max</span>
        </div>

        <div className={styles.searchWrap}>
          <input
            className={styles.search}
            type="search"
            placeholder="Search subjects…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search subjects"
          />
        </div>

        {types.length > 1 && (
          <div className={styles.filters}>
            <button
              className={`${styles.chip} ${typeFilter === null ? styles.chipActive : ''}`}
              onClick={() => setTypeFilter(null)}
            >
              All {subjects.length}
            </button>
            {types.map(([t, n]) => (
              <button
                key={t}
                className={`${styles.chip} ${typeFilter === t ? styles.chipActive : ''}`}
                onClick={() => setTypeFilter(t === typeFilter ? null : t)}
              >
                {t} {n}
              </button>
            ))}
          </div>
        )}

        <div className={styles.list}>
          {loading && <div className={styles.empty}>Loading pages…</div>}
          {!loading && visible.length === 0 && (
            <div className={styles.empty}>
              {subjects.length === 0
                ? 'No pages yet. Run a generation, or open a page from the candidates.'
                : 'No subject matches this filter.'}
            </div>
          )}
          {pagedSubjects.map((s) => (
            <button
              key={s.slug}
              className={`${styles.item} ${selected?.slug === s.slug ? styles.itemActive : ''}`}
              onClick={() => selectSubject(s)}
              title={`${s.subject} — ${s.claims_total} claims`}
            >
              <div className={styles.itemRow}>
                <span className={styles.itemName}>{s.subject}</span>
                <span className={styles.itemMeta}>
                  {s.claims_total}
                  {s.needs_split && <span className={styles.splitTag}>split</span>}
                </span>
              </div>
            </button>
          ))}
        </div>
        {!loading && visible.length > 0 && (
          <Pagination
            page={page}
            pageSize={pageSize}
            total={visible.length}
            onPageChange={setPage}
            onPageSizeChange={(n) => { setPageSize(n); setPage(1); }}
            pageSizeOptions={[25, 50, 100]}
          />
        )}
      </aside>

      <main className={styles.main}>
        {selected && (
          <div className={styles.mainHead}>
            <span className={styles.mainTitle}>{selected.subject}</span>
            <span className={styles.badge}>{humanType(selected.type)}</span>
            {covered !== null && total !== null && (
              <span className={`${styles.badge} ${isPartial ? styles.badgeWarn : styles.badgeOk}`}>
                {covered}/{total} claims
              </span>
            )}
            <button
              className={styles.buildBtn}
              onClick={handleBuild}
              disabled={building || pageLoading}
            >
              {building ? 'Generating…' : selected.pages?.length ? 'Regenerate' : 'Generate'}
            </button>
          </div>
        )}

        {selected && (selected.pages?.length ?? 0) > 1 && (
          <div className={styles.parts}>
            <span style={{ color: '#72777d' }}>
              Split into {selected.pages!.length} parts (limit {limit}/page):
            </span>
            {selected.pages!.map((slug, i) => (
              <button
                key={slug}
                className={`${styles.partLink} ${activeSlug === slug ? styles.partLinkActive : ''}`}
                onClick={() => void openPage(slug)}
              >
                Part {i + 1}
              </button>
            ))}
          </div>
        )}

        {!generated && !loading && (
          <div className={styles.notice}>
            <strong>This knowledge base has no generated pages yet.</strong>{' '}
            {candidates.length > 0
              ? `${candidates.length} subjects are ready. Start with the top 20 — you can generate more later.`
              : 'Ingest documents first; subjects come from the claims.'}{' '}
            {candidates.length > 0 && (
              <button className={styles.buildBtn} disabled={reconciling} onClick={startGeneration}>
                {reconciling
                  ? queuePending !== null
                    ? `Generating… ${queuePending} queued`
                    : 'Starting…'
                  : 'Start generation'}
              </button>
            )}
          </div>
        )}
        {notice && <div className={styles.notice}>{notice}</div>}
        {error && <div className={styles.error}>{error}</div>}

        {!selected && (
          <div className={styles.placeholder}>
            <strong>One page per subject</strong>
            <span>
              Pick a subject on the left. Each page is compiled from at most {limit}{' '}
              claims; larger subjects are split so nothing is silently dropped.
            </span>
          </div>
        )}

        {selected && pageLoading && (
          <div className={styles.placeholder}>Loading page…</div>
        )}

        {selected && !pageLoading && body && (
          <article className={styles.content}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
          </article>
        )}

        {selected && !pageLoading && !body && !error && (
          <div className={styles.placeholder}>
            <strong>Not generated yet</strong>
            <span>
              This subject has {selected.claims_total} claims. Press Generate to compile
              {selected.needs_split ? ' — it will be split across several pages.' : '.'}
            </span>
          </div>
        )}
      </main>
    </div>
  );
}
