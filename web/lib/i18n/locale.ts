/**
 * Locale primitives shared by both the server (layout / metadata) and the
 * client (provider / switcher).
 *
 * This module must stay free of React and of the 'use client' directive:
 * Server Components cannot call functions exported from a 'use client' module,
 * so `isLocale` / `negotiateLocale` have to live here to be usable in layout.tsx.
 */

export type Locale = 'zh' | 'en' | 'ja';

export const LOCALES: Locale[] = ['zh', 'en', 'ja'];

export const LOCALE_LABELS: Record<Locale, string> = {
  zh: '中文',
  en: 'English',
  ja: '日本語',
};

/** Cookie written by the client so the server can render the right locale. */
export const LOCALE_COOKIE = 'softwiki_locale';

/** Used when neither a cookie nor a usable Accept-Language header exists. */
export const DEFAULT_LOCALE: Locale = 'zh';

export function isLocale(v: string | null | undefined): v is Locale {
  return v === 'zh' || v === 'en' || v === 'ja';
}

/** BCP-47 tag for the <html lang> attribute. */
export function htmlLang(locale: Locale): string {
  return locale === 'zh' ? 'zh-CN' : locale;
}

/** Pick a supported locale from an Accept-Language header value. */
export function negotiateLocale(acceptLanguage: string | null | undefined): Locale {
  if (!acceptLanguage) return DEFAULT_LOCALE;

  const ranked = acceptLanguage
    .split(',')
    .map((part) => {
      const [tag, ...params] = part.trim().split(';');
      const q = params.find((p) => p.trim().startsWith('q='));
      const quality = q ? parseFloat(q.split('=')[1]) : 1;
      return {
        tag: tag.trim().toLowerCase(),
        quality: Number.isNaN(quality) ? 0 : quality,
      };
    })
    .filter((entry) => entry.tag && entry.quality > 0)
    .sort((a, b) => b.quality - a.quality);

  for (const { tag } of ranked) {
    if (tag === 'zh' || tag.startsWith('zh-')) return 'zh';
    if (tag === 'en' || tag.startsWith('en-')) return 'en';
    if (tag === 'ja' || tag.startsWith('ja-')) return 'ja';
  }
  return DEFAULT_LOCALE;
}
