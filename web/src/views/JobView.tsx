import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Info, Plus, Save, Sparkles, Trash2, Undo2 } from "lucide-react";
import { api, type Criterion, type ModelKey } from "@/api";
import { ErrorNote, PageHeader, Spinner } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

function nextId(list: Criterion[]): string | null {
  const used = new Set(list.map((c) => c.id));
  for (let i = 1; i <= 99; i++) if (!used.has(`C${i}`)) return `C${i}`;
  return null;
}

export function JobView({ model }: { model: ModelKey }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [saved, setSaved] = useState<Criterion[]>([]);
  const [draft, setDraft] = useState<Criterion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<"suggest" | "save" | null>(null);
  const [showFiche, setShowFiche] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    api
      .getJob()
      .then((j) => {
        setTitle(j.title);
        setText(j.text);
        setSaved(j.criteria);
        setDraft(j.criteria);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const dirty = useMemo(() => JSON.stringify(saved) !== JSON.stringify(draft), [saved, draft]);
  const invalid = draft.some((c) => !c.label.trim());

  const update = (i: number, patch: Partial<Criterion>) => setDraft((d) => d.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const remove = (i: number) => setDraft((d) => d.filter((_, j) => j !== i));
  const add = () => {
    const id = nextId(draft);
    if (id) setDraft((d) => [...d, { id, label: "", description: "" }]);
  };

  const suggest = async () => {
    setBusy("suggest");
    setError(null);
    setNotice(null);
    try {
      const r = await api.suggestCriteria(model);
      setDraft(r.criteria);
      setNotice("Proposition générée à partir de la fiche — relisez, ajustez, puis cliquez sur « Enregistrer ». Rien n'est enregistré pour l'instant.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    setBusy("save");
    setError(null);
    setNotice(null);
    try {
      const cleaned = draft.map((c) => ({ ...c, label: c.label.trim(), description: c.description.trim() }));
      const r = await api.saveCriteria(cleaned);
      setSaved(r.criteria);
      setDraft(r.criteria);
      setNotice("Critères enregistrés. Les candidats déjà analysés peuvent être ré-analysés depuis leur fiche pour en tenir compte.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <Spinner />;

  return (
    <div className="space-y-6">
      <PageHeader title={title || "Poste"} description="Fiche de poste et critères de lecture des candidatures." />

      <Card className="gap-0 py-0">
        <button
          onClick={() => setShowFiche((s) => !s)}
          className="hover:bg-accent/50 flex w-full cursor-pointer items-center justify-between rounded-xl px-5 py-4 text-left"
          aria-expanded={showFiche}
        >
          <span className="font-medium">Fiche de poste</span>
          <ChevronDown className={cn("text-muted-foreground size-4 transition-transform", showFiche && "rotate-180")} />
        </button>
        {showFiche && (
          <div className="border-t px-5 py-4">
            <div className="text-sm leading-relaxed whitespace-pre-wrap">{text || "Aucune fiche de poste chargée."}</div>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>Critères</CardTitle>
              <CardDescription className="mt-1.5">Chaque CV est lu au regard de ces critères, un par un.</CardDescription>
            </div>
            <Button variant="outline" onClick={suggest} disabled={busy !== null}>
              <Sparkles className={cn(busy === "suggest" && "animate-pulse")} />
              {busy === "suggest" ? "Proposition en cours…" : "Proposer des critères depuis la fiche"}
            </Button>
          </div>
          <div className="border-primary/30 bg-primary/5 mt-3 flex items-start gap-2 rounded-md border px-3 py-2 text-sm">
            <Info className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
            <span>
              <strong className="font-semibold">Ces critères sont la seule base de comparaison.</strong> Formulez-les à partir des exigences du poste,
              jamais à partir de caractéristiques personnelles.
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {draft.length === 0 && <p className="text-muted-foreground text-sm">Aucun critère. Ajoutez-en ou demandez une proposition.</p>}
          <ul className="space-y-2">
            {draft.map((c, i) => (
              <li key={c.id} className="bg-background/50 flex items-start gap-3 rounded-lg border p-3">
                <span className="bg-secondary text-secondary-foreground mt-1.5 inline-flex h-6 min-w-9 items-center justify-center rounded font-mono text-xs font-semibold">
                  {c.id}
                </span>
                <div className="grid flex-1 gap-2">
                  <Input
                    value={c.label}
                    maxLength={80}
                    placeholder="Libellé (ex. : Expérience Python ≥ 4 ans)"
                    aria-label={`Libellé du critère ${c.id}`}
                    onChange={(e) => update(i, { label: e.target.value })}
                    className={cn("font-medium", !c.label.trim() && "border-destructive/50")}
                  />
                  <Textarea
                    value={c.description}
                    maxLength={300}
                    rows={1}
                    placeholder="Précision facultative"
                    aria-label={`Description du critère ${c.id}`}
                    onChange={(e) => update(i, { description: e.target.value })}
                    className="text-muted-foreground min-h-9"
                  />
                </div>
                <Button variant="ghost" size="icon" onClick={() => remove(i)} aria-label={`Supprimer le critère ${c.id}`} title="Supprimer">
                  <Trash2 className="text-muted-foreground" />
                </Button>
              </li>
            ))}
          </ul>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <Button variant="outline" onClick={add} disabled={!nextId(draft)}>
              <Plus /> Ajouter un critère
            </Button>
            <div className="flex items-center gap-2">
              {dirty && <span className="text-muted-foreground text-xs">Modifications non enregistrées</span>}
              <Button variant="ghost" onClick={() => setDraft(saved)} disabled={!dirty || busy !== null}>
                <Undo2 /> Annuler
              </Button>
              <Button onClick={save} disabled={!dirty || invalid || busy !== null}>
                <Save /> {busy === "save" ? "Enregistrement…" : "Enregistrer"}
              </Button>
            </div>
          </div>
          {notice && <p className="text-muted-foreground border-l-primary border-l-2 pl-3 text-sm">{notice}</p>}
          <ErrorNote error={error} />
        </CardContent>
      </Card>
    </div>
  );
}
