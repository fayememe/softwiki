'use client';

import { useEffect, useRef, useState } from 'react';
import { useI18n, LOCALES, LOCALE_LABELS, Locale } from '@/lib/i18n';
import styles from './LanguageSwitcher.module.css';

/** Compact label in the top-right cluster: 中 / EN / 日. */
const SHORT_LABEL: Record<Locale, string> = { zh: '中', en: 'EN', ja: '日' };

export default function LanguageSwitcher() {
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
    <div className={styles.wrap} ref={rootRef}>
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
            Math.max(8, rect.left),
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
        <span className={styles.langLabel}>{SHORT_LABEL[locale]}</span>
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
