"use client";

import * as React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleHelp,
  CircleSlash,
  Clock,
  FileQuestion,
  Loader2,
  MinusCircle,
  Quote,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/primitives";
import type { AssessmentStatus, CandidateStatus, EvidenceItem, Verification } from "@/lib/api";
import { N_, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions }: { title: string; description?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-7">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="hud-title text-2xl font-semibold">{title}</h1>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      <div className="hud-rule mt-4" aria-hidden />
    </div>
  );
}

export function EmptyState({ icon: Icon = FileQuestion, title, children, action }: { icon?: React.ElementType; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-14 text-center">
      <div className="mb-3 rounded-full bg-muted p-3">
        <Icon className="size-5 text-muted-foreground" />
      </div>
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-muted-foreground">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      <XCircle className="mt-0.5 size-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

export function Notice({ children, tone = "info", icon: Icon }: { children: React.ReactNode; tone?: "info" | "warning"; icon?: React.ElementType }) {
  const I = Icon || (tone === "warning" ? AlertTriangle : CircleHelp);
  return (
    <div className={cn("flex items-start gap-2 rounded-md border px-3 py-2 text-sm",
      tone === "warning" ? "border-warning/30 bg-warning/5 text-foreground" : "border-info/25 bg-info/5 text-foreground")}>
      <I className={cn("mt-0.5 size-4 shrink-0", tone === "warning" ? "text-warning" : "text-info")} />
      <div>{children}</div>
    </div>
  );
}

const CANDIDATE_STATUS: Record<CandidateStatus, { label: string; variant: "default" | "info" | "success" | "danger" | "warning"; icon: React.ElementType }> = {
  imported: { label: N_("Imported"), variant: "default", icon: CircleDashed },
  pending: { label: N_("Waiting for extraction"), variant: "warning", icon: Clock },
  processing: { label: N_("Processing"), variant: "info", icon: Loader2 },
  completed: { label: N_("Completed"), variant: "success", icon: CheckCircle2 },
  failed: { label: N_("Failed"), variant: "danger", icon: XCircle },
};

export function CandidateStatusBadge({ status }: { status: CandidateStatus }) {
  const { t } = useI18n();
  const s = CANDIDATE_STATUS[status];
  const I = s.icon;
  return (
    <Badge variant={s.variant}>
      <I className={cn(status === "processing" && "animate-spin")} />
      {t(s.label)}
    </Badge>
  );
}

export const ASSESSMENT: Record<AssessmentStatus, { label: string; short: string; variant: "success" | "info" | "default" | "warning"; icon: React.ElementType; cls: string }> = {
  demonstrated: { label: N_("Clearly demonstrated"), short: N_("Demonstrated"), variant: "success", icon: CheckCircle2, cls: "text-success" },
  partial: { label: N_("Partially demonstrated"), short: N_("Partial"), variant: "info", icon: MinusCircle, cls: "text-info" },
  not_found: { label: N_("Not found in the CV"), short: N_("Not found"), variant: "default", icon: CircleSlash, cls: "text-muted-foreground" },
  undetermined: { label: N_("Cannot be determined"), short: N_("Undetermined"), variant: "warning", icon: CircleHelp, cls: "text-warning" },
};

export function AssessmentBadge({ status, short }: { status: AssessmentStatus; short?: boolean }) {
  const { t } = useI18n();
  const a = ASSESSMENT[status];
  const I = a.icon;
  return (
    <Badge variant={a.variant}>
      <I />
      {t(short ? a.short : a.label)}
    </Badge>
  );
}

/** CV section names returned by the backend. */
export const SECTIONS = [N_("header"), N_("summary"), N_("experience"), N_("education"), N_("skills"), N_("projects"),
  N_("languages"), N_("certifications"), N_("interests"), N_("extracted profile")];

export function VerificationMark({ v }: { v?: Verification }) {
  const { t } = useI18n();
  if (!v) return null;
  const map = {
    verified: { t: N_("Evidence found in the CV"), c: "text-success", I: CheckCircle2 },
    approximate: { t: N_("Evidence found (approximate match)"), c: "text-success", I: CheckCircle2 },
    term_found: { t: N_("Term found in the CV"), c: "text-success/80", I: CheckCircle2 },
    not_found: { t: N_("Unverified: not found in the CV text — check the original"), c: "text-warning", I: AlertTriangle },
    missing: { t: N_("No supporting quote"), c: "text-muted-foreground", I: CircleHelp },
  } as const;
  const m = map[v.status];
  const title = t(m.t) + (v.location ? ` (${t("section: {s}", { s: t(v.location.section) })})` : "");
  return (
    <span title={title} className={cn("inline-flex", m.c)}>
      <m.I className="size-3.5" aria-label={t(m.t)} />
    </span>
  );
}

export function EvidenceQuote({ e, onLocate }: { e: EvidenceItem; onLocate?: (loc: NonNullable<EvidenceItem["location"]>) => void }) {
  const { t } = useI18n();
  return (
    <figure className={cn("rounded-md border-l-2 bg-muted/60 px-3 py-2 text-sm", e.verified ? "border-success/60" : "border-warning/70")}>
      <blockquote className="flex gap-2">
        <Quote className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
        <span className="italic">{e.quote}</span>
      </blockquote>
      <figcaption className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {e.verified ? (
          <span className="inline-flex items-center gap-1 text-success"><CheckCircle2 className="size-3" /> {t("Found in the CV")}</span>
        ) : (
          <span className="inline-flex items-center gap-1 text-warning"><AlertTriangle className="size-3" /> {t("Not found verbatim — check the CV")}</span>
        )}
        {e.location && (
          <>
            <span>· {t("section: {s}", { s: t(e.location.section) })}</span>
            {onLocate && (
              <button type="button" className="text-primary hover:underline" onClick={() => onLocate(e.location!)}>
                {t("show in CV")}
              </button>
            )}
          </>
        )}
      </figcaption>
    </figure>
  );
}

export function Stat({ label, value, hint, icon: Icon }: { label: string; value: React.ReactNode; hint?: React.ReactNode; icon?: React.ElementType }) {
  return (
    <div className="hud-panel hud-flat rounded-lg border p-4">
      <div className="hud-label flex items-center justify-between text-muted-foreground">
        {label}
        {Icon && <Icon className="size-4 text-glow2" />}
      </div>
      <div className="hud-glow-text mt-2 font-display text-3xl font-semibold tabular text-accent-foreground">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

/** Circular HUD gauge (ring with gradient arc), e.g. RAM / VRAM usage. */
export function Gauge({ label, used, total, caption }: { label: string; used: number; total: number; caption?: string }) {
  const pct = total ? Math.min(100, Math.round((used / total) * 100)) : 0;
  const r = 42;
  const c = 2 * Math.PI * r;
  const id = React.useId().replace(/:/g, "");
  const tone = pct > 90 ? "hsl(var(--destructive))" : pct > 75 ? "hsl(var(--warning))" : "hsl(var(--glow-2))";
  return (
    <figure className="flex flex-col items-center gap-1.5" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <svg viewBox="0 0 100 100" className="size-28 -rotate-90 drop-shadow-[0_0_10px_hsl(var(--glow)/0.35)]">
        <defs>
          <linearGradient id={`g${id}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="hsl(var(--glow))" />
            <stop offset="100%" stopColor={tone} />
          </linearGradient>
        </defs>
        <circle cx="50" cy="50" r={r} fill="none" stroke="hsl(var(--border))" strokeWidth="6" />
        <circle cx="50" cy="50" r={r - 9} fill="none" stroke="hsl(var(--glow) / 0.18)" strokeWidth="1" strokeDasharray="2 3" />
        <circle cx="50" cy="50" r={r} fill="none" stroke={`url(#g${id})`} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * c} ${c}`} />
        <text x="50" y="50" transform="rotate(90 50 50)" textAnchor="middle" dominantBaseline="central"
          className="fill-foreground font-display text-[20px] font-semibold">{pct}%</text>
      </svg>
      <figcaption className="text-center">
        <div className="hud-label text-muted-foreground">{label}</div>
        {caption && <div className="text-xs text-muted-foreground tabular">{caption}</div>}
      </figcaption>
    </figure>
  );
}

export function Meter({ label, used, total }: { label: string; used: number; total: number }) {
  const { gb } = useI18n();
  const pct = total ? Math.round((used / total) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular">{gb(used)} / {gb(total)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full", pct > 90 ? "bg-destructive" : pct > 75 ? "bg-warning" : "bg-gradient-to-r from-glow to-glow2 shadow-[0_0_8px_hsl(var(--glow-2)/0.6)]")} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
