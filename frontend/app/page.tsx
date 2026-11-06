"use client";

import Link from "next/link";
import {
  Activity,
  Briefcase,
  CheckCircle2,
  Cpu,
  FileStack,
  Hourglass,
  Upload,
  Users,
} from "lucide-react";
import { EmptyState, ErrorBanner, Gauge, Notice, PageHeader, Stat } from "@/components/common";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton } from "@/components/ui/primitives";
import type { SystemStatus } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { N_, useI18n } from "@/lib/i18n";

interface Dashboard {
  total_applications: number;
  active_candidates: number;
  processed_cvs: number;
  failed_cvs: number;
  pending_extractions: number;
  pending_analyses: number;
  job_descriptions: number;
  completed_analyses: number;
  recent_activity: { id: number; ts: string; type: string; candidate_id: string | null; candidate_label: string | null; job_id: string | null; job_title: string | null }[];
}

const EVENT_LABELS: Record<string, string> = {
  document_imported: N_("CV imported"),
  text_extracted: N_("Document read"),
  profile_extracted: N_("Profile extracted"),
  embeddings_created: N_("Indexed for search"),
  embeddings_failed: N_("Search indexing failed"),
  processing_completed: N_("Processing completed"),
  processing_failed: N_("Processing failed"),
  job_created: N_("Job description created"),
  job_updated: N_("Job description updated"),
  job_deleted: N_("Job description deleted"),
  analysis_requested: N_("Analysis requested"),
  analysis_completed: N_("Analysis completed"),
  interview_requested: N_("Interview preparation requested"),
  interview_completed: N_("Interview preparation ready"),
  conversation_started: N_("Assistant conversation started"),
};

export default function DashboardPage() {
  const { t, timeAgo, gb } = useI18n();
  const dash = useResource<Dashboard>("/api/dashboard", { pollMs: 5000 });
  const sys = useResource<SystemStatus>("/api/system/status", { pollMs: 10000 });
  const d = dash.data;
  const s = sys.data;

  return (
    <>
      <PageHeader
        title={t("Dashboard")}
        description={t("Overview of applications and of the local AI engine.")}
        actions={
          <>
            <Button variant="outline" asChild><Link href="/jobs/new"><Briefcase /> {t("New job description")}</Link></Button>
            <Button asChild><Link href="/candidates/import"><Upload /> {t("Import CVs")}</Link></Button>
          </>
        }
      />
      {dash.error && <ErrorBanner message={dash.error} />}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {d ? (
          <>
            <Stat label={t("Applications")} value={d.total_applications} icon={FileStack} hint={t("CVs imported")} />
            <Stat label={t("Active candidates")} value={d.active_candidates} icon={Users} hint={t("Profiles ready")} />
            <Stat label={t("Processed CVs")} value={d.processed_cvs} icon={CheckCircle2} hint={d.failed_cvs ? t("{n} failed", { n: d.failed_cvs }) : t("No failures")} />
            <Stat label={t("Pending extractions")} value={d.pending_extractions} icon={Hourglass} hint={t("Waiting or in progress")} />
            <Stat label={t("Pending analyses")} value={d.pending_analyses} icon={Activity} hint={t("{n} completed", { n: d.completed_analyses })} />
            <Stat label={t("Job descriptions")} value={d.job_descriptions} icon={Briefcase} />
          </>
        ) : (
          Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[98px]" />)
        )}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("Recent activity")}</CardTitle>
            <CardDescription>{t("Latest events on this computer.")}</CardDescription>
          </CardHeader>
          <CardContent>
            {d && d.recent_activity.length === 0 && (
              <EmptyState icon={Upload} title={t("No activity yet")} action={<Button asChild size="sm"><Link href="/candidates/import">{t("Import your first CVs")}</Link></Button>}>
                {t("Import CVs (PDF, Word or text) to start. Demo data:")} <code className="rounded bg-muted px-1">python -m app.demo.seed</code>.
              </EmptyState>
            )}
            <ul className="divide-y">
              {d?.recent_activity.map((e) => (
                <li key={e.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <div className="min-w-0">
                    <span className="font-medium">{EVENT_LABELS[e.type] ? t(EVENT_LABELS[e.type]) : e.type}</span>
                    {e.candidate_label && e.candidate_id && (
                      <> · <Link className="text-primary hover:underline" href={`/candidates/${e.candidate_id}`}>{e.candidate_label}</Link></>
                    )}
                    {e.job_title && e.job_id && (
                      <> · <Link className="text-muted-foreground hover:underline" href={`/jobs/${e.job_id}`}>{e.job_title}</Link></>
                    )}
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">{timeAgo(e.ts)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Cpu className="size-4" /> {t("Local AI engine")}</CardTitle>
            <CardDescription>{t("Runs on this computer — nothing is sent online.")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!s && <Skeleton className="h-40" />}
            {s && (
              <>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                  <dt className="text-muted-foreground">{t("Connection")}</dt>
                  <dd className={s.ollama.reachable ? "text-success" : "text-destructive"}>
                    {s.ollama.reachable ? t("Connected (Ollama {v})", { v: s.ollama.version || "?" }) : t("Not reachable")}
                  </dd>
                  <dt className="text-muted-foreground">{t("Analysis model")}</dt>
                  <dd className={s.active_model_available ? "" : "text-warning"}>{s.active_model}</dd>
                  <dt className="text-muted-foreground">{t("Search model")}</dt>
                  <dd className={s.embedding_model_available ? "" : "text-warning"}>{s.embedding_model}</dd>
                  <dt className="text-muted-foreground">{t("In memory")}</dt>
                  <dd>{s.running_models.length ? s.running_models.map((m) => m.name).join(", ") : t("none")}</dd>
                  <dt className="text-muted-foreground">{t("Queue")}</dt>
                  <dd>{s.queue.pending ? t("{n} task(s)", { n: s.queue.pending }) : t("idle")}</dd>
                  <dt className="text-muted-foreground">{t("Scanned PDF (OCR)")}</dt>
                  <dd>{s.ocr_available ? t("available") : t("not installed")}</dd>
                </dl>
                <div className="flex flex-wrap justify-around gap-4 border-t pt-4">
                  <Gauge label={t("RAM")} used={s.hardware.ram_total_mb - s.hardware.ram_available_mb} total={s.hardware.ram_total_mb}
                    caption={`${gb(s.hardware.ram_total_mb - s.hardware.ram_available_mb)} / ${gb(s.hardware.ram_total_mb)}`} />
                  {s.hardware.gpus.map((g) => (
                    <Gauge key={g.name} label={t("GPU memory")} used={g.vram_used_mb} total={g.vram_total_mb}
                      caption={`${gb(g.vram_used_mb)} / ${gb(g.vram_total_mb)}`} />
                  ))}
                </div>
                {s.issues.map((i) => (
                  <Notice key={i} tone="warning">{i}</Notice>
                ))}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
