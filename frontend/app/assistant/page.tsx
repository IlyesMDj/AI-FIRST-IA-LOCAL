"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { MessagesSquare, Plus, Trash2 } from "lucide-react";
import { ChatPanel } from "@/components/chat-panel";
import { EmptyState, ErrorBanner, PageHeader } from "@/components/common";
import { Button, Card, CardContent, CardHeader, CardTitle, Select } from "@/components/ui/primitives";
import { api, type CandidateSummary, type Conversation, type Job } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";
import { candidateLabel, cn } from "@/lib/utils";

function NewConversation({ initial, onCreated }: { initial: string[]; onCreated: (c: Conversation) => void }) {
  const { t } = useI18n();
  const cands = useResource<CandidateSummary[]>("/api/candidates?status=completed");
  const jobs = useResource<Job[]>("/api/jobs");
  const [sel, setSel] = useState<string[]>(initial);
  const [job, setJob] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const create = async () => {
    setErr(null);
    try {
      onCreated(await api.post<Conversation>("/api/conversations", { candidate_ids: sel, job_id: job || null }));
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  return (
    <Card>
      <CardHeader><CardTitle>{t("New conversation")}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="mb-2 text-sm text-muted-foreground">{t("Candidates in scope (1 to 4). The assistant only sees these CVs.")}</div>
          <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto">
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
            {cands.data?.length === 0 && <p className="text-sm text-muted-foreground">{t("No processed candidate yet.")}</p>}
          </div>
        </div>
        <div className="max-w-sm">
          <Select value={job} onChange={(e) => setJob(e.target.value)} aria-label={t("Job description (optional)")}>
            <option value="">{t("No job description (optional)")}</option>
            {jobs.data?.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
          </Select>
        </div>
        {err && <ErrorBanner message={err} />}
        <Button onClick={create} disabled={!sel.length}><MessagesSquare /> {t("Start")}</Button>
      </CardContent>
    </Card>
  );
}

function AssistantInner() {
  const { t, timeAgo } = useI18n();
  const params = useSearchParams();
  const initial = (params.get("ids") || "").split(",").filter(Boolean);
  const convs = useResource<Conversation[]>("/api/conversations");
  const [active, setActive] = useState<Conversation | null>(null);
  const [creating, setCreating] = useState(initial.length > 0);

  useEffect(() => {
    if (!active && !creating && convs.data?.length) setActive(convs.data[0]);
  }, [convs.data, active, creating]);

  const remove = async (c: Conversation) => {
    await api.del(`/api/conversations/${c.id}`);
    if (active?.id === c.id) setActive(null);
    convs.reload();
  };

  return (
    <>
      <PageHeader title={t("Assistant")} description={t("Ask questions about one or several candidates. Answers cite the CV and never rank candidates.")}
        actions={<Button onClick={() => { setCreating(true); setActive(null); }}><Plus /> {t("New conversation")}</Button>} />
      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="space-y-1">
          {convs.data?.length === 0 && <p className="px-2 text-sm text-muted-foreground">{t("No conversation yet.")}</p>}
          {convs.data?.map((c) => (
            <div key={c.id} className={cn("group flex items-center gap-1 rounded-md", active?.id === c.id ? "bg-accent" : "hover:bg-secondary")}>
              <button className="min-w-0 flex-1 px-3 py-2 text-left" onClick={() => { setActive(c); setCreating(false); }}>
                <div className="truncate text-sm font-medium">{c.candidates.map((x) => x.label).join(", ")}</div>
                <div className="text-xs text-muted-foreground">{timeAgo(c.created_at)}</div>
              </button>
              <button className="p-2 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100 focus:opacity-100" aria-label={t("Delete conversation")} onClick={() => remove(c)}>
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
        <div>
          {creating && <NewConversation initial={initial} onCreated={(c) => { setCreating(false); setActive(c); convs.reload(); }} />}
          {!creating && active && <ChatPanel key={active.id} conversation={active} className="h-[calc(100vh-13rem)]" />}
          {!creating && !active && convs.data?.length === 0 && (
            <EmptyState icon={MessagesSquare} title={t("Start a conversation")} action={<Button onClick={() => setCreating(true)}><Plus /> {t("New conversation")}</Button>}>
              {t("Choose the candidates the assistant may consult. It answers from their CVs only.")}
            </EmptyState>
          )}
        </div>
      </div>
    </>
  );
}

export default function AssistantPage() {
  return <Suspense><AssistantInner /></Suspense>;
}
