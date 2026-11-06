"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ClipboardList,
  FileText,
  History,
  Mail,
  MessageSquareQuote,
  MessagesSquare,
  Phone,
  RefreshCw,
  ShieldAlert,
  Trash2,
  UserRound,
} from "lucide-react";
import { CandidateAnalyses } from "@/components/analysis-list";
import { ChatPanel } from "@/components/chat-panel";
import { CvText, useRedactionText } from "@/components/candidate/cv-text";
import { ProfileView } from "@/components/candidate/profile-view";
import { CandidateStatusBadge, EmptyState, ErrorBanner, Notice } from "@/components/common";
import { DeletionReportView } from "@/components/deletion-report";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Progress, Skeleton } from "@/components/ui/primitives";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type CandidateDetail, type Conversation, type DeletionReport } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { N_, useI18n } from "@/lib/i18n";
import { candidateLabel } from "@/lib/utils";

// Processing steps in the order the backend runs them (backend sends them translated).
const STEP_COUNT = 4;
const STEP_INDEX: Record<string, number> = {
  "Reading document": 0, "Lecture du document": 0,
  "Removing unnecessary personal data": 1, "Suppression des données personnelles inutiles": 1,
  "Extracting professional information": 2, "Extraction des informations professionnelles": 2,
  "Indexing for search": 3, "Indexation pour la recherche": 3,
};

const EVENT_LABELS: Record<string, string> = {
  document_imported: N_("Document received and stored locally"),
  text_extracted: N_("Text extracted and sensitive data removed"),
  profile_extracted: N_("Professional profile extracted by the local AI"),
  embeddings_created: N_("Search index created"),
  embeddings_failed: N_("Search index failed"),
  processing_completed: N_("Processing completed"),
  processing_failed: N_("Processing failed"),
  analysis_requested: N_("Analysis requested"),
  analysis_completed: N_("Analysis completed"),
  interview_requested: N_("Interview preparation requested"),
  interview_completed: N_("Interview preparation completed"),
  conversation_started: N_("Assistant conversation started"),
};

function DeleteDialog({ cand, onDeleted }: { cand: CandidateDetail; onDeleted: (r: DeletionReport) => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const del = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.del<{ report: DeletionReport }>(`/api/candidates/${cand.id}`);
      setOpen(false);
      onDeleted(r.report);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button variant="outline" className="text-destructive hover:text-destructive" onClick={() => setOpen(true)}><Trash2 /> {t("Delete")}</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("Delete {name} permanently?", { name: candidateLabel(cand) })}</DialogTitle>
            <DialogDescription>{t("This cannot be undone. The following will be removed from this application:")}</DialogDescription>
          </DialogHeader>
          <ul className="list-disc space-y-0.5 pl-5 text-sm">
            <li>{t("the original CV and any temporary files")}</li>
            <li>{t("extracted text, structured profile and search index (embeddings)")}</li>
            <li>{t("analyses, interview preparations and assistant conversations involving this candidate")}</li>
            <li>{t("this candidate's activity log entries")}</li>
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">
            {t("A verification report is produced. Copies outside the application (e-mails, downloads, backups) must be deleted separately.")}
          </p>
          {err && <div className="mt-3"><ErrorBanner message={err} /></div>}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{t("Cancel")}</Button>
            <Button variant="destructive" onClick={del} disabled={busy}><Trash2 /> {busy ? t("Deleting…") : t("Delete permanently")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function CandidateChat({ candidateId }: { candidateId: string }) {
  const [conv, setConv] = useState<Conversation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const list = await api.get<Conversation[]>(`/api/conversations?candidate_id=${candidateId}`);
        const own = list.find((c) => c.candidates.length === 1);
        setConv(own || (await api.post<Conversation>("/api/conversations", { candidate_ids: [candidateId] })));
      } catch (e) {
        setErr((e as Error).message);
      }
    })();
  }, [candidateId]);
  if (err) return <ErrorBanner message={err} />;
  if (!conv) return <Skeleton className="h-96" />;
  return <ChatPanel conversation={conv} />;
}

