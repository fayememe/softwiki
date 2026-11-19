import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import "./globals.css";
import { I18nProvider } from "@/lib/i18n";
import { LOCALE_COOKIE, htmlLang, isLocale, negotiateLocale, type Locale } from "@/lib/i18n/locale";
import { en } from "@/lib/i18n/locales/en";
import { zh } from "@/lib/i18n/locales/zh";
import { ja } from "@/lib/i18n/locales/ja";

const DICTS = { en, zh, ja };

/**
 * Resolve the UI language on the server so the first paint already matches the
 * visitor: an explicit choice (cookie) wins over negotiation (Accept-Language).
 */
async function resolveLocale(): Promise<Locale> {
  const cookieStore = await cookies();
  const saved = cookieStore.get(LOCALE_COOKIE)?.value;
  if (isLocale(saved)) return saved;

  const headerStore = await headers();
  return negotiateLocale(headerStore.get("accept-language"));
}

export async function generateMetadata(): Promise<Metadata> {
  const locale = await resolveLocale();
  const meta = DICTS[locale].meta;
  return {
    title: meta.title,
    description: meta.description,
    keywords: meta.keywords.split(","),
    openGraph: {
      title: meta.title,
      description: meta.description,
      type: "website",
    },
  };
}

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const locale = await resolveLocale();
  return (
    <html lang={htmlLang(locale)} suppressHydrationWarning>
      <body>
        <I18nProvider initialLocale={locale}>{children}</I18nProvider>
      </body>
    </html>
  );
}
