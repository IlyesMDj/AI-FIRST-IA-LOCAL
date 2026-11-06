"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  Briefcase,
  Columns3,
  LayoutDashboard,
  Menu,
  MessagesSquare,
  Moon,
  Settings,
  ShieldCheck,
  Sun,
  Users,
  X,
} from "lucide-react";
import { useResource } from "@/lib/hooks";
import type { SystemStatus } from "@/lib/api";
import { N_, useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: N_("Dashboard"), icon: LayoutDashboard },
  { href: "/candidates", label: N_("Candidates"), icon: Users },
  { href: "/jobs", label: N_("Job descriptions"), icon: Briefcase },
  { href: "/assistant", label: N_("Assistant"), icon: MessagesSquare },
  { href: "/compare", label: N_("Compare"), icon: Columns3 },
];
const NAV_ADMIN = [
  { href: "/privacy", label: N_("Privacy & data"), icon: ShieldCheck },
  { href: "/settings", label: N_("AI settings"), icon: Settings },
  { href: "/settings/benchmark", label: N_("Model benchmark"), icon: BarChart3 },
];

function ThemeToggle() {
  const { t } = useI18n();
  const [dark, setDark] = useState(false);
  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);
  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("rcl-theme", next ? "dark" : "light");
    } catch {
      /* ignore */
    }
  };
  return (
    <button onClick={toggle} className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground" aria-label={t("Toggle dark mode")}>
      {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}

function LanguageSwitch() {
  const { lang, setLang, t } = useI18n();
  const opts: { v: Lang; label: string; title: string }[] = [
    { v: "fr", label: "FR", title: "Français" },
    { v: "en", label: "EN", title: "English" },
  ];
  return (
    <div role="group" aria-label={t("Language")} className="flex rounded-md border bg-card p-0.5 text-xs font-medium">
      {opts.map((o) => (
        <button
          key={o.v}
          type="button"
          lang={o.v}
          title={o.title}
          aria-pressed={lang === o.v}
          onClick={() => setLang(o.v)}
          className={cn("rounded px-2 py-1", lang === o.v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function AIStatus() {
  const { t } = useI18n();
  const { data } = useResource<SystemStatus>("/api/system/status", { pollMs: 15000 });
  let tone = "bg-muted-foreground";
  let text = t("Checking local AI…");
  if (data) {
    if (!data.ollama.reachable) {
      tone = "bg-destructive";
      text = t("Local AI offline");
    } else if (!data.active_model_available) {
      tone = "bg-warning";
      text = t("Model unavailable");
    } else if (data.queue.pending > 0) {
      tone = "bg-info animate-pulse";
      text = t("Working · {n} task(s)", { n: data.queue.pending });
    } else {
      tone = "bg-success";
      text = t("Local AI ready");
    }
  }
  return (
    <Link href="/settings" className="hidden items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground hover:text-foreground sm:flex" title={data?.active_model}>
      <span className={cn("size-2 rounded-full", tone)} />
      {text}
    </Link>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useI18n();
  const path = usePathname();
  const isActive = (href: string) => (href === "/" ? path === "/" : href === "/settings" ? path === "/settings" : path.startsWith(href));
  const item = (n: (typeof NAV)[number]) => (
    <Link
      key={n.href}
      href={n.href}
      onClick={onNavigate}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm",
        isActive(n.href) ? "nav-active bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
      )}
    >
      <n.icon className="size-4" />
      {t(n.label)}
    </Link>
  );
  return (
    <nav className="flex flex-1 flex-col gap-0.5 px-3">
      {NAV.map(item)}
      <div className="hud-label mb-1 mt-6 px-2.5 text-muted-foreground/70">{t("Administration")}</div>
      {NAV_ADMIN.map(item)}
    </nav>
  );
}

function Brand() {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2 px-5 py-5">
      <div className="btn-glow flex size-9 items-center justify-center rounded-lg text-primary-foreground">
        <ShieldCheck className="size-4" />
      </div>
      <div className="leading-tight">
        <div className="hud-title text-sm font-semibold">Recruiter Copilot</div>
        <div className="text-[11px] text-muted-foreground">{t("Local · private by design")}</div>
      </div>
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-sidebar/80 backdrop-blur lg:flex dark:shadow-[inset_-1px_0_0_hsl(var(--glow)/0.25),8px_0_30px_hsl(var(--glow)/0.06)]">
        <Brand />
        <NavLinks />
        <div className="border-t px-5 py-3 text-[11px] leading-relaxed text-muted-foreground">
          {t("All processing happens on this computer. The AI assists; decisions stay with you.")}
        </div>
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col bg-sidebar shadow-xl">
            <div className="flex items-center justify-between pr-3">
              <Brand />
              <button onClick={() => setOpen(false)} aria-label={t("Close menu")} className="p-2"><X className="size-4" /></button>
            </div>
            <NavLinks onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b bg-background/70 px-4 backdrop-blur sm:px-6 dark:shadow-[0_1px_0_hsl(var(--glow)/0.25)]">
          <button className="rounded-md p-2 hover:bg-secondary lg:hidden" onClick={() => setOpen(true)} aria-label={t("Open menu")}>
            <Menu className="size-4" />
          </button>
          <div className="flex-1" />
          <AIStatus />
          <LanguageSwitch />
          <ThemeToggle />
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
