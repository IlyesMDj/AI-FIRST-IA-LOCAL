"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AlertTriangle, Columns3, FileText, MessagesSquare, ScanText, Search, Upload, Users } from "lucide-react";
import { CandidateStatusBadge, EmptyState, ErrorBanner, PageHeader } from "@/components/common";
import { Button, Card, Input, Select, Skeleton } from "@/components/ui/primitives";
import type { CandidateSummary } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { candidateLabel, initials } from "@/lib/utils";

export default function CandidatesPage() {
  const { t, formatDate } = useI18n();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (status) params.set("status", status);
  const { data, error, loading } = useResource<CandidateSummary[]>(`/api/candidates?${params}`, {
    pollMs: 3000,
    pollWhile: (d) => d.some((c) => ["pending", "processing"].includes(c.status)),
  });

  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 4 ? s : [...s, id]));

  return (
    <>
      <PageHeader
        title={t("Candidates")}
        description={t("Imported applications and their processing status.")}
        actions={<Button asChild><Link href="/candidates/import"><Upload /> {t("Import CVs")}</Link></Button>}
      />

      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground" />
          <Input className="pl-9" placeholder={t("Search by name, e-mail or file name")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("Search candidates")} />
        </div>
        <Select className="sm:w-56" value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("Filter by status")}>
          <option value="">{t("All statuses")}</option>
          <option value="completed">{t("Completed")}</option>
          <option value="pending">{t("Waiting for extraction")}</option>
          <option value="processing">{t("Processing")}</option>
          <option value="imported">{t("Imported")}</option>
          <option value="failed">{t("Failed")}</option>
        </Select>
      </div>

      {selected.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border bg-accent/50 px-3 py-2 text-sm">
          <span className="font-medium">{t("{n} selected", { n: selected.length })}</span>
          <span className="text-muted-foreground">{t("(max 4)")}</span>
          <div className="flex-1" />
          <Button size="sm" variant="outline" disabled={selected.length < 2} onClick={() => router.push(`/compare?ids=${selected.join(",")}`)}>
            <Columns3 /> {t("Compare")}
          </Button>
          <Button size="sm" variant="outline" onClick={() => router.push(`/assistant?ids=${selected.join(",")}`)}>
            <MessagesSquare /> {t("Ask the assistant")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>{t("Clear")}</Button>
        </div>
      )}

      {error && <ErrorBanner message={error} />}
      {loading && !data && <Skeleton className="h-64" />}
      {data && data.length === 0 && (
        <EmptyState icon={Users} title={q || status ? t("No candidate matches these filters") : t("No candidates yet")}
          action={!q && !status && <Button asChild><Link href="/candidates/import"><Upload /> {t("Import CVs")}</Link></Button>}>
          {!q && !status && t("Import PDF, Word or text CVs. Each document is processed locally on this computer.")}
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="w-10 px-4 py-2.5"><span className="sr-only">{t("Select")}</span></th>
                  <th className="px-2 py-2.5 font-medium">{t("Candidate")}</th>
                  <th className="px-4 py-2.5 font-medium">{t("Status")}</th>
                  <th className="hidden px-4 py-2.5 font-medium md:table-cell">{t("Document")}</th>
                  <th className="hidden px-4 py-2.5 font-medium lg:table-cell">{t("Imported on")}</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {data.map((c) => (
                  <tr key={c.id} className="hover:bg-muted/40">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        className="size-4 accent-[hsl(var(--primary))]"
                        checked={selected.includes(c.id)}
                        disabled={c.status !== "completed"}
                        onChange={() => toggle(c.id)}
                        aria-label={t("Select {name}", { name: candidateLabel(c) })}
                      />
                    </td>
                    <td className="px-2 py-3">
                      <Link href={`/candidates/${c.id}`} className="flex items-center gap-3">
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
                          {initials(candidateLabel(c))}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate font-medium hover:underline">{candidateLabel(c)}</span>
                          <span className="block truncate text-xs text-muted-foreground">{c.email || "—"}</span>
                        </span>
                        {c.has_warnings && <AlertTriangle className="size-4 shrink-0 text-warning" aria-label={t("Has warnings")} />}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <CandidateStatusBadge status={c.status} />
                      {c.status === "processing" && c.processing_step && <div className="mt-1 text-xs text-muted-foreground">{c.processing_step}…</div>}
                      {c.status === "failed" && c.error_message && <div className="mt-1 max-w-xs truncate text-xs text-destructive" title={c.error_message}>{c.error_message}</div>}
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">
                      <span className="inline-flex items-center gap-1.5">
                        {c.ocr_used ? <ScanText className="size-4" /> : <FileText className="size-4" />}
                        <span className="max-w-[180px] truncate">{c.original_filename}</span>
                      </span>
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground lg:table-cell">{formatDate(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
}
