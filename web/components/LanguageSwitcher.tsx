'use client';

import { useEffect, useRef, useState } from 'react';
import { useI18n, LOCALES, LOCALE_LABELS, Locale } from '@/lib/i18n';
import styles from './LanguageSwitcher.module.css';

function GlobeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z" />
    </svg>
  );
}

/**
 * ISO codes for the collapsed pill. The native names (中文 / English / 日本語)
 * are shown in the menu; mixing one Latin abbreviation with two CJK characters
 * ("EN / 日 / 中") read like a typo.
 */
const SHORT_LABEL: Record<Locale, string> = { zh: 'ZH', en: 'EN', ja: 'JA' };

export default function LanguageSwitcher({ collapsed = false }: { collapsed?: boolean }) {
  const { locale, setLocale, t } = useI18n();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const btnRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className={styles.wrap} data-collapsed={collapsed ? 'true' : undefined} ref={rootRef}>
      <button
        ref={btnRef}
        className={styles.langBtn}
        onClick={() => {
          if (open) { setOpen(false); return; }
          const rect = btnRef.current?.getBoundingClientRect();
          if (!rect) return;
          // Fixed positioning: the menu must escape the sidebar's overflow and
          // the collapsed rail, which are both too narrow for a dropdown.
          const menuWidth = 150;
          const left = Math.min(
            Math.max(8, collapsed ? rect.right + 6 : rect.left),
            window.innerWidth - menuWidth - 8,
          );
          const estimatedHeight = 132;
          const top = rect.bottom + 6 + estimatedHeight > window.innerHeight
            ? Math.max(8, rect.top - estimatedHeight - 6)
            : rect.bottom + 6;
          setPos({ left, top });
          setOpen(true);
        }}
        title={`${t('common.language')}: ${LOCALE_LABELS[locale]}`}
        aria-label={`${t('common.language')}: ${LOCALE_LABELS[locale]}`}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <GlobeIcon />
        <span className={styles.langLabel}>
          {collapsed ? SHORT_LABEL[locale] : LOCALE_LABELS[locale]}
        </span>
      </button>

      {open && (
        <div
          className={styles.menu}
          role="menu"
          style={pos ? { left: pos.left, top: pos.top } : undefined}
        >
          {LOCALES.map(item => (
            <button
              key={item}
              role="menuitemradio"
              aria-checked={item === locale}
              className={`${styles.menuItem} ${item === locale ? styles.menuItemActive : ''}`}
              onClick={() => { setLocale(item); setOpen(false); }}
            >
              <span>{LOCALE_LABELS[item]}</span>
              {item === locale && <span className={styles.menuCheck}>✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
