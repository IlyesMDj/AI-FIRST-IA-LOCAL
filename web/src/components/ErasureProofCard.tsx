import { AlertTriangle, CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import type { ErasureProof } from "@/api";
import { cn, formatDate } from "@/lib/utils";

const TABLE_LABELS: Record<string, string> = {
  candidates: "Candidat",
  documents: "Texte du CV (masqué)",
  analyses: "Analyse",
  evidence: "Citations",
  questions: "Questions d'entretien",
};

export function ErasureProofCard({ proof, compact = false }: { proof: ErasureProof; compact?: boolean }) {
  const ok = proof.verified;
  // Anciennes preuves (avant ajout des champs) : valeurs absentes → traitées comme inconnues.
  const checked = proof.extracts_checked ?? 0;
  const vacuumOk = proof.vacuum_ok ?? true;
  const hitsOk = proof.raw_file_hits === 0 && checked > 0;
  return (
    <div
      className={cn(
        "rounded-xl border-2 p-5",
        ok ? "border-ok-border bg-ok-bg/40" : "border-destructive/40 bg-destructive/5",
        compact && "p-4",
      )}
    >
      <div className="flex flex-wrap items-center gap-3">
        {ok ? <ShieldCheck className="text-ok-fg size-7" aria-hidden /> : <XCircle className="text-destructive size-7" aria-hidden />}
        <div className="min-w-0 flex-1">
          <div className={cn("text-lg font-semibold", ok ? "text-ok-fg" : "text-destructive")}>
            {ok ? "Effacement vérifié ✓" : "Effacement NON vérifié"}
          </div>
          <div className="text-muted-foreground text-sm">{formatDate(proof.erased_at)}</div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <div className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">Lignes restantes en base</div>
          <ul className="space-y-1 text-sm">
            {Object.entries(proof.tables).map(([table, n]) => (
              <li key={table} className="flex items-center justify-between gap-3">
                <span>
                  {TABLE_LABELS[table] ?? table} <code className="text-muted-foreground text-xs">{table}</code>
                </span>
                <span className={cn("inline-flex items-center gap-1 font-mono font-semibold", n === 0 ? "text-ok-fg" : "text-destructive")}>
                  {n}
                  {n === 0 ? <CheckCircle2 className="size-3.5" aria-label="ok" /> : <XCircle className="size-3.5" aria-label="non nul" />}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="space-y-3">
          <div>
            <div className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">Octets du fichier de base</div>
            <div className="flex items-center justify-between gap-3 text-sm">
              <span>
                {checked} extrait{checked > 1 ? "s" : ""} du CV recherché{checked > 1 ? "s" : ""} dans le fichier de base :
              </span>
              <span className={cn("inline-flex shrink-0 items-center gap-1 font-mono font-semibold", hitsOk ? "text-ok-fg" : "text-destructive")}>
                {proof.raw_file_hits} trouvé{proof.raw_file_hits > 1 ? "s" : ""}
                {hitsOk ? <CheckCircle2 className="size-3.5" aria-hidden /> : <XCircle className="size-3.5" aria-hidden />}
              </span>
            </div>
            <div className="mt-1 flex items-center justify-between gap-3 text-sm">
              <span>Compactage de la base (VACUUM)</span>
              <span className={cn("inline-flex items-center gap-1 font-semibold", vacuumOk ? "text-ok-fg" : "text-destructive")}>
                {vacuumOk ? "effectué" : "échoué"}
                {vacuumOk ? <CheckCircle2 className="size-3.5" aria-hidden /> : <XCircle className="size-3.5" aria-hidden />}
              </span>
            </div>
            {checked === 0 && (
              <p className="text-partial-fg mt-2 flex items-start gap-1.5 text-xs">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                Aucun extrait recherché : la vérification dans les octets du fichier n'a pas pu être faite (ou le candidat n'avait pas de texte enregistré).
              </p>
            )}
            {!vacuumOk && (
              <p className="text-destructive mt-2 flex items-start gap-1.5 text-xs">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                Le compactage a échoué : des pages libérées peuvent subsister dans le fichier. Relancez un effacement ou redémarrez l'application.
              </p>
            )}
          </div>
          <div>
            <div className="text-muted-foreground mb-1 text-xs font-medium tracking-wide uppercase">Empreinte de l'identifiant (SHA-256)</div>
            <code className="bg-muted block rounded px-2 py-1 font-mono text-xs break-all">{proof.candidate_id_hash}</code>
            <p className="text-muted-foreground mt-1 text-xs">Le journal ne conserve ni nom ni texte : seulement cette empreinte.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