export default function CandidatePage() {
  const { t, formatDate, formatBytes } = useI18n();
  const redactionText = useRedactionText();
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: c, error, reload } = useResource<CandidateDetail>(`/api/candidates/${id}`, {
    pollMs: 2000,
    pollWhile: (d) => d.status === "pending" || d.status === "processing",
  });
  const life = useResource<{ ts: string; type: string; details: Record<string, unknown> }[]>(`/api/candidates/${id}/lifecycle`);
  const [tab, setTab] = useState("profile");
  const [highlight, setHighlight] = useState<{ start: number; end: number } | null>(null);
  const [report, setReport] = useState<DeletionReport | null>(null);

  const locate = (loc: { start: number; end: number }) => {
    setHighlight(loc);
    setTab("cv");
  };

  const reprocess = async () => {
    await api.post(`/api/candidates/${id}/process`);
    reload();
  };

  if (report) {
    return (
      <Card className="mx-auto max-w-2xl">
        <CardHeader><CardTitle>{t("Candidate deleted")}</CardTitle></CardHeader>
        <CardContent>
          <DeletionReportView report={report} />
          <div className="mt-6 flex gap-2">
            <Button onClick={() => router.push("/candidates")}>{t("Back to candidates")}</Button>
            <Button variant="outline" asChild><Link href="/privacy">{t("All deletion reports")}</Link></Button>
          </div>
        </CardContent>
      </Card>
    );
  }
  if (error) return <EmptyState title={t("Candidate not found")}>{error} <Link href="/candidates" className="text-primary hover:underline">{t("Back to candidates")}</Link></EmptyState>;
  if (!c) return <Skeleton className="h-[60vh]" />;

  const label = candidateLabel(c);
  const ready = c.status === "completed";
  const stepIdx = c.processing_step ? STEP_INDEX[c.processing_step] ?? 0 : 0;
  const knownWarning = (w: string) => /instructions (addressed to an AI|adressées à une IA)|may correspond|correspond peut-être/.test(w);

  return (
    <>
      <Link href="/candidates" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> {t("Candidates")}</Link>
      <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground"><UserRound className="size-5" /></div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="hud-title truncate text-xl font-semibold">{label}</h1>
              <CandidateStatusBadge status={c.status} />
              {c.ocr_used && <Badge variant="outline">{t("Scanned · OCR")}</Badge>}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
              {c.email && <span className="inline-flex items-center gap-1"><Mail className="size-3.5" /> {c.email}</span>}
              {c.phone && <span className="inline-flex items-center gap-1"><Phone className="size-3.5" /> {c.phone}</span>}
              <span className="inline-flex items-center gap-1"><FileText className="size-3.5" /> {c.original_filename} · {formatBytes(c.file_size)}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          {(c.status === "failed" || c.status === "completed" || c.status === "imported") && (
            <Button variant="outline" onClick={reprocess}><RefreshCw /> {c.status === "imported" ? t("Start processing") : t("Process again")}</Button>
          )}
          <DeleteDialog cand={c} onDeleted={setReport} />
        </div>
      </div>

      <div className="mb-5 space-y-2">
        {(c.status === "pending" || c.status === "processing") && (
          <Card>
            <CardContent className="space-y-2 p-4">
              <div className="flex justify-between text-sm">
                <span className="font-medium">{c.status === "pending" ? t("Waiting for the local AI…") : `${c.processing_step}…`}</span>
                <span className="text-muted-foreground">{t("step {i} of {n}", { i: stepIdx + 1, n: STEP_COUNT })}</span>
              </div>
              <Progress value={c.status === "pending" ? 3 : ((stepIdx + 0.5) / STEP_COUNT) * 100} />
              <p className="text-xs text-muted-foreground">{t("You can leave this page; processing continues in the background.")}</p>
            </CardContent>
          </Card>
        )}
        {c.status === "failed" && c.error_message && <ErrorBanner message={c.error_message} />}
        {c.injection_flags.length > 0 && (
          <Notice tone="warning" icon={ShieldAlert}>
            <strong>{t("Possible manipulation attempt.")}</strong>{" "}
            {t("This document contains text addressed to an AI (e.g. “{excerpt}”). It was treated as plain CV content and ignored as an instruction.", { excerpt: c.injection_flags[0].excerpt })}
          </Notice>
        )}
        {c.possible_duplicates.length > 0 && (
          <Notice tone="warning">
            {t("This profile may correspond to another candidate:")}{" "}
            {c.possible_duplicates.map((d, i) => (
              <span key={d.candidate_id}>{i > 0 && ", "}<Link className="text-primary hover:underline" href={`/candidates/${d.candidate_id}`}>{d.rule}</Link></span>
            ))}. {t("Nothing was merged — please review.")}
          </Notice>
        )}
        {c.warnings.filter((w) => !knownWarning(w)).map((w) => (
          <Notice key={w} tone="warning">{w}</Notice>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="profile"><UserRound /> {t("Profile")}</TabsTrigger>
          <TabsTrigger value="cv"><FileText /> {t("CV text")}</TabsTrigger>
          <TabsTrigger value="analyses" disabled={!ready}><ClipboardList /> {t("Analyses")}</TabsTrigger>
          <TabsTrigger value="interview" disabled={!ready}><MessageSquareQuote /> {t("Interview")}</TabsTrigger>
          <TabsTrigger value="assistant" disabled={!ready}><MessagesSquare /> {t("Assistant")}</TabsTrigger>
          <TabsTrigger value="data"><History /> {t("Data & history")}</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          {c.profile ? <ProfileView profile={c.profile} onLocate={locate} /> : (
            <EmptyState title={c.status === "failed" ? t("No profile could be extracted") : t("Profile not available yet")}>
              {c.status === "failed" ? t("Fix the problem above and process the document again.") : t("The profile appears here once the local AI has read the CV.")}
            </EmptyState>
          )}
        </TabsContent>
        <TabsContent value="cv">
          {c.text_method ? <CvText candidateId={c.id} highlight={highlight} hasOriginal={!!c.original_filename} /> : (
            <EmptyState title={t("The document has not been read yet")}>
              {["pdf", "jpg", "png"].includes(c.file_type) && <a className="text-primary hover:underline" href={`/api/candidates/${c.id}/document`} target="_blank" rel="noreferrer">{t("Preview the original document")}</a>}
            </EmptyState>
          )}
        </TabsContent>
        <TabsContent value="analyses"><CandidateAnalyses candidateId={c.id} kind="analysis" disabled={!ready} /></TabsContent>
        <TabsContent value="interview"><CandidateAnalyses candidateId={c.id} kind="interview" disabled={!ready} /></TabsContent>
        <TabsContent value="assistant">{tab === "assistant" && <CandidateChat candidateId={c.id} />}</TabsContent>
        <TabsContent value="data">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>{t("Data lifecycle")}</CardTitle></CardHeader>
              <CardContent>
                <ol className="relative space-y-3 border-l pl-5 text-sm">
                  {life.data?.map((e, i) => (
                    <li key={i} className="relative">
                      <span className="absolute -left-[25px] top-1.5 size-2.5 rounded-full bg-primary" />
                      <div className="font-medium">{EVENT_LABELS[e.type] ? t(EVENT_LABELS[e.type]) : e.type}</div>
                      <div className="text-xs text-muted-foreground">
                        {formatDate(e.ts)}
                        {"model" in e.details && ` · ${String(e.details.model)}`}
                        {"redactions" in e.details && ` · ${t("{n} item(s) removed for privacy", { n: String(e.details.redactions) })}`}
                      </div>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>{t("What is stored for this candidate")}</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
                  <dt className="text-muted-foreground">{t("Original document")}</dt><dd>data/uploads/{c.id.slice(0, 8)}…/</dd>
                  <dt className="text-muted-foreground">{t("Extracted text")}</dt><dd>{c.text_method ? t("local database (sensitive data removed)") : "—"}</dd>
                  <dt className="text-muted-foreground">{t("Profile & search index")}</dt><dd>{c.profile ? t("local database") : "—"}</dd>
                  <dt className="text-muted-foreground">{t("Removed for privacy")}</dt>
                  <dd>{c.redactions && Object.keys(c.redactions).length ? redactionText(c.redactions) : t("nothing detected")}</dd>
                  <dt className="text-muted-foreground">{t("Imported on")}</dt><dd>{formatDate(c.created_at)}</dd>
                  <dt className="text-muted-foreground">{t("Processed on")}</dt><dd>{formatDate(c.processed_at)}</dd>
                </dl>
                <Notice icon={AlertTriangle}>{t("Deleting the candidate removes all of the above and produces a verification report.")}</Notice>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </>
  );
}
