"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ChevronDown, Download, Loader2, Printer } from "lucide-react";
import { ASSESSMENT, AssessmentBadge, EmptyState, ErrorBanner, EvidenceQuote, Notice } from "@/components/common";
import { Badge, Button, Card, CardContent, Progress, Skeleton } from "@/components/ui/primitives";
import type { Analysis, AssessmentStatus, CriterionResult } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { useI18n, type Vars } from "@/lib/i18n";

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

type T = (k: string, v?: Vars) => string;

function toMarkdown(a: Analysis, t: T, formatDate: (s: string | null) => string): string {
  const r = a.result!;
  const lines = [`# ${a.kind === "interview" ? t("Interview preparation") : t("Requirement analysis")}`, "",
    `- ${t("Candidate:")} ${a.candidate_name}`, `- ${t("Job:")} ${a.job_title}`,
    `- ${t("Generated on {date} with {model} (local)", { date: formatDate(a.completed_at), model: a.model || "?" })}`, ""];
  if (r.criteria) {
    for (const c of r.criteria) {
      lines.push(`## ${c.requirement} (${c.importance === "required" ? t("required") : t("optional")})`, `**${t(ASSESSMENT[c.status].label)}**`, "", c.explanation, "");
      c.evidence.forEach((e) => lines.push(`> ${e.quote}${e.verified ? "" : ` _(${t("not found verbatim in the CV")})_`}`));
      if (c.relevant_experience) lines.push("", `${t("Relevant experience:")} ${c.relevant_experience}`);
      if (c.missing_information) lines.push("", `${t("To clarify:")} ${c.missing_information}`);
      lines.push("");
    }
    lines.push("---", r.disclaimer || "");
  }
  if (r.categories) {
    for (const cat of r.categories) {
      if (!cat.questions.length) continue;
      lines.push(`## ${cat.label}`, "");
      cat.questions.forEach((q, i) => {
        lines.push(`${i + 1}. **${q.question}**`, `   - ${t("Why it matters:")} ${q.why_relevant}`, `   - ${t("Competency:")} ${q.competency}`);
        if (q.evidence) lines.push(`   - CV: “${q.evidence.quote}”`);
      });
      lines.push("");
    }
  }
  return lines.join("\n");
}

const KIND_LABELS: Record<string, string> = { skill: "skill", experience: "experience", education: "education", language: "language", criterion: "criterion" };

function CriterionCard({ c }: { c: CriterionResult }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(c.status !== "not_found");
  const A = ASSESSMENT[c.status];
  return (
    <Card>
      <button type="button" className="flex w-full items-start gap-3 p-4 text-left" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <A.icon className={`mt-0.5 size-5 shrink-0 ${A.cls}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{c.requirement}</span>
            <Badge variant="outline">{c.importance === "required" ? t(KIND_LABELS[c.kind] || c.kind) : t("optional")}</Badge>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">{c.explanation}</p>
        </div>
        <AssessmentBadge status={c.status} />
        <ChevronDown className={`mt-0.5 size-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <CardContent className="space-y-3 border-t pt-4">
          {c.evidence.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs font-medium text-muted-foreground">{t("Evidence found in the CV")}</div>
              {c.evidence.map((e, i) => <EvidenceQuote key={i} e={e} />)}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{t("No quote from the CV supports this requirement.")}</p>
          )}
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs font-medium text-muted-foreground">{t("Relevant experience")}</dt>
              <dd>{c.relevant_experience || "—"}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-muted-foreground">{t("Missing or unclear information")}</dt>
              <dd>{c.missing_information || "—"}</dd>
            </div>
          </dl>
          {c.status === "not_found" && (
            <p className="text-xs text-muted-foreground">{t("Not mentioned in the CV — this does not mean the candidate lacks it. Consider asking during the interview.")}</p>
          )}
          {c.verification_notes.map((n) => <Notice key={n} tone="warning">{n}</Notice>)}
        </CardContent>
      )}
    </Card>
  );
}

