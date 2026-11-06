"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Bot, FileText, Loader2, Send, User } from "lucide-react";
import { ErrorBanner } from "@/components/common";
import { Button, Textarea } from "@/components/ui/primitives";
import { api, langHeaders, type ChatMessage, type Citation, type Conversation } from "@/lib/api";
import { N_, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const SUGGESTIONS_ONE = [
  N_("What are this candidate's main technical skills?"),
  N_("Summarize their professional experience."),
  N_("Which projects show experience with databases?"),
  N_("What information should I clarify during the interview?"),
];
const SUGGESTIONS_MANY = [
  N_("Compare the evidence in these profiles against the job requirements."),
  N_("What experience does each candidate have with databases?"),
  N_("Which information is missing or unclear in each CV?"),
];

function RefText({ text, cites }: { text: string; cites: Citation[] }) {
  const { t } = useI18n();
  const parts = text.split(/(\[C\d+-(?:\d+|P)\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[(C\d+-(?:\d+|P))\]$/);
        if (!m) return <span key={i}>{p}</span>;
        const c = cites.find((x) => x.ref === m[1]);
        return (
          <sup key={i} title={c ? `${c.candidate_label} · ${t(c.section)}${c.text ? `\n“${c.text.slice(0, 200)}…”` : ""}` : m[1]}
            className="mx-0.5 cursor-help rounded bg-accent px-1 text-[10px] font-semibold text-accent-foreground">
            {m[1]}
          </sup>
        );
      })}
    </>
  );
}

function Sources({ cites }: { cites: Citation[] }) {
  const { t } = useI18n();
  if (!cites.length) return null;
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer text-muted-foreground hover:text-foreground">{t("{n} source(s) cited", { n: cites.length })}</summary>
      <ul className="mt-2 space-y-2">
        {cites.map((c) => (
          <li key={c.ref} className="rounded-md border bg-card p-2">
            <div className="flex items-center gap-1.5 font-medium">
              <FileText className="size-3" /> [{c.ref}] {c.candidate_label} · {t(c.section)}
              <Link href={`/candidates/${c.candidate_id}`} className="ml-auto text-primary hover:underline">{t("profile")}</Link>
            </div>
            {c.text && <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{c.text}</p>}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function ChatPanel({ conversation, className }: { conversation: Conversation; className?: string }) {
  const { t } = useI18n();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<Conversation>(`/api/conversations/${conversation.id}`).then((c) => setMessages(c.messages || [])).catch((e) => setError(e.message));
  }, [conversation.id]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q, citations: [] }, { role: "assistant", content: "", citations: [] }]);
    try {
      const res = await fetch(`/api/conversations/${conversation.id}/messages`, {
        method: "POST", headers: langHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ message: q }),
      });
      if (!res.ok || !res.body) throw new Error((await res.json().catch(() => ({}))).detail || t("The assistant is unavailable."));
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      let sources: Citation[] = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const ev = JSON.parse(line);
          if (ev.type === "sources") sources = ev.sources;
          if (ev.type === "token")
            setMessages((m) => { const c = [...m]; const last = c[c.length - 1]; c[c.length - 1] = { ...last, content: last.content + ev.text, citations: sources }; return c; });
          if (ev.type === "done")
            setMessages((m) => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], citations: ev.citations.length ? ev.citations : [] }; return c; });
          if (ev.type === "error") throw new Error(ev.message);
        }
      }
    } catch (e) {
      setError((e as Error).message);
      setMessages((m) => (m[m.length - 1]?.content ? m : m.slice(0, -1)));
    } finally {
      setBusy(false);
    }
  };

  const suggestions = conversation.candidates.length > 1 ? SUGGESTIONS_MANY : SUGGESTIONS_ONE;

  return (
    <div className={cn("flex min-h-[480px] flex-col rounded-lg border bg-card", className)}>
      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        {messages.length === 0 && (
          <div className="py-6 text-center">
            <Bot className="mx-auto mb-2 size-6 text-muted-foreground" />
            <p className="font-medium">{t("Ask a question about {names}", { names: conversation.candidates.map((c) => c.label).join(", ") })}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t("Answers are based only on the CV content and cite their sources.")}</p>
            <div className="mx-auto mt-4 flex max-w-xl flex-wrap justify-center gap-2">
              {suggestions.map((s) => (
                <button key={s} onClick={() => send(t(s))} className="rounded-full border px-3 py-1 text-xs hover:bg-secondary">{t(s)}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className="flex gap-3">
            <div className={cn("flex size-7 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-secondary" : "bg-accent text-accent-foreground")}>
              {m.role === "user" ? <User className="size-3.5" /> : <Bot className="size-3.5" />}
            </div>
            <div className="min-w-0 flex-1 pt-0.5 text-sm leading-relaxed">
              {m.role === "assistant" && !m.content && busy ? (
                <span className="inline-flex items-center gap-2 text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> {t("Reading the CV…")}</span>
              ) : (
                <div className="whitespace-pre-wrap">{m.role === "assistant" ? <RefText text={m.content} cites={m.citations} /> : m.content}</div>
              )}
              {m.role === "assistant" && <Sources cites={m.citations} />}
            </div>
          </div>
        ))}
        <div ref={bottom} />
      </div>
      {error && <div className="px-5 pb-2"><ErrorBanner message={error} /></div>}
      <form className="flex items-end gap-2 border-t p-3" onSubmit={(e) => { e.preventDefault(); send(input); }}>
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
          placeholder={t("Ask about skills, experience, projects… (Enter to send)")}
          className="min-h-[44px] resize-none"
          rows={1}
          maxLength={2000}
          aria-label={t("Your question")}
        />
        <Button type="submit" size="icon" disabled={busy || !input.trim()} aria-label={t("Send")}><Send /></Button>
      </form>
      <p className="px-4 pb-3 text-[11px] text-muted-foreground">{t("The assistant can make mistakes. It never ranks candidates or makes hiring decisions.")}</p>
    </div>
  );
}
