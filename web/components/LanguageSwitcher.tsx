'use client';

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

const SHORT_LABEL: Record<Locale, string> = { zh: '中', en: 'EN', ja: '日' };

export default function LanguageSwitcher({ collapsed = false }: { collapsed?: boolean }) {
  const { locale, setLocale, t } = useI18n();

  const next = () => {
    const idx = LOCALES.indexOf(locale);
    setLocale(LOCALES[(idx + 1) % LOCALES.length]);
  };

  return (
    <button
      className={styles.langBtn}
      onClick={next}
      title={`${t('common.language')}: ${LOCALE_LABELS[locale]}`}
      aria-label={`${t('common.language')}: ${LOCALE_LABELS[locale]}`}
    >
      <GlobeIcon />
      <span className={styles.langLabel}>{collapsed ? SHORT_LABEL[locale] : LOCALE_LABELS[locale]}</span>
    </button>
  );
}