export default function AnalysisPage() {
  const { t, formatDate } = useI18n();
  const { id } = useParams<{ id: string }>();
  const { data: a, error } = useResource<Analysis>(`/api/analyses/${id}`, {
    pollMs: 2000,
    pollWhile: (d) => d.status === "pending" || d.status === "processing",
  });
  const [filter, setFilter] = useState<AssessmentStatus | "">("");

  if (error) return <EmptyState title={t("Analysis not found")}>{error}</EmptyState>;
  if (!a) return <Skeleton className="h-96" />;
  const r = a.result;

  return (
    <>
      <Link href={`/candidates/${a.candidate_id}`} className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground print:hidden"><ArrowLeft className="size-4" /> {a.candidate_name}</Link>
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{a.kind === "interview" ? t("Interview preparation") : t("Requirement analysis")}</div>
          <h1 className="hud-title text-xl font-semibold">{a.candidate_name} <span className="font-normal text-muted-foreground">·</span> <Link href={`/jobs/${a.job_id}`} className="hover:underline">{a.job_title}</Link></h1>
          {a.completed_at && <p className="text-sm text-muted-foreground">{formatDate(a.completed_at)} · {t("local model {model}", { model: a.model || "?" })}</p>}
        </div>
        {a.status === "completed" && (
          <div className="flex gap-2 print:hidden">
            <Button variant="outline" onClick={() => download(`${a.kind}-${a.id.slice(0, 8)}.md`, toMarkdown(a, t, (s) => formatDate(s)))}><Download /> {t("Export")}</Button>
            <Button variant="outline" onClick={() => window.print()}><Printer /> {t("Print")}</Button>
          </div>
        )}
      </div>

      {(a.status === "pending" || a.status === "processing") && (
        <Card><CardContent className="space-y-2 p-5">
          <div className="flex items-center gap-2 text-sm font-medium"><Loader2 className="size-4 animate-spin" /> {a.status === "pending" ? t("Waiting for the local AI…") : t("The local AI is reading the CV…")}</div>
          <Progress value={a.status === "pending" ? 2 : a.progress} />
          <p className="text-xs text-muted-foreground">{t("Each requirement is checked separately. You can leave this page.")}</p>
        </CardContent></Card>
      )}
      {a.status === "failed" && <ErrorBanner message={a.error_message || t("The analysis failed.")} />}

      {r?.criteria && (
        <div className="space-y-4">
          <Notice>{r.disclaimer}</Notice>
          <div className="flex flex-wrap gap-2 print:hidden" role="group" aria-label={t("Filter by status")}>
            <Button size="sm" variant={filter === "" ? "secondary" : "ghost"} onClick={() => setFilter("")}>{t("All ({n})", { n: r.criteria.length })}</Button>
            {(Object.keys(ASSESSMENT) as AssessmentStatus[]).map((s) => {
              const n = r.criteria!.filter((c) => c.status === s).length;
              return n ? (
                <Button key={s} size="sm" variant={filter === s ? "secondary" : "ghost"} onClick={() => setFilter(s)}>{t(ASSESSMENT[s].label)} ({n})</Button>
              ) : null;
            })}
          </div>
          <div className="space-y-3">
            {r.criteria.filter((c) => !filter || c.status === filter).map((c) => <CriterionCard key={c.id} c={c} />)}
          </div>
        </div>
      )}

      {r?.categories && (
        <div className="space-y-4">
          <Notice>{r.disclaimer}</Notice>
          {r.categories.filter((c) => c.questions.length).map((cat) => (
            <Card key={cat.key}>
              <div className="border-b px-5 py-3 font-medium">{cat.label}</div>
              <CardContent className="divide-y p-0">
                {cat.questions.map((q, i) => (
                  <div key={i} className="space-y-2 px-5 py-4">
                    <div className="font-medium">{i + 1}. {q.question}</div>
                    <div className="grid gap-2 text-sm sm:grid-cols-2">
                      <div><span className="text-xs font-medium text-muted-foreground">{t("Why it matters:")} </span>{q.why_relevant}</div>
                      <div><span className="text-xs font-medium text-muted-foreground">{t("Competency:")} </span>{q.competency}</div>
                    </div>
                    {q.evidence && <EvidenceQuote e={q.evidence} />}
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
          {r.removed_questions ? (
            <p className="text-xs text-muted-foreground">{t("{n} generated question(s) were automatically removed because they touched on non-job-related or protected topics.", { n: r.removed_questions })}</p>
          ) : null}
        </div>
      )}
    </>
  );
}
