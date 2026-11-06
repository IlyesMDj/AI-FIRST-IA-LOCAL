"use client";

import Link from "next/link";
import { useState } from "react";
import { ClipboardList, Loader2, MessageSquareQuote, Play } from "lucide-react";
import { EmptyState, ErrorBanner } from "@/components/common";
import { Badge, Button, Progress, Select } from "@/components/ui/primitives";
import { api, type Analysis, type Job } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { N_, useI18n } from "@/lib/i18n";

const STATUS: Record<Analysis["status"], { label: string; variant: "warning" | "info" | "success" | "danger" }> = {
  pending: { label: N_("Queued"), variant: "warning" },
  processing: { label: N_("Running"), variant: "info" },
  completed: { label: N_("Ready"), variant: "success" },
  failed: { label: N_("Failed"), variant: "danger" },
};

export function AnalysisRows({ items, show }: { items: Analysis[]; show: "job" | "candidate" }) {
  const { t, formatDate } = useI18n();
  return (
    <ul className="divide-y rounded-lg border bg-card">
      {items.map((a) => (
        <li key={a.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            {a.kind === "interview" ? <MessageSquareQuote className="size-4 shrink-0 text-muted-foreground" /> : <ClipboardList className="size-4 shrink-0 text-muted-foreground" />}
            <div className="min-w-0">
              <Link href={`/analyses/${a.id}`} className="block truncate text-sm font-medium hover:underline">
                {a.kind === "interview" ? t("Interview preparation") : t("Requirement analysis")} · {show === "job" ? a.job_title : a.candidate_name}
              </Link>
              <div className="text-xs text-muted-foreground">{formatDate(a.created_at)}{a.model && ` · ${a.model}`}</div>
              {a.status === "failed" && a.error_message && <div className="text-xs text-destructive">{a.error_message}</div>}
            </div>
          </div>
          <div className="flex w-full items-center gap-3 sm:w-48">
            {a.status === "processing" ? <div className="flex-1"><Progress value={a.progress} /></div> : <div className="flex-1" />}
            <Badge variant={STATUS[a.status].variant}>
              {a.status === "processing" && <Loader2 className="animate-spin" />}
              {t(STATUS[a.status].label)}
            </Badge>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function CandidateAnalyses({ candidateId, kind, disabled }: { candidateId: string; kind: "analysis" | "interview"; disabled?: boolean }) {
  const { t } = useI18n();
  const jobs = useResource<Job[]>("/api/jobs");
  const list = useResource<Analysis[]>(`/api/analyses?candidate_id=${candidateId}&kind=${kind}`, {
    pollMs: 2500,
    pollWhile: (d) => d.some((a) => a.status === "pending" || a.status === "processing"),
  });
  const [jobId, setJobId] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const launch = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.post(kind === "interview" ? "/api/analyses/interview" : "/api/analyses", { candidate_ids: [candidateId], job_id: jobId });
      await list.reload();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 rounded-lg border bg-card p-4 sm:flex-row sm:items-center">
        <div className="flex-1 text-sm">
          <div className="font-medium">{kind === "interview" ? t("Prepare an interview") : t("Analyse against a job description")}</div>
          <div className="text-muted-foreground">
            {kind === "interview"
              ? t("Generates job-related questions grouped by theme, with the CV evidence behind each one.")
              : t("Checks each requirement for evidence in the CV. No score and no recommendation.")}
          </div>
        </div>
        <Select className="sm:w-64" value={jobId} onChange={(e) => setJobId(e.target.value)} aria-label={t("Job description")}>
          <option value="">{t("Choose a job description…")}</option>
          {jobs.data?.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
        </Select>
        <Button onClick={launch} disabled={!jobId || busy || disabled}><Play /> {kind === "interview" ? t("Generate") : t("Analyse")}</Button>
      </div>
      {jobs.data?.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("No job description yet.")} <Link className="text-primary hover:underline" href="/jobs/new">{t("Create one")}</Link>.</p>
      )}
      {err && <ErrorBanner message={err} />}
      {list.data && list.data.length === 0 && (
        <EmptyState icon={kind === "interview" ? MessageSquareQuote : ClipboardList} title={kind === "interview" ? t("No interview preparation yet") : t("No analysis yet")}>
          {t("Select a job description above to start. Processing runs locally and may take a minute.")}
        </EmptyState>
      )}
      {list.data && list.data.length > 0 && <AnalysisRows items={list.data} show="job" />}
    </div>
  );
}
