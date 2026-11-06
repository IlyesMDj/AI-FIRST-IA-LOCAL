"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Columns3 } from "lucide-react";
import { AssessmentBadge, EmptyState, ErrorBanner, Notice, PageHeader, VerificationMark } from "@/components/common";
import { Button, Card, Select, Skeleton } from "@/components/ui/primitives";
import { api, type CandidateSummary, type Certification, type CriterionResult, type Education, type Experience, type Job, type Project, type Skill } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { candidateLabel, cn } from "@/lib/utils";

interface Column {
  candidate_id: string;
  label: string;
  skills: Skill[];
  experience: Experience[];
  projects: Project[];
  education: Education[];
  certifications: Certification[];
  languages: { language: string; level: string | null }[];
  analysis: { id: string; criteria: Record<string, CriterionResult> } | null;
}
interface CompareData {
  job: { id: string; title: string } | null;
  criteria: { id: string; requirement: string; importance: string; kind: string }[];
  columns: Column[];
  disclaimer: string;
}

function Row({ title, cols, render }: { title: string; cols: Column[]; render: (c: Column) => React.ReactNode }) {
  return (
    <tr className="align-top">
      <th scope="row" className="sticky left-0 w-44 bg-card px-4 py-3 text-left text-xs font-medium text-muted-foreground">{title}</th>
      {cols.map((c) => <td key={c.candidate_id} className="min-w-[220px] border-l px-4 py-3 text-sm">{render(c)}</td>)}
    </tr>
  );
}

function CompareInner() {
  const { t, lang } = useI18n();
  const params = useSearchParams();
  const cands = useResource<CandidateSummary[]>("/api/candidates?status=completed");
  const jobs = useResource<Job[]>("/api/jobs");
  const [sel, setSel] = useState<string[]>((params.get("ids") || "").split(",").filter(Boolean));
  const [job, setJob] = useState(params.get("job") || "");
  const [data, setData] = useState<CompareData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const none = <span className="text-muted-foreground">{t("Not mentioned")}</span>;
  const date = (d: string | null) => (d === "present" ? t("present") : d || "?");

  useEffect(() => {
    if (sel.length < 2) {
      setData(null);
      return;
    }
    setLoading(true);
    api.post<CompareData>("/api/compare", { candidate_ids: sel, job_id: job || null })
      .then((d) => { setData(d); setErr(null); })
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false));
  }, [sel, job, lang]);

  return (
    <>
      <PageHeader title={t("Compare candidates")} description={t("Side-by-side view of the evidence in each CV. No overall score or winner.")} />
      <div className="mb-4 space-y-3 rounded-lg border bg-card p-4">
        <div className="flex flex-wrap gap-2">
          {cands.data?.map((c) => {
            const on = sel.includes(c.id);
            return (
              <button key={c.id} type="button" aria-pressed={on} disabled={!on && sel.length >= 4}
                onClick={() => setSel((s) => (on ? s.filter((x) => x !== c.id) : [...s, c.id]))}
                className={cn("rounded-full border px-3 py-1 text-sm disabled:opacity-40", on ? "border-primary bg-accent text-accent-foreground" : "hover:bg-secondary")}>
                {candidateLabel(c)}
              </button>
            );
          })}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Select className="sm:w-80" value={job} onChange={(e) => setJob(e.target.value)} aria-label={t("Job description")}>
            <option value="">{t("Without job description")}</option>
            {jobs.data?.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
          </Select>
          <span className="text-xs text-muted-foreground">{t("Select 2 to 4 candidates. With a job description, the latest analysis of each candidate is shown.")}</span>
        </div>
      </div>

      {err && <ErrorBanner message={err} />}
      {sel.length < 2 && <EmptyState icon={Columns3} title={t("Select at least two candidates")}>{t("Only processed candidates can be compared.")}</EmptyState>}
      {loading && !data && <Skeleton className="h-96" />}
      {data && (
        <div className="space-y-3">
          <Notice>{data.disclaimer}</Notice>
          <Card className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead className="border-b">
                <tr>
                  <th className="sticky left-0 bg-card" />
                  {data.columns.map((c) => (
                    <th key={c.candidate_id} className="border-l px-4 py-3 text-left">
                      <Link href={`/candidates/${c.candidate_id}`} className="font-semibold hover:underline">{c.label}</Link>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y">
                {data.job && data.criteria.map((cr) => (
                  <Row key={cr.id} title={`${cr.requirement}${cr.importance === "optional" ? ` (${t("optional")})` : ""}`} cols={data.columns} render={(c) => {
                    if (!c.analysis) return <Link className="text-xs text-primary hover:underline" href={`/jobs/${data.job!.id}`}>{t("Not analysed yet")}</Link>;
                    const r = c.analysis.criteria[cr.requirement];
                    if (!r) return <span className="text-xs text-muted-foreground">{t("Not in this analysis (job changed since)")}</span>;
                    const ev = r.evidence.find((e) => e.verified);
                    return (
                      <div className="space-y-1">
                        <AssessmentBadge status={r.status} short />
                        {ev && <p className="line-clamp-3 text-xs italic text-muted-foreground">“{ev.quote}”</p>}
                        {r.missing_information && <p className="text-xs text-muted-foreground">{t("To clarify:")} {r.missing_information}</p>}
                      </div>
                    );
                  }} />
                ))}
                <Row title={t("Skills")} cols={data.columns} render={(c) => {
                  const s = c.skills.filter((x) => x.category !== "soft");
                  return s.length ? <div className="flex flex-wrap gap-1">{s.map((x, i) => (
                    <span key={i} className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs", x.basis === "inferred" && "border-dashed text-muted-foreground")}>{x.name}<VerificationMark v={x.verification} /></span>
                  ))}</div> : none;
                }} />
                <Row title={t("Professional experience")} cols={data.columns} render={(c) => c.experience.length ? (
                  <ul className="space-y-1.5">{c.experience.map((e, i) => (
                    <li key={i}><div className="font-medium">{e.position || "?"}</div><div className="text-xs text-muted-foreground">{e.company} · {date(e.start_date)} – {date(e.end_date)}</div></li>
                  ))}</ul>) : none} />
                <Row title={t("Projects")} cols={data.columns} render={(c) => c.projects.length ? (
                  <ul className="space-y-1">{c.projects.map((p, i) => <li key={i}><span className="font-medium">{p.name}</span>{p.technologies.length > 0 && <span className="text-xs text-muted-foreground"> · {p.technologies.join(", ")}</span>}</li>)}</ul>) : none} />
                <Row title={t("Education")} cols={data.columns} render={(c) => c.education.length ? (
                  <ul className="space-y-1">{c.education.map((e, i) => <li key={i}>{e.degree}<div className="text-xs text-muted-foreground">{[e.institution, e.graduation_year].filter(Boolean).join(" · ")}</div></li>)}</ul>) : none} />
                <Row title={t("Certifications")} cols={data.columns} render={(c) => c.certifications.length ? c.certifications.map((x) => x.name).join(", ") : none} />
                <Row title={t("Languages")} cols={data.columns} render={(c) => c.languages.length ? c.languages.map((l) => `${l.language}${l.level ? ` (${l.level})` : ""}`).join(", ") : none} />
              </tbody>
            </table>
          </Card>
          <div className="flex justify-end"><Button variant="outline" asChild><Link href={`/assistant?ids=${sel.join(",")}`}>{t("Ask the assistant about these candidates")}</Link></Button></div>
        </div>
      )}
    </>
  );
}

export default function ComparePage() {
  return <Suspense><CompareInner /></Suspense>;
}
