"use client";

import { useState } from "react";
import { CheckCircle2, FileCheck2, Lock, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import { EmptyState, Notice, PageHeader } from "@/components/common";
import { DeletionReportView } from "@/components/deletion-report";
import { useRedactionText } from "@/components/candidate/cv-text";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton } from "@/components/ui/primitives";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type DeletionReport } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { N_, useI18n } from "@/lib/i18n";

interface Inventory {
  stores: { name: string; location: string; items: number | null; bytes: number }[];
  records: Record<string, number>;
  redactions_applied: Record<string, number>;
  network: { inference_endpoint: string; allowed_inference_hosts: string[]; telemetry: string; external_calls: string };
}

const RECORD_LABELS: Record<string, string> = {
  candidates: N_("candidates"), extracted_texts: N_("extracted texts"), structured_profiles: N_("structured profiles"),
  text_chunks: N_("text chunks"), embeddings: N_("embeddings"), analyses: N_("analyses"),
  interview_preparations: N_("interview preparations"), conversations: N_("conversations"), chat_messages: N_("chat messages"),
  lifecycle_events: N_("lifecycle events"), deletion_reports: N_("deletion reports"),
};

const STEPS = [
  { t: N_("Reception"), d: N_("File chosen by the recruiter in the browser"), s: N_("browser memory") },
  { t: N_("Import"), d: N_("Type, size & hash checked; duplicate detection"), s: "data/uploads/<id>/" },
  { t: N_("Text extraction"), d: N_("PDF / Word / text, or local OCR for scans"), s: N_("memory only") },
  { t: N_("Minimisation"), d: N_("Birth date, age, family, nationality, address… removed"), s: N_("SQLite (redacted text)") },
  { t: N_("AI analysis"), d: N_("Local model via Ollama on 127.0.0.1"), s: N_("GPU / RAM (transient)") },
  { t: N_("Structured storage"), d: N_("Validated profile with evidence"), s: "SQLite" },
  { t: N_("Embeddings"), d: N_("Search vectors (nomic-embed-text)"), s: N_("SQLite (same rows)") },
  { t: N_("Search & consultation"), d: N_("Candidate-isolated retrieval, chat, analyses"), s: "SQLite" },
  { t: N_("Deletion"), d: N_("Transaction + file removal + verification report"), s: N_("report without personal data") },
];

function DataFlow() {
  const { t } = useI18n();
  const w = 150, h = 74, gap = 22, cols = 3;
  return (
    <svg viewBox={`0 0 ${cols * (w + gap) - gap + 20} ${3 * (h + 40) + 10}`} className="w-full max-w-3xl" role="img" aria-label={t("Data flow of a CV through the application")}>
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" className="fill-muted-foreground" />
        </marker>
      </defs>
      {STEPS.map((s, i) => {
        const row = Math.floor(i / cols);
        const colRaw = i % cols;
        const col = row % 2 === 0 ? colRaw : cols - 1 - colRaw; // snake layout
        const x = 10 + col * (w + gap);
        const y = 10 + row * (h + 40);
        const last = i === STEPS.length - 1;
        let arrow = null;
        if (!last) {
          const nRow = Math.floor((i + 1) / cols);
          if (nRow === row) {
            const dir = row % 2 === 0 ? 1 : -1;
            const x1 = dir === 1 ? x + w : x;
            arrow = <line x1={x1} y1={y + h / 2} x2={x1 + dir * (gap - 2)} y2={y + h / 2} className="stroke-muted-foreground" strokeWidth={1.2} markerEnd="url(#arr)" />;
          } else {
            arrow = <line x1={x + w / 2} y1={y + h} x2={x + w / 2} y2={y + h + 38} className="stroke-muted-foreground" strokeWidth={1.2} markerEnd="url(#arr)" />;
          }
        }
        return (
          <g key={s.t}>
            <rect x={x} y={y} width={w} height={h} rx={8} className={i === 4 ? "fill-accent stroke-primary" : i === 8 ? "fill-destructive/10 stroke-destructive/60" : "fill-card stroke-border"} strokeWidth={1.2} />
            <text x={x + 10} y={y + 20} className="fill-foreground text-[11px] font-semibold">{i + 1}. {t(s.t)}</text>
            <foreignObject x={x + 8} y={y + 26} width={w - 16} height={h - 28}>
              <div className="text-[9.5px] leading-tight text-muted-foreground">{t(s.d)}<div className="mt-0.5 font-mono text-[9px] text-primary">{t(s.s)}</div></div>
            </foreignObject>
            {arrow}
          </g>
        );
      })}
    </svg>
  );
}

