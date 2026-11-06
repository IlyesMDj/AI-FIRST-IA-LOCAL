import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleDashed, CircleHelp, Clock, FileWarning, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Assessment, Status } from "@/api";
import { cn } from "@/lib/utils";

// --- Routage minimal par hash (aucun état stocké) --------------------------

export function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash.replace(/^#/, "") || "/candidats";
}

export function navigate(path: string) {
  window.location.hash = path;
}

// --- Évaluations ------------------------------------------------------------

export const ASSESSMENT_STYLE: Record<Assessment, { variant: "ok" | "partial" | "none"; cell: string; icon: typeof CheckCircle2 }> = {
  présent: { variant: "ok", cell: "bg-ok-bg text-ok-fg", icon: CheckCircle2 },
  partiel: { variant: "partial", cell: "bg-partial-bg text-partial-fg", icon: CircleDashed },
  "non trouvé": { variant: "none", cell: "bg-none-bg text-none-fg", icon: CircleHelp },
};

export function AssessmentBadge({ value, className }: { value: Assessment; className?: string }) {
  const s = ASSESSMENT_STYLE[value] ?? ASSESSMENT_STYLE["non trouvé"];
  const Icon = s.icon;
  return (
    <Badge variant={s.variant} className={className}>
      <Icon aria-hidden />
      {value}
    </Badge>
  );
}

/** Une évaluation « présent » / « partiel » sans citation retrouvée dans le CV n'est pas étayée. */
export function isUnsupportedClaim(assessment: Assessment, quote: string | null | undefined): boolean {
  return (assessment === "présent" || assessment === "partiel") && !quote;
}

export const UNSUPPORTED_LABEL = "citation introuvable — non étayé";

export function EvidenceBadge({ assessment, quote, className }: { assessment: Assessment; quote: string | null; className?: string }) {
  if (!isUnsupportedClaim(assessment, quote)) return <AssessmentBadge value={assessment} className={className} />;
  return (
    <Badge variant="none" className={cn("border-dashed", className)} title={`Le modèle a répondu « ${assessment} » mais sa citation est introuvable dans le CV.`}>
      <AlertTriangle aria-hidden />
      {assessment} ? · {UNSUPPORTED_LABEL}
    </Badge>
  );
}

export function AssessmentLegend() {
  return (
    <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
      <span>Légende :</span>
      <AssessmentBadge value="présent" />
      <AssessmentBadge value="partiel" />
      <AssessmentBadge value="non trouvé" />
      <span className="ml-1">« non trouvé » = absent du CV, pas forcément absent chez la personne.</span>
    </div>
  );
}

// --- Statuts ----------------------------------------------------------------

const STATUS: Record<Status, { label: string; icon: typeof Clock; cls: string; spin?: boolean }> = {
  pending: { label: "En attente", icon: Clock, cls: "text-muted-foreground bg-muted border-border" },
  analyzing: { label: "Analyse…", icon: Loader2, cls: "text-primary bg-accent border-border", spin: true },
  ready: { label: "Prêt", icon: CheckCircle2, cls: "bg-ok-bg text-ok-fg border-ok-border" },
  unsupported: { label: "Illisible", icon: FileWarning, cls: "bg-partial-bg text-partial-fg border-partial-border" },
  error: { label: "Erreur", icon: AlertTriangle, cls: "text-destructive bg-destructive/10 border-destructive/30" },
};

export function StatusBadge({ status }: { status: Status }) {
  const s = STATUS[status] ?? STATUS.error;
  const Icon = s.icon;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap", s.cls)}>
      <Icon className={cn("size-3", s.spin && "animate-spin")} aria-hidden />
      {s.label}
    </span>
  );
}

export const isBusy = (s: Status) => s === "pending" || s === "analyzing";

// --- Messages ---------------------------------------------------------------

export function ErrorNote({ error, className }: { error: unknown; className?: string }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className={cn("border-destructive/30 bg-destructive/10 text-destructive flex items-start gap-2 rounded-md border px-3 py-2 text-sm", className)}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{msg}</span>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="text-muted-foreground flex items-center gap-2 text-sm">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label ?? "Chargement…"}
    </div>
  );
}

export function PageHeader({ title, description, children }: { title: string; description?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export const REMOVED_LABELS: Record<string, string> = {
  email: "Adresse e-mail",
  telephone: "Téléphone",
  adresse: "Adresse postale",
  date_naissance: "Date de naissance",
  age: "Âge",
  nationalite: "Nationalité",
  situation_familiale: "Situation familiale",
  lien_perso: "Lien vers un profil personnel",
  numero_secu: "Numéro de sécurité sociale",
  photo: "Photo (mention)",
};
