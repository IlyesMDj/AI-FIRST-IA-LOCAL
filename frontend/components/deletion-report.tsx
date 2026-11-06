"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import type { DeletionReport } from "@/lib/api";
import { N_, useI18n } from "@/lib/i18n";

const LABELS: Record<string, string> = {
  candidate: N_("Candidate record"),
  extracted_text: N_("Extracted text"),
  structured_profile: N_("Structured profile"),
  chunks_and_embeddings: N_("Search index entries"),
  embeddings: N_("Embeddings (vectors)"),
  analyses_and_interview_preps: N_("Analyses & interview preparations"),
  conversation_links: N_("Conversation links"),
  conversations: N_("Conversations"),
  chat_messages: N_("Chat messages"),
  lifecycle_events: N_("Activity log entries"),
};

export function DeletionReportView({ report }: { report: DeletionReport }) {
  const { t, formatDate } = useI18n();
  return (
    <div className="space-y-4 text-sm">
      <div className="text-xs text-muted-foreground">
        {t("Reference {ref}", { ref: report.candidate_ref })} · {formatDate(report.deleted_at)}
      </div>
      <div>
        <h4 className="mb-1.5 font-medium">{t("Removed")}</h4>
        <ul className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
          {Object.entries(report.removed.records).map(([k, v]) => (
            <li key={k} className="flex justify-between gap-2"><span className="text-muted-foreground">{LABELS[k] ? t(LABELS[k]) : k}</span><span className="tabular">{v}</span></li>
          ))}
          <li className="flex justify-between gap-2"><span className="text-muted-foreground">{t("File folders")}</span><span className="tabular">{report.removed.files.length}</span></li>
        </ul>
      </div>
      <div>
        <h4 className="mb-1.5 font-medium">{t("Verification after deletion")}</h4>
        <ul className="space-y-1">
          {report.verification.map((c) => (
            <li key={c.check} className="flex items-center gap-2">
              {c.passed ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-destructive" />}
              {c.check}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h4 className="mb-1.5 font-medium">{t("Limitations")}</h4>
        <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
          {report.limitations.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </div>
    </div>
  );
}
