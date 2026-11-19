'use client';

import { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';
import { en } from './locales/en';
import { zh } from './locales/zh';
import { ja } from './locales/ja';
import { DEFAULT_LOCALE, LOCALE_COOKIE, htmlLang, type Locale } from './locale';

// Re-export the shared primitives so consumers can import everything from
// '@/lib/i18n'. The definitions stay in ./locale so server code can use them.
export {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  LOCALE_LABELS,
  LOCALES,
  htmlLang,
  isLocale,
  negotiateLocale,
  type Locale,
} from './locale';

/** The English dictionary defines the canonical key shape. */
export type Dict = typeof en;

const DICTS: Record<Locale, Dict> = { zh, en, ja };

/** Walk a dot-separated path into a nested dictionary object. */
function lookup(dict: unknown, path: string): string | undefined {
  let node: unknown = dict;
  for (const part of path.split('.')) {
    if (node && typeof node === 'object' && part in (node as Record<string, unknown>)) {
      node = (node as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return typeof node === 'string' ? node : undefined;
}

/**
 * All leaf key paths of the English dictionary, e.g. 'sidebar.home'.
 * Gives `t()` autocompletion and a compile-time error for typos.
 */
type Leaves<T> = {
  [K in keyof T & string]: T[K] extends string
    ? K
    : T[K] extends object
      ? `${K}.${Leaves<T[K]>}`
      : never;
}[keyof T & string];

export type MessageKey = Leaves<Dict>;

export interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  /**
   * Translate a dot-separated key, e.g. t('sidebar.home').
   * Supports {name} interpolation. Unknown keys fall back to English, then to
   * the key itself.
   */
  t: (key: MessageKey | (string & {}), params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function translate(
  locale: Locale,
  key: string,
  params?: Record<string, string | number>,
): string {
  let text = lookup(DICTS[locale], key) ?? lookup(DICTS.en, key) ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replaceAll(`{${k}}`, String(v));
    }
  }
  return text;
}

/**
 * `initialLocale` comes from the server (cookie, then Accept-Language), so the
 * first paint already matches the visitor instead of flashing a default.
 */
export function I18nProvider({
  children,
  initialLocale = DEFAULT_LOCALE,
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    // Persist so the server keeps rendering this language on the next visit.
    try {
      document.cookie = `${LOCALE_COOKIE}=${l}; path=/; max-age=31536000; samesite=lax`;
    } catch {
      // Cookies unavailable (private mode): the in-memory choice still applies.
    }
    document.documentElement.lang = htmlLang(l);
  }, []);

  const t = useCallback(
    (key: string, params?: Record<string, string | number>) => translate(locale, key, params),
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    // Safe fallback for usage outside the provider (should not happen).
    return {
      locale: DEFAULT_LOCALE,
      setLocale: () => {},
      t: (key, params) => translate(DEFAULT_LOCALE, key, params),
    };
  }
  return ctx;
}

/** Convenience hook returning only the translate function. */
export function useT() {
  return useI18n().t;
}
