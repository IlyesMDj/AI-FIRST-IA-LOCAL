"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ClipboardList, Columns3, MessageSquareQuote, Pencil, Play, Trash2 } from "lucide-react";
import { AnalysisRows } from "@/components/analysis-list";
import { EmptyState, ErrorBanner, Notice } from "@/components/common";
import { JobForm } from "@/components/job-form";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton } from "@/components/ui/primitives";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, type Analysis, type CandidateSummary, type Job } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { N_, useI18n } from "@/lib/i18n";
import { candidateLabel } from "@/lib/utils";

const KIND_LABELS: Record<string, string> = {
  skill: N_("skill"), experience: N_("experience"), education: N_("education"), language: N_("language"), criterion: N_("criterion"),
};

export default function JobPage() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const job = useResource<Job>(`/api/jobs/${id}`);
  const crit = useResource<{ id: string; kind: string; importance: string; requirement: string }[]>(`/api/jobs/${id}/criteria`);
  const cands = useResource<CandidateSummary[]>("/api/candidates?status=completed");
  const analyses = useResource<Analysis[]>(`/api/analyses?job_id=${id}`, {
    pollMs: 2500,
    pollWhile: (d) => d.some((a) => a.status === "pending" || a.status === "processing"),
  });
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [confirmDel, setConfirmDel] = useState(false);

  if (job.error) return <EmptyState title={t("Job description not found")}>{job.error}</EmptyState>;
  if (!job.data) return <Skeleton className="h-96" />;
  const j = job.data;

  const launch = async (kind: "analysis" | "interview") => {
    setErr(null);
    try {
      await api.post(kind === "interview" ? "/api/analyses/interview" : "/api/analyses", { candidate_ids: selected, job_id: id });
      setSelected([]);
      analyses.reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  if (editing) {
    return (
      <div className="mx-auto max-w-4xl">
        <button onClick={() => setEditing(false)} className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> {t("Cancel editing")}</button>
        <JobForm initial={j} onSaved={() => { setEditing(false); job.reload(); crit.reload(); }} />
      </div>
    );
  }

  return (
    <>
      <Link href="/jobs" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> {t("Job descriptions")}</Link>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="hud-title text-xl font-semibold">{j.title}</h1>
          {j.description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{j.description}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setEditing(true)}><Pencil /> {t("Edit")}</Button>
          <Button variant="outline" className="text-destructive" onClick={() => setConfirmDel(true)}><Trash2 /> {t("Delete")}</Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>{t("Criteria checked")}</CardTitle>
            <CardDescription>{t("{n} criteria, each assessed separately.", { n: crit.data?.length ?? 0 })}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-sm">
              {crit.data?.map((c) => (
                <li key={c.id} className="flex items-start justify-between gap-2">
                  <span>{c.requirement}</span>
                  <Badge variant={c.importance === "required" ? "primary" : "outline"}>
                    {c.importance === "required" ? (KIND_LABELS[c.kind] ? t(KIND_LABELS[c.kind]) : c.kind) : t("optional")}
                  </Badge>
                </li>
              ))}
            </ul>
            {j.responsibilities.length > 0 && (
              <>
                <div className="mb-1 mt-4 text-xs font-medium text-muted-foreground">{t("Responsibilities")}</div>
                <ul className="list-disc space-y-0.5 pl-5 text-sm">{j.responsibilities.map((r) => <li key={r}>{r}</li>)}</ul>
              </>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>{t("Analyse candidates")}</CardTitle>
              <CardDescription>{t("Select processed candidates. Each candidate is analysed separately against the same criteria.")}</CardDescription>
            </CardHeader>
            <CardContent>
              {cands.data?.length === 0 && <p className="text-sm text-muted-foreground">{t("No processed candidate yet.")} <Link href="/candidates/import" className="text-primary hover:underline">{t("Import CVs")}</Link>.</p>}
              <div className="flex max-h-60 flex-wrap gap-2 overflow-y-auto">
                {cands.data?.map((c) => {
                  const on = selected.includes(c.id);
                  return (
                    <button key={c.id} type="button" onClick={() => setSelected((s) => (on ? s.filter((x) => x !== c.id) : [...s, c.id]))}
                      className={`rounded-full border px-3 py-1 text-sm ${on ? "border-primary bg-accent text-accent-foreground" : "hover:bg-secondary"}`} aria-pressed={on}>
                      {candidateLabel(c)}
                    </button>
                  );
                })}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button disabled={!selected.length} onClick={() => launch("analysis")}><Play /> {t("Analyse")} {selected.length || ""}</Button>
                <Button variant="outline" disabled={!selected.length} onClick={() => launch("interview")}><MessageSquareQuote /> {t("Prepare interviews")}</Button>
                <Button variant="outline" disabled={selected.length < 2 || selected.length > 4} onClick={() => router.push(`/compare?ids=${selected.join(",")}&job=${id}`)}><Columns3 /> {t("Compare")}</Button>
              </div>
              {err && <div className="mt-3"><ErrorBanner message={err} /></div>}
            </CardContent>
          </Card>
          <Notice>{t("Results show evidence per criterion. No score, ranking or recommendation is produced: the decision is yours.")}</Notice>
          {analyses.data && analyses.data.length > 0 ? <AnalysisRows items={analyses.data} show="candidate" /> : (
            <EmptyState icon={ClipboardList} title={t("No analysis for this job yet")}>{t("Select candidates above and start an analysis.")}</EmptyState>
          )}
        </div>
      </div>

      <Dialog open={confirmDel} onOpenChange={setConfirmDel}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("Delete this job description?")}</DialogTitle>
            <DialogDescription>{t("Analyses and interview preparations made for this job are deleted too. Candidates are kept.")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDel(false)}>{t("Cancel")}</Button>
            <Button variant="destructive" onClick={async () => { await api.del(`/api/jobs/${id}`); router.push("/jobs"); }}><Trash2 /> {t("Delete")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
