"use client";

import { useEffect, useRef } from "react";
import { ExternalLink } from "lucide-react";
import { Badge, Button, Card, CardContent, Skeleton } from "@/components/ui/primitives";
import { ErrorBanner } from "@/components/common";
import { useResource } from "@/lib/hooks";
import { N_, useI18n } from "@/lib/i18n";

interface TextData { text: string; sections: { name: string; start: number; end: number }[]; method: string; redactions: Record<string, number> }

const METHOD: Record<string, string> = {
  pdf_text: N_("PDF text"), ocr: N_("Local OCR (scanned document)"), docx: N_("Word document"), txt: N_("Text file"),
};

/** Redaction categories returned by the backend. */
export const REDACTION_LABELS: Record<string, string> = {
  birth_date: N_("birth date"), age: N_("age"), marital_status: N_("family status"), nationality: N_("nationality"),
  gender: N_("gender"), religion: N_("religion"), health: N_("health"), social_security: N_("social security number"),
  address: N_("address"), photo_reference: N_("photo reference"),
};

export function useRedactionText() {
  const { t } = useI18n();
  return (r: Record<string, number> | null | undefined) =>
    Object.entries(r || {}).map(([k, v]) => `${REDACTION_LABELS[k] ? t(REDACTION_LABELS[k]) : k} (${v})`).join(", ");
}

export function CvText({ candidateId, highlight, hasOriginal }: { candidateId: string; highlight: { start: number; end: number } | null; hasOriginal: boolean }) {
  const { t } = useI18n();
  const redactionText = useRedactionText();
  const { data, error } = useResource<TextData>(`/api/candidates/${candidateId}/text`);
  const markRef = useRef<HTMLElement>(null);

  useEffect(() => {
    markRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlight, data]);

  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Skeleton className="h-96" />;

  const t0 = data.text;
  const h = highlight && highlight.start < t0.length ? highlight : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="outline">{t("Source: {method}", { method: METHOD[data.method] ? t(METHOD[data.method]) : data.method })}</Badge>
        {Object.keys(data.redactions || {}).length > 0 && (
          <Badge variant="primary" title={t("Information not needed for recruitment, removed before storage and AI analysis")}>
            {t("Removed for privacy: {items}", { items: redactionText(data.redactions) })}
          </Badge>
        )}
        <div className="flex-1" />
        {hasOriginal && (
          <Button variant="outline" size="sm" asChild>
            <a href={`/api/candidates/${candidateId}/document`} target="_blank" rel="noreferrer"><ExternalLink /> {t("Open original")}</a>
          </Button>
        )}
      </div>
      {data.method === "ocr" && (
        <p className="text-xs text-muted-foreground">{t("This text was recognised from a scanned image; recognition errors are possible.")}</p>
      )}
      <Card>
        <CardContent className="max-h-[70vh] overflow-auto p-5">
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
            {h ? (
              <>
                {t0.slice(0, h.start)}
                <mark ref={markRef} className="rounded bg-warning/30 px-0.5 text-foreground">{t0.slice(h.start, h.end)}</mark>
                {t0.slice(h.end)}
              </>
            ) : t0}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}