function Reports() {
  const { t, formatDate } = useI18n();
  const list = useResource<{ id: string; candidate_ref: string; deleted_at: string; success: boolean }[]>("/api/deletion-reports");
  const [open, setOpen] = useState<DeletionReport | null>(null);
  if (!list.data) return <Skeleton className="h-32" />;
  if (!list.data.length) return <EmptyState icon={FileCheck2} title={t("No deletion yet")}>{t("Each candidate deletion produces a verification report listed here. Reports contain no personal data.")}</EmptyState>;
  return (
    <>
      <ul className="divide-y rounded-lg border bg-card">
        {list.data.map((r) => (
          <li key={r.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
            {r.success ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-destructive" />}
            <span className="font-mono text-xs">{r.candidate_ref}</span>
            <span className="flex-1 text-muted-foreground">{formatDate(r.deleted_at)}</span>
            <Button size="sm" variant="ghost" onClick={async () => setOpen((await api.get<{ report: DeletionReport }>(`/api/deletion-reports/${r.id}`)).report)}>{t("View report")}</Button>
          </li>
        ))}
      </ul>
      <Dialog open={!!open} onOpenChange={(o) => { if (!o) setOpen(null); }}>
        <DialogContent className="max-w-xl">
          <DialogHeader><DialogTitle>{t("Deletion report")}</DialogTitle></DialogHeader>
          {open && <DeletionReportView report={open} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function PrivacyPage() {
  const { t, formatBytes } = useI18n();
  const redactionText = useRedactionText();
  const inv = useResource<Inventory>("/api/privacy/inventory");
  const d = inv.data;
  return (
    <>
      <PageHeader title={t("Privacy & data")} description={t("Where candidate data lives, how it flows, and how it is deleted.")} />
      <div className="mb-5 grid gap-3 md:grid-cols-3">
        <Notice icon={Lock}><strong>{t("Local only.")}</strong> {t("CVs, extracted data, embeddings and AI prompts stay on this computer. AI inference only on {endpoint}.", { endpoint: d?.network.inference_endpoint || "localhost" })}</Notice>
        <Notice icon={ShieldCheck}><strong>{t("No telemetry.")}</strong> {t("No analytics, no tracking, no cloud sync. The interface and server listen on 127.0.0.1 only.")}</Notice>
        <Notice icon={TriangleAlert} tone="warning"><strong>{t("Not a compliance certificate.")}</strong> {t("Local processing alone does not make a processing GDPR-compliant: purposes, legal basis and retention must be validated by your organisation and DPO.")}</Notice>
      </div>

      <Tabs defaultValue="inventory">
        <TabsList>
          <TabsTrigger value="inventory">{t("Stored data")}</TabsTrigger>
          <TabsTrigger value="flow">{t("Data flow")}</TabsTrigger>
          <TabsTrigger value="deletions">{t("Deletion reports")}</TabsTrigger>
          <TabsTrigger value="register">{t("Processing register")}</TabsTrigger>
        </TabsList>

        <TabsContent value="inventory">
          {!d ? <Skeleton className="h-48" /> : (
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader><CardTitle>{t("Storage locations")}</CardTitle><CardDescription>{t("All under the application's local data folder.")}</CardDescription></CardHeader>
                <CardContent>
                  <ul className="divide-y text-sm">
                    {d.stores.map((s) => (
                      <li key={s.name} className="flex justify-between gap-3 py-2">
                        <div><div className="font-medium">{s.name}</div><div className="font-mono text-xs text-muted-foreground">{s.location}</div></div>
                        <div className="text-right text-muted-foreground">{s.items !== null && <div>{t("{n} file(s)", { n: s.items })}</div>}<div>{formatBytes(s.bytes)}</div></div>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>{t("Records")}</CardTitle></CardHeader>
                <CardContent>
                  <ul className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
                    {Object.entries(d.records).map(([k, v]) => (
                      <li key={k} className="flex justify-between"><span className="text-muted-foreground">{RECORD_LABELS[k] ? t(RECORD_LABELS[k]) : k}</span><span className="tabular">{v}</span></li>
                    ))}
                  </ul>
                  <div className="mt-4 text-sm font-medium">{t("Removed before storage (data minimisation)")}</div>
                  <p className="text-sm text-muted-foreground">
                    {Object.keys(d.redactions_applied).length ? redactionText(d.redactions_applied) : t("Nothing detected yet.")}
                  </p>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="flow">
          <Card>
            <CardHeader><CardTitle>{t("Journey of a CV")}</CardTitle><CardDescription>{t("Every step runs on this computer. Full details: docs/data-lifecycle.md.")}</CardDescription></CardHeader>
            <CardContent><DataFlow /></CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="deletions"><Reports /></TabsContent>

        <TabsContent value="register">
          <Card>
            <CardHeader><CardTitle>{t("Simplified processing register (summary)")}</CardTitle><CardDescription>{t("Template — items marked “to validate” must be decided by your organisation and DPO. Full version: docs/data/registre-simplifie.md.")}</CardDescription></CardHeader>
            <CardContent>
              <dl className="grid gap-x-6 gap-y-3 text-sm md:grid-cols-[200px_1fr]">
                <dt className="font-medium">{t("Purpose")}</dt><dd>{t("Assist recruiters in reading and understanding applications for a given position. No automated decision.")}</dd>
                <dt className="font-medium">{t("Data subjects")}</dt><dd>{t("Job applicants.")}</dd>
                <dt className="font-medium">{t("Data categories")}</dt><dd>{t("Identification (name, e-mail, phone), professional experience, education, skills, languages, certifications, projects.")}</dd>
                <dt className="font-medium">{t("Minimisation")}</dt><dd>{t("Birth date, age, family status, nationality, gender, religion, health and home address are removed before storage and AI analysis.")}</dd>
                <dt className="font-medium">{t("Legal basis")}</dt><dd className="text-warning">{t("To validate by the organisation / DPO (not decided by the software).")}</dd>
                <dt className="font-medium">{t("Recipients")}</dt><dd>{t("Authorised recruiters using this computer. No transfer to third parties or outside the device.")}</dd>
                <dt className="font-medium">{t("Retention")}</dt><dd className="text-warning">{t("To define by the organisation (e.g. per applicable guidance). Deletion is manual, per candidate, with a report.")}</dd>
                <dt className="font-medium">{t("Security")}</dt><dd>{t("Local-only processing, loopback binding, input validation, prompt-injection protections, secure delete in database. Disk encryption (e.g. BitLocker) recommended.")}</dd>
                <dt className="font-medium">{t("Limitations")}</dt><dd>{t("No user authentication in this version; SSD remanence; copies outside the app not managed. See docs/known-limitations.md.")}</dd>
              </dl>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </>
  );
}
