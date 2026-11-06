"use client";

// Minimal i18n (EN source strings → FR dictionary, gettext style).
// - `t('English text {var}', { var })` returns the French text when lang = fr.
// - Strings in constant tables are wrapped in N_('…') so the checker finds them.
// - The language is stored in a `lang` cookie, read by the root layout on the
//   server, so the first render is already in the right language (no flash).
// - Backend messages are translated by the backend (X-Lang header, see lib/api.ts).
// - `npm run check:i18n` lists strings used with t() that have no French entry.

import { createContext, useContext, useMemo, useState } from "react";
import { FR } from "./i18n-fr";

export type Lang = "en" | "fr";
export type Vars = Record<string, string | number>;

let currentLang: Lang = "en";
/** Current UI language, for non-React code (API client). */
export function getLang(): Lang {
  return currentLang;
}

function interpolate(s: string, vars?: Vars) {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

export function translate(lang: Lang, key: string, vars?: Vars) {
  return interpolate(lang === "fr" ? FR[key] ?? key : key, vars);
}

const LOCALES: Record<Lang, string> = { en: "en-GB", fr: "fr-FR" };

function makeHelpers(lang: Lang) {
  const t = (key: string, vars?: Vars) => translate(lang, key, vars);
  const locale = LOCALES[lang];
  return {
    lang,
    t,
    formatDate(iso: string | null | undefined, withTime = true) {
      if (!iso) return "—";
      return new Date(iso).toLocaleString(locale, withTime
        ? { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
        : { day: "2-digit", month: "short", year: "numeric" });
    },
    timeAgo(iso: string) {
      const s = (new Date(iso).getTime() - Date.now()) / 1000;
      const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
      if (Math.abs(s) < 60) return rtf.format(0, "second");
      if (Math.abs(s) < 3600) return rtf.format(Math.round(s / 60), "minute");
      if (Math.abs(s) < 86400) return rtf.format(Math.round(s / 3600), "hour");
      return rtf.format(Math.round(s / 86400), "day");
    },
    formatBytes(n: number) {
      const u = lang === "fr" ? ["o", "Ko", "Mo"] : ["B", "KB", "MB"];
      if (n < 1024) return `${n} ${u[0]}`;
      if (n < 1048576) return `${(n / 1024).toFixed(0)} ${u[1]}`;
      return `${(n / 1048576).toLocaleString(locale, { maximumFractionDigits: 1 })} ${u[2]}`;
    },
    /** GB with one decimal, e.g. "5,8 Go" / "5.8 GB" (input in MB). */
    gb(mb: number) {
      return `${(mb / 1024).toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ${lang === "fr" ? "Go" : "GB"}`;
    },
    num(n: number, digits = 0) {
      return n.toLocaleString(locale, { maximumFractionDigits: digits, minimumFractionDigits: digits });
    },
  };
}

type I18n = ReturnType<typeof makeHelpers> & { setLang: (l: Lang) => void };

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ initialLang, children }: { initialLang: Lang; children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  currentLang = lang;
  const value = useMemo<I18n>(() => ({
    ...makeHelpers(lang),
    setLang(l: Lang) {
      document.cookie = `lang=${l}; path=/; max-age=31536000; samesite=lax`;
      document.documentElement.lang = l;
      currentLang = l;
      setLangState(l);
    },
  }), [lang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const v = useContext(Ctx);
  if (!v) throw new Error("useI18n outside I18nProvider");
  return v;
}

/** Marks a static string for translation (translated later with t()). */
export const N_ = (s: string) => s;
