import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import {
  ArrowLeft,
  EyeOff,
  FileText,
  Lightbulb,
  ListChecks,
  MessageCircleQuestion,
  MessagesSquare,
  Quote,
  RefreshCw,
  ScanLine,
  Send,
  Square,
  Trash2,
} from "lucide-react";
import { api, type CandidateDetail, type Criterion, type ErasureProof, type Evidence, type ModelKey } from "@/api";
import { AssessmentLegend, EvidenceBadge, ErrorNote, isBusy, navigate, REMOVED_LABELS, Spinner, StatusBadge } from "@/components/common";
import { ErasureProofCard } from "@/components/ErasureProofCard";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type Range = { start: number; end: number; key: number };

// --- Texte masqué du CV, avec surlignage -----------------------------------

// Marqueurs posés par le masquage côté serveur : « [email retiré] », « [date_naissance retirée] »…
const REDACTION_RE = /\[[^\]\n]{1,48}retir[ée]+(?:\(e\))?\]/g;
const BULLET_RE = /^(\s*)([-•*–▪◦·]|\d{1,2}[.)])\s+/;
const PERIOD_RE = /^(\s*)((?:(?:janv|févr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc)[a-zéû.]*\s+)?(?:19|20)\d{2}\s*(?:[-–—à/]|au|to)\s*(?:(?:janv|févr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc)[a-zéû.]*\s+)?(?:(?:19|20)\d{2}|aujourd'hui|présent|actuel|now|today))/i;

/** « [situation_familiale retirée] » → « Situation familiale masquée ». */
function redactionLabel(piece: string): string {
  const key = piece.replace(/^\[|\]$/g, "").replace(/\s*retir[ée]+(?:\(e\))?$/, "").trim();
  const label = REMOVED_LABELS[key] ?? key.replace(/_/g, " ");
  return `${label.charAt(0).toUpperCase()}${label.slice(1)} masqué(e)`;
}

type LineKind = "name" | "heading" | "bullet" | "text" | "blank";

function classify(line: string, isFirst: boolean): LineKind {
  const t = line.trim();
  if (!t) return "blank";
  if (BULLET_RE.test(line)) return "bullet";
  const letters = t.replace(/[^A-Za-zÀ-ÿ]/g, "");
  const upper = letters.length >= 3 && letters === letters.toUpperCase();
  if (upper && t.length <= 60 && !REDACTION_RE.test(t)) {
    REDACTION_RE.lastIndex = 0;
    return isFirst ? "name" : "heading";
  }
  REDACTION_RE.lastIndex = 0;
  if (t.length <= 42 && t.endsWith(":")) return "heading";
  if (isFirst && t.length <= 48 && !t.includes("@")) return "name";
  return "text";
}

/** Rend un morceau [from, to) du texte : étiquettes de masquage + surlignage de la citation, offsets exacts. */
function Inline({ text, from, to, hl, markRef }: { text: string; from: number; to: number; hl: { start: number; end: number; key: number } | null; markRef: RefObject<HTMLElement | null> }) {
  const cuts = new Set([from, to]);
  const redactions: [number, number][] = [];
  REDACTION_RE.lastIndex = 0;
  const slice = text.slice(from, to);
  for (const m of slice.matchAll(REDACTION_RE)) {
    const s = from + (m.index ?? 0);
    redactions.push([s, s + m[0].length]);
    cuts.add(s);
    cuts.add(s + m[0].length);
  }
  if (hl) {
    if (hl.start > from && hl.start < to) cuts.add(hl.start);
    if (hl.end > from && hl.end < to) cuts.add(hl.end);
  }
  const points = [...cuts].sort((a, b) => a - b);
  const out: ReactNode[] = [];
  let firstMarked = true;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    if (a >= b) continue;
    const piece = text.slice(a, b);
    const isRed = redactions.some(([s, e]) => a >= s && b <= e);
    let node: ReactNode = isRed ? (
      <span className="cv-redacted" title="Donnée écartée à l'import : jamais stockée ni envoyée à l'IA">
        <EyeOff className="size-3" aria-hidden />
        {redactionLabel(piece)}
      </span>
    ) : (
      piece
    );
    const inHl = hl && a >= hl.start && b <= hl.end;
    if (inHl) {
      node = (
        <mark key={`m${hl!.key}-${a}`} ref={firstMarked ? (markRef as RefObject<HTMLElement>) : undefined} className="cv-highlight">
          {node}
        </mark>
      );
      firstMarked = false;
    } else {
      node = <span key={a}>{node}</span>;
    }
    out.push(node);
  }
  return <>{out}</>;
}

function CvText({ text, range }: { text: string; range: Range | null }) {
  const markRef = useRef<HTMLElement>(null);
  const [raw, setRaw] = useState(false);
  useLayoutEffect(() => {
    markRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [range?.key, raw]);

  const hl = range && range.start >= 0 && range.end <= text.length && range.start < range.end ? range : null;

  // Découpe en lignes en gardant les offsets d'origine (le surlignage reste exact).
  const lines: { start: number; end: number }[] = [];
  let pos = 0;
  for (const l of text.split("\n")) {
    lines.push({ start: pos, end: pos + l.length });
    pos += l.length + 1;
  }
  let seenContent = false;

  return (
    <div className="px-5 pb-5">
      <div className="mb-3 flex justify-end">
        <div className="bg-muted inline-flex rounded-full p-0.5 text-xs" role="radiogroup" aria-label="Affichage du CV">
          {[false, true].map((r) => (
            <button
              key={String(r)}
              role="radio"
              aria-checked={raw === r}
              onClick={() => setRaw(r)}
              className={cn("cursor-pointer rounded-full px-3 py-1 font-medium transition-all", raw === r ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
            >
              {r ? "Texte brut" : "Mise en forme"}
            </button>
          ))}
        </div>
      </div>
      <div className="cv-paper max-h-[68vh] overflow-auto">
        {raw ? (
          <div className="font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap">
            <Inline text={text} from={0} to={text.length} hl={hl} markRef={markRef} />
          </div>
        ) : (
          lines.map(({ start, end }, i) => {
            const line = text.slice(start, end);
            const kind = classify(line, !seenContent);
            if (kind !== "blank") seenContent = true;
            if (kind === "blank") return <div key={i} className="h-2" />;
            if (kind === "name")
              return (
                <div key={i} className="cv-name">
                  <Inline text={text} from={start} to={end} hl={hl} markRef={markRef} />
                </div>
              );
            if (kind === "heading")
              return (
                <div key={i} className="cv-heading">
                  <Inline text={text} from={start} to={end} hl={hl} markRef={markRef} />
                </div>
              );
            if (kind === "bullet") {
              const pre = line.match(BULLET_RE)![0].length;
              return (
                <div key={i} className="cv-bullet">
                  <span className="cv-dot" aria-hidden />
                  <span>
                    <Inline text={text} from={start + pre} to={end} hl={hl} markRef={markRef} />
                  </span>
                </div>
              );
            }
            const period = line.match(PERIOD_RE);
            if (period) {
              const ps = start + period[1].length, pe = ps + period[2].length;
              return (
                <div key={i} className="cv-line">
                  <span className="cv-period">
                    <Inline text={text} from={ps} to={pe} hl={hl} markRef={markRef} />
                  </span>{" "}
                  <Inline text={text} from={pe} to={end} hl={hl} markRef={markRef} />
                </div>
              );
            }
            return (
              <div key={i} className="cv-line">
                <Inline text={text} from={start} to={end} hl={hl} markRef={markRef} />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// --- Onglet Analyse ----------------------------------------------------------

function AnalysisTab({
  cand,
  criteria,
  onQuote,
  activeCriterion,
}: {
  cand: CandidateDetail;
  criteria: Criterion[];
  onQuote: (e: Evidence) => void;
  activeCriterion: string | null;
}) {
  const a = cand.analysis!;
  const label = (id: string) => criteria.find((c) => c.id === id)?.label ?? id;
  const removed = Object.entries(cand.removed ?? {}).filter(([, n]) => n > 0);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="text-muted-foreground size-4" /> Résumé
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-relaxed">{a.summary}</p>
        </CardContent>
      </Card>

      <Card className="gap-3">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListChecks className="text-muted-foreground size-4" /> Lecture critère par critère
          </CardTitle>
          <CardDescription>Cliquez sur une citation pour la retrouver dans le CV.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-muted-foreground text-left text-xs">
                <tr>
                  <th className="px-3 py-2 font-medium">Critère</th>
                  <th className="px-3 py-2 font-medium">Évaluation</th>
                  <th className="px-3 py-2 font-medium">Citation du CV</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {a.evidence.map((e) => (
                  <tr key={e.criterion_id} className={cn("align-top", activeCriterion === e.criterion_id && "bg-accent/50")}>
                    <td className="px-3 py-2.5">
                      <div className="font-medium">{label(e.criterion_id)}</div>
                      <div className="text-muted-foreground font-mono text-xs">{e.criterion_id}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      <EvidenceBadge assessment={e.assessment} quote={e.quote} />
                    </td>
                    <td className="px-3 py-2.5">
                      {e.quote ? (
                        <button
                          onClick={() => onQuote(e)}
                          className="hover:bg-accent group flex cursor-pointer items-start gap-1.5 rounded px-1 py-0.5 text-left italic"
                          title="Afficher dans le CV"
                        >
                          <Quote className="text-muted-foreground group-hover:text-primary mt-0.5 size-3.5 shrink-0" aria-hidden />
                          <span className="underline decoration-dotted underline-offset-4">{e.quote}</span>
                        </button>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <AssessmentLegend />
        </CardContent>
      </Card>

      {a.points_to_clarify.length > 0 && (
        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="text-muted-foreground size-4" /> Points à clarifier
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {a.points_to_clarify.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-5 sm:grid-cols-2">
        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <EyeOff className="text-muted-foreground size-4" /> Données écartées à l'import
            </CardTitle>
            <CardDescription className="text-xs">Masquées avant tout stockage et toute analyse.</CardDescription>
          </CardHeader>
          <CardContent>
            {removed.length === 0 ? (
              <p className="text-muted-foreground text-sm">Aucune donnée personnelle détectée.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {removed.map(([cat, n]) => (
                  <li key={cat} className="flex justify-between gap-2">
                    <span>{REMOVED_LABELS[cat] ?? cat}</span>
                    <span className="text-muted-foreground font-mono">× {n}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card className="gap-3">
          <CardHeader>
            <CardTitle className="text-sm">Traçabilité</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Modèle</span>
              <code className="font-mono text-xs">{a.model}</code>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-muted-foreground">Version du prompt</span>
              <code className="font-mono text-xs">v{a.prompt_version}</code>
            </div>
            <p className={cn("pt-1 text-xs", a.dropped_quotes > 0 ? "text-partial-fg" : "text-muted-foreground")}>
              {a.dropped_quotes} citation{a.dropped_quotes > 1 ? "s" : ""} écartée{a.dropped_quotes > 1 ? "s" : ""} car introuvable
              {a.dropped_quotes > 1 ? "s" : ""} dans le CV
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// --- Onglet Questions d'entretien -------------------------------------------

function QuestionsTab({
  cand,
  criteria,
  model,
  onUpdated,
}: {
  cand: CandidateDetail;
  criteria: Criterion[];
  model: ModelKey;
  onUpdated: (qs: CandidateDetail["questions"]) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const label = (id: string | null) => (id ? (criteria.find((c) => c.id === id)?.label ?? id) : null);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.generateQuestions(cand.id, model);
      onUpdated(r.questions);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-muted-foreground text-sm">Questions ouvertes pour vérifier en entretien ce que le CV ne dit pas, ou pas clairement.</p>
        <Button onClick={generate} disabled={busy}>
          <MessageCircleQuestion className={cn(busy && "animate-pulse")} />
          {busy ? "Génération…" : cand.questions.length ? "Régénérer" : "Générer des questions"}
        </Button>
      </div>
      <ErrorNote error={error} />
      {cand.questions.length === 0 && !busy && <p className="text-muted-foreground text-sm">Aucune question générée pour l'instant.</p>}
      <ol className="space-y-3">
        {cand.questions.map((q, i) => (
          <li key={i} className="bg-card rounded-lg border p-4">
            <div className="flex gap-3">
              <span className="bg-primary/10 text-primary grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold">{i + 1}</span>
              <div className="min-w-0 space-y-1.5">
                <p className="font-medium">{q.question}</p>
                <p className="text-muted-foreground text-sm">{q.rationale}</p>
                {label(q.criterion_id) && (
                  <Badge variant="secondary" className="font-normal">
                    <span className="font-mono">{q.criterion_id}</span> · {label(q.criterion_id)}
                  </Badge>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

// --- Onglet Poser une question (streaming, non conservé) ---------------------

type Msg = { role: "user" | "assistant"; text: string; error?: boolean };

function AskTab({ cand, model }: { cand: CandidateDetail; model: ModelKey }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [streaming, setStreaming] = useState(false);
  const ctrl = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => () => ctrl.current?.abort(), []);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [msgs]);

  const send = async () => {
    const question = q.trim();
    if (!question || streaming) return;
    setQ("");
    setMsgs((m) => [...m, { role: "user", text: question }, { role: "assistant", text: "" }]);
    setStreaming(true);
    const c = new AbortController();
    ctrl.current = c;
    const appendLast = (fn: (m: Msg) => Msg) => setMsgs((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);
    try {
      await api.ask(cand.id, question, model, (t) => appendLast((m) => ({ ...m, text: m.text + t })), c.signal);
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") appendLast((m) => ({ ...m, error: true, text: m.text || (e instanceof Error ? e.message : "Erreur") }));
    } finally {
      setStreaming(false);
      ctrl.current = null;
    }
  };

  return (
    <div className="space-y-4">
      <div className="border-partial-border bg-partial-bg/50 text-partial-fg flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
        <EyeOff className="size-4 shrink-0" aria-hidden />
        <span>
          <strong className="font-semibold">Les échanges ne sont pas enregistrés.</strong> Ils disparaissent dès que vous quittez cette fiche.
          L'assistant répond uniquement à partir du CV et ne recommande pas.
        </span>
      </div>

      <div className="bg-card min-h-48 space-y-3 rounded-lg border p-4">
        {msgs.length === 0 && (
          <p className="text-muted-foreground text-sm">Exemple : « Quelles technologies de base de données sont mentionnées, et dans quel contexte ? »</p>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap",
                m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
                m.error && "bg-destructive/10 text-destructive",
              )}
            >
              {m.text || (streaming && i === msgs.length - 1 ? <span className="text-muted-foreground animate-pulse">…</span> : null)}
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="flex items-end gap-2"
      >
        <Textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Votre question sur ce CV…"
          rows={2}
          className="bg-card"
          aria-label="Question sur le CV"
        />
        {streaming ? (
          <Button type="button" variant="outline" onClick={() => ctrl.current?.abort()} aria-label="Arrêter">
            <Square /> Arrêter
          </Button>
        ) : (
          <Button type="submit" disabled={!q.trim()}>
            <Send /> Envoyer
          </Button>
        )}
      </form>
    </div>
  );
}

// --- Effacement ----------------------------------------------------------------

function EraseButton({ cand, onErased }: { cand: CandidateDetail; onErased: (p: ErasureProof) => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = async (e: { preventDefault(): void }) => {
    e.preventDefault(); // garder le dialogue ouvert pendant l'appel
    setBusy(true);
    setError(null);
    try {
      const proof = await api.erase(cand.id);
      setOpen(false);
      onErased(proof);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={(o) => !busy && setOpen(o)}>
      <AlertDialogTrigger asChild>
        <Button variant="outline" className="text-destructive hover:bg-destructive/10 hover:text-destructive border-destructive/40">
          <Trash2 /> Effacer
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Effacer définitivement « {cand.display_name} » ?</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>Seront supprimés : le texte du CV, l'analyse, les citations et les questions d'entretien. Le fichier de base est ensuite compacté puis vérifié.</p>
              <p>Cette action est irréversible. Une preuve d'effacement (sans nom ni texte) sera conservée au journal.</p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <ErrorNote error={error} />
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Annuler</AlertDialogCancel>
          <AlertDialogAction onClick={run} disabled={busy}>
            <Trash2 /> {busy ? "Effacement…" : "Effacer définitivement"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// --- Vue principale ------------------------------------------------------------

export function CandidateView({ id, model }: { id: string; model: ModelKey }) {
  const [cand, setCand] = useState<CandidateDetail | null>(null);
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [range, setRange] = useState<Range | null>(null);
  const [activeCriterion, setActiveCriterion] = useState<string | null>(null);
  const [proof, setProof] = useState<ErasureProof | null>(null);
  const [reBusy, setReBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setCand(await api.getCandidate(id));
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [id]);

  useEffect(() => {
    load();
    api
      .getJob()
      .then((j) => setCriteria(j.criteria))
      .catch(() => {});
  }, [load]);

  const busy = cand ? isBusy(cand.status) : false;
  useEffect(() => {
    if (!busy || proof) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [busy, load, proof]);

  const showQuote = (e: Evidence) => {
    if (!cand?.redacted_text || !e.quote) return;
    let start = e.start ?? -1;
    let end = e.end ?? -1;
    if (start < 0 || end <= start || cand.redacted_text.slice(start, end) !== e.quote) {
      start = cand.redacted_text.indexOf(e.quote);
      end = start + e.quote.length;
    }
    if (start < 0) return;
    setActiveCriterion(e.criterion_id);
    setRange({ start, end, key: Date.now() });
  };

  const reanalyze = async () => {
    setReBusy(true);
    try {
      await api.reanalyze(id, model);
      setRange(null);
      await load();
    } catch (e) {
      setError(e);
    } finally {
      setReBusy(false);
    }
  };

  if (proof) {
    return (
      <div className="mx-auto max-w-3xl space-y-5">
        <h1 className="text-2xl font-semibold tracking-tight">Candidat effacé</h1>
        <p className="text-muted-foreground text-sm">Preuve d'effacement produite par le serveur local et inscrite au journal.</p>
        <ErasureProofCard proof={proof} />
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => navigate("/candidats")}>
            <ArrowLeft /> Retour à la liste des candidats
          </Button>
          <Button variant="outline" onClick={() => navigate("/effacements")}>
            Voir le journal des effacements
          </Button>
        </div>
      </div>
    );
  }

  if (!cand) {
    return error ? (
      <div className="space-y-4">
        <BackLink />
        <ErrorNote error={error} />
      </div>
    ) : (
      <Spinner />
    );
  }

  const ready = cand.status === "ready" && cand.analysis;

  return (
    <div className="space-y-5">
      <BackLink />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{cand.display_name}</h1>
          <StatusBadge status={cand.status} />
        </div>
        <div className="flex flex-wrap gap-2">
          {(cand.status === "ready" || cand.status === "error") && (
            <Button variant="outline" onClick={reanalyze} disabled={reBusy}>
              <RefreshCw className={cn(reBusy && "animate-spin")} /> Ré-analyser
            </Button>
          )}
          <EraseButton cand={cand} onErased={setProof} />
        </div>
      </div>
      <ErrorNote error={error} />
      {ready && cand.reason && (
        <div className="border-partial-border bg-partial-bg/40 text-partial-fg flex items-start gap-2 rounded-lg border px-3 py-2 text-sm">
          <ScanLine className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            {cand.reason} : texte transcrit par le modèle de vision local, à vérifier sur le document d'origine.
          </span>
        </div>
      )}

      {!ready ? (
        <Card>
          <CardContent>
            {busy ? (
              <Spinner label={cand.status === "pending" ? "En attente d'analyse (un CV à la fois)…" : "Analyse en cours par le modèle local…"} />
            ) : (
              <div className="space-y-1 text-sm">
                <p className="font-medium">{cand.status === "unsupported" ? "Fichier illisible" : "L'analyse a échoué"}</p>
                {cand.reason && <p className="text-muted-foreground">{cand.reason}</p>}
                <p className="text-muted-foreground pt-2">Vous pouvez effacer ce fichier, puis le réimporter dans un autre format.</p>
              </div>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
          <Tabs defaultValue="analyse">
            <TabsList>
              <TabsTrigger value="analyse">
                <ListChecks /> Analyse
              </TabsTrigger>
              <TabsTrigger value="questions">
                <MessageCircleQuestion /> Questions d'entretien
              </TabsTrigger>
              <TabsTrigger value="ask">
                <MessagesSquare /> Poser une question
              </TabsTrigger>
            </TabsList>
            <TabsContent value="analyse">
              <AnalysisTab cand={cand} criteria={criteria} onQuote={showQuote} activeCriterion={activeCriterion} />
            </TabsContent>
            <TabsContent value="questions">
              <QuestionsTab cand={cand} criteria={criteria} model={model} onUpdated={(questions) => setCand({ ...cand, questions })} />
            </TabsContent>
            <TabsContent value="ask">
              <AskTab cand={cand} model={model} />
            </TabsContent>
          </Tabs>

          <Card className="gap-3 lg:sticky lg:top-20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <span className="logo-badge grid size-7 place-items-center rounded-lg text-white shadow-sm">
                  <FileText className="size-3.5" />
                </span>
                CV — version masquée
              </CardTitle>
              <CardDescription className="text-xs">
                Seule version conservée. Il sert à vérifier chaque citation (cliquez une citation dans l'analyse pour la retrouver ici) et à
                contrôler le masquage : les données écartées apparaissent comme <span className="cv-redacted"><EyeOff className="size-3" aria-hidden />retiré</span>.
              </CardDescription>
            </CardHeader>
            <CvText text={cand.redacted_text ?? ""} range={range} />
          </Card>
        </div>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <a href="#/candidats" className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm">
      <ArrowLeft className="size-4" /> Candidats
    </a>
  );
}
