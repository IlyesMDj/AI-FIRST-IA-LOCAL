import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronRight, FileUp, ListOrdered, Upload } from "lucide-react";
import { api, type CandidateSummary, type ModelKey } from "@/api";
import { ErrorNote, isBusy, navigate, PageHeader, Spinner, StatusBadge } from "@/components/common";
import { Card } from "@/components/ui/card";
import { cn, formatDate } from "@/lib/utils";

const ACCEPT = ".pdf,.txt,.md,.png,.jpg,.jpeg";

export function useCandidates() {
  const [list, setList] = useState<CandidateSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const refresh = useCallback(async () => {
    try {
      setList(await api.listCandidates());
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);
  // Interrogation toutes les 2 s tant qu'un statut est en attente / en analyse.
  const busy = list?.some((c) => isBusy(c.status)) ?? false;
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [busy, refresh]);
  return { list, error, refresh };
}

function DropZone({ model, onUploaded }: { model: ModelKey; onUploaded: () => void }) {
  const [over, setOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const input = useRef<HTMLInputElement>(null);

  const send = async (files: File[]) => {
    if (!files.length) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadCandidates(files, model);
      onUploaded();
    } catch (e) {
      setError(e);
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <div className="space-y-2">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          send(Array.from(e.dataTransfer.files));
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
          over ? "border-primary bg-primary/5" : "hover:border-primary/50 hover:bg-accent/40 bg-card",
          uploading && "pointer-events-none opacity-60",
        )}
      >
        <span className="bg-primary/10 text-primary grid size-11 place-items-center rounded-full">
          {uploading ? <Upload className="size-5 animate-bounce" /> : <FileUp className="size-5" />}
        </span>
        <span className="font-medium">{uploading ? "Envoi en cours…" : "Déposez les CV ici ou cliquez pour choisir"}</span>
        <span className="text-muted-foreground text-xs">
          PDF, TXT, MD, PNG, JPG · plusieurs fichiers possibles · les données personnelles non utiles au poste sont masquées dès l'import
        </span>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          onChange={(e) => send(Array.from(e.target.files ?? []))}
        />
      </label>
      <ErrorNote error={error} />
    </div>
  );
}

export function CandidatesView({ model }: { model: ModelKey }) {
  const { list, error, refresh } = useCandidates();
  const counts = list?.reduce<Record<string, number>>((acc, c) => ((acc[c.status] = (acc[c.status] ?? 0) + 1), acc), {}) ?? {};

  return (
    <div className="space-y-6">
      <PageHeader
        title="Candidats"
        description={
          <span className="inline-flex items-center gap-1.5">
            <ListOrdered className="size-4" aria-hidden /> Affichés dans l'ordre d'import. Aucun classement, aucun score.
          </span>
        }
      />
      <DropZone model={model} onUploaded={refresh} />
      <ErrorNote error={error} />

      {list === null ? (
        <Spinner />
      ) : list.length === 0 ? (
        <p className="text-muted-foreground text-sm">Aucun candidat pour l'instant.</p>
      ) : (
        <Card className="gap-0 overflow-hidden py-0">
          <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 border-b px-5 py-2.5 text-xs">
            <span>{list.length} fichier(s)</span>
            {counts.ready ? <span>{counts.ready} prêt(s)</span> : null}
            {(counts.pending ?? 0) + (counts.analyzing ?? 0) > 0 && <span>{(counts.pending ?? 0) + (counts.analyzing ?? 0)} en cours — actualisation automatique</span>}
            {(counts.unsupported ?? 0) + (counts.error ?? 0) > 0 && <span>{(counts.unsupported ?? 0) + (counts.error ?? 0)} à vérifier</span>}
          </div>
          <ul className="divide-y">
            {list.map((c, i) => (
              <li key={c.id}>
                <button
                  onClick={() => navigate(`/candidats/${encodeURIComponent(c.id)}`)}
                  className="hover:bg-accent/50 group flex w-full cursor-pointer items-center gap-4 px-5 py-3 text-left"
                >
                  <span className="text-muted-foreground w-6 shrink-0 text-right font-mono text-xs" title="Ordre d'import">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{c.display_name}</div>
                    {c.reason && c.status !== "pending" && c.status !== "analyzing" ? (
                      <div className="text-muted-foreground truncate text-xs">{c.reason}</div>
                    ) : (
                      <div className="text-muted-foreground text-xs">Importé le {formatDate(c.created_at)}</div>
                    )}
                  </div>
                  <StatusBadge status={c.status} />
                  <ChevronRight className="text-muted-foreground size-4 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
