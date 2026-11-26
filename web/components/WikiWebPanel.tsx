'use client';

/**
 * Wiki panel: the published portal and the generation surface, in one place.
 *
 * Two tabs:
 *   - Portal: the static snapshot served from `<workspace>/exports/wikiweb/`
 *     under `/wikiweb`, embedded so the app chrome stays visible, with an
 *     explicit "open in new tab" escape hatch.
 *   - Pages: the per-subject wiki pages and the agent-proposed change plans
 *     (`/api/wiki/plans`), i.e. the place where generation is driven.
 *
 * The right rail is the control surface. Rebuilding the static portal is still
 * a script (`scripts/wikiweb_build.py`) that also requires a web restart, so
 * that button stays disabled and says so — no fake success states.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useT } from '@/lib/i18n';
import WikiPagesPanel from './WikiPagesPanel';
import styles from './WikiWebPanel.module.css';

type Tab = 'portal' | 'pages';

/** Right rail sizing: drag the divider, double-click to reset, remembered locally. */
const RAIL_DEFAULT = 300;
const RAIL_MIN = 240;
const RAIL_MAX = 720;
const RAIL_KEY = 'softwiki_wiki_rail_width';

interface PortalState {
  generated: boolean | null;
  subjects: number | null;
}

export default function WikiWebPanel({ onOpenAssistant }: { onOpenAssistant?: () => void }) {
  const t = useT();
  const [tab, setTab] = useState<Tab>('portal');
  const [kb, setKb] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [portal, setPortal] = useState<PortalState>({ generated: null, subjects: null });
  const [railWidth, setRailWidth] = useState(RAIL_DEFAULT);
  const [railDragging, setRailDragging] = useState(false);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);
  // Double-tap detection is done by hand: taking pointer capture makes Chrome
  // unreliable about synthesising `dblclick` on the handle.
  const lastTapRef = useRef(0);
  const dragStartXRef = useRef(0);

  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(RAIL_KEY));
      if (Number.isFinite(saved) && saved >= RAIL_MIN) setRailWidth(Math.min(RAIL_MAX, saved));
    } catch {
      /* storage disabled: keep the default */
    }
  }, []);

  const applyRailWidth = useCallback((clientX: number) => {
    const body = bodyRef.current;
    if (!body) return;
    const rect = body.getBoundingClientRect();
    // Leave at least 320px for the portal preview.
    const maxForWidth = Math.max(RAIL_MIN, Math.min(RAIL_MAX, rect.width - 320));
    setRailWidth(Math.min(maxForWidth, Math.max(RAIL_MIN, rect.right - clientX)));
  }, []);

  const endRailDrag = useCallback(() => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    setRailDragging(false);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  // Safety net: if the capture is lost (window loses focus, pointer leaves the
  // window), the drag must still end.
  useEffect(() => {
    window.addEventListener('pointerup', endRailDrag);
    window.addEventListener('pointercancel', endRailDrag);
    return () => {
      window.removeEventListener('pointerup', endRailDrag);
      window.removeEventListener('pointercancel', endRailDrag);
    };
  }, [endRailDrag]);

  // Persist a settled width (not every animation frame of the drag).
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(RAIL_KEY, String(railWidth));
      } catch {
        /* ignore */
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [railWidth]);

  useEffect(() => {
    fetch('/api/kb', { cache: 'no-store' })
      .then(r => r.json())
      .then(d => setKb(d.active || d.kbs?.[0]?.name || ''))
      .catch(() => setKb(''));
  }, []);

  useEffect(() => {
    fetch('/api/wiki/pages', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (!d) return;
        setPortal({
          generated: Boolean(d.generated),
          subjects: Array.isArray(d.subjects) ? d.subjects.length : null,
        });
      })
      .catch(() => {});
  }, [tab]);

  const reload = useCallback(() => setReloadKey(k => k + 1), []);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <h1 className={styles.title}>{t('wikiweb.title')}</h1>
          <div className={styles.tabs} role="tablist">
            <button
              role="tab"
              aria-selected={tab === 'portal'}
              className={`${styles.tab} ${tab === 'portal' ? styles.tabActive : ''}`}
              onClick={() => setTab('portal')}
            >
              {t('wikiweb.tabPortal')}
            </button>
            <button
              role="tab"
              aria-selected={tab === 'pages'}
              className={`${styles.tab} ${tab === 'pages' ? styles.tabActive : ''}`}
              onClick={() => setTab('pages')}
            >
              {t('wikiweb.tabPages')}
            </button>
          </div>
        </div>
        <div className={styles.actions}>
          {tab === 'portal' && (
            <button className={styles.ghostBtn} onClick={reload} title={t('wikiweb.reload')}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12a9 9 0 1 1-3-6.7" /><polyline points="21 3 21 9 15 9" />
              </svg>
              {t('wikiweb.reload')}
            </button>
          )}
          <a className={styles.primaryBtn} href="/wikiweb" target="_blank" rel="noopener noreferrer">
            {t('wikiweb.openExternal')}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
        </div>
      </header>

      <div className={styles.body} ref={bodyRef} data-dragging={railDragging ? 'true' : undefined}>
        {tab === 'pages' ? (
          <div className={styles.pagesPane}>
            <WikiPagesPanel />
          </div>
        ) : (
          <>
            <div className={styles.frameWrap}>
              <iframe
                key={reloadKey}
                className={styles.frame}
                src="/wikiweb"
                title={t('wikiweb.title')}
              />
            </div>

            <div
              className={styles.railResizer}
              role="separator"
              aria-orientation="vertical"
              aria-label={t('wikiweb.resizeRail')}
              title={t('wikiweb.resizeRail')}
              onPointerDown={(event) => {
                // No preventDefault here: it also cancels the compatibility
                // click/dblclick events, which is what the reset gesture uses.
                // Selection is suppressed with user-select instead.
                // Pointer capture matters, though: without it the moves go to
                // the portal <iframe> as soon as the cursor crosses it and the
                // drag silently freezes at the starting width.
                event.currentTarget.setPointerCapture(event.pointerId);
                draggingRef.current = true;
                dragStartXRef.current = event.clientX;
                setRailDragging(true);
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';
              }}
              onPointerMove={(event) => {
                if (!draggingRef.current) return;
                applyRailWidth(event.clientX);
              }}
              onPointerUp={(event) => {
                event.currentTarget.releasePointerCapture?.(event.pointerId);
                const moved = Math.abs(event.clientX - dragStartXRef.current);
                endRailDrag();
                if (moved > 4) {
                  lastTapRef.current = 0;
                  return;
                }
                const now = Date.now();
                if (now - lastTapRef.current < 320) {
                  setRailWidth(RAIL_DEFAULT);
                  lastTapRef.current = 0;
                } else {
                  lastTapRef.current = now;
                }
              }}
              onPointerCancel={endRailDrag}
              onDoubleClick={() => setRailWidth(RAIL_DEFAULT)}
            />
            <aside className={styles.rail} style={{ width: railWidth }}>
              <div className={styles.railSection}>
                <h2 className={styles.railTitle}>{t('wikiweb.generate')}</h2>
                <button className={styles.railBtn} onClick={() => setTab('pages')}>
                  {t('wikiweb.managePages')}
                </button>
                <button className={styles.railBtn} disabled title={t('wikiweb.rebuildUnavailable')}>
                  {t('wikiweb.rebuild')}
                </button>
                <p className={styles.railHint}>{t('wikiweb.rebuildUnavailable')}</p>
              </div>

              <div className={styles.railSection}>
                <h2 className={styles.railTitle}>{t('wikiweb.assistant')}</h2>
                <button
                  className={styles.railBtn}
                  onClick={onOpenAssistant}
                  disabled={!onOpenAssistant}
                >
                  {t('wikiweb.openAssistant')}
                </button>
                <p className={styles.railHint}>{t('wikiweb.assistantHint')}</p>
              </div>

              <div className={styles.railSection}>
                <h2 className={styles.railTitle}>{t('wikiweb.status')}</h2>
                <p className={styles.railHint}>
                  {kb ? `${kb} · ` : ''}
                  {portal.generated === null
                    ? t('wikiweb.statusUnknown')
                    : portal.generated
                      ? `${t('wikiweb.statusGenerated')} · ${portal.subjects ?? 0} ${t('wikiweb.subjects')}`
                      : t('wikiweb.statusNotGenerated')}
                </p>
              </div>
            </aside>
          </>
        )}
      </div>
    </div>
  );
}
