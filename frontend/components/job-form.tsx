"use client";

import { useState } from "react";
import { Save } from "lucide-react";
import { ErrorBanner } from "@/components/common";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Textarea } from "@/components/ui/primitives";
import { api, type Job } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type JobInput = Omit<Job, "id" | "created_at" | "updated_at">;

const EMPTY: JobInput = {
  title: "", description: "", required_skills: [], optional_skills: [], experience_requirements: "",
  education_requirements: "", languages: [], responsibilities: [], criteria: [],
};

const toLines = (a: string[]) => a.join("\n");
const fromLines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);

function ListField({ id, label, hint, value, onChange, rows = 4 }: { id: string; label: string; hint: string; value: string; onChange: (v: string) => void; rows?: number }) {
  const { t } = useI18n();
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Textarea id={id} rows={rows} value={value} onChange={(e) => onChange(e.target.value)} placeholder={t("One item per line")} />
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

export function JobForm({ initial, onSaved }: { initial?: Job; onSaved: (j: Job) => void }) {
  const { t } = useI18n();
  const base = initial || EMPTY;
  const [f, setF] = useState({
    title: base.title, description: base.description,
    required_skills: toLines(base.required_skills), optional_skills: toLines(base.optional_skills),
    experience_requirements: base.experience_requirements, education_requirements: base.education_requirements,
    languages: toLines(base.languages), responsibilities: toLines(base.responsibilities), criteria: toLines(base.criteria),
  });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const body: JobInput = {
      title: f.title, description: f.description, experience_requirements: f.experience_requirements,
      education_requirements: f.education_requirements, required_skills: fromLines(f.required_skills),
      optional_skills: fromLines(f.optional_skills), languages: fromLines(f.languages),
      responsibilities: fromLines(f.responsibilities), criteria: fromLines(f.criteria),
    };
    try {
      const j = initial ? await api.put<Job>(`/api/jobs/${initial.id}`, body) : await api.post<Job>("/api/jobs", body);
      onSaved(j);
    } catch (e2) {
      setErr((e2 as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={save} className="space-y-4">
      <Card>
        <CardHeader><CardTitle>{t("Position")}</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="title">{t("Job title")} *</Label>
            <Input id="title" required minLength={2} maxLength={200} value={f.title} onChange={(e) => set("title")(e.target.value)} placeholder={t("e.g. Backend Python Developer")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="desc">{t("Description")}</Label>
            <Textarea id="desc" rows={4} value={f.description} onChange={(e) => set("description")(e.target.value)} placeholder={t("Context, team, missions…")} />
          </div>
          <ListField id="resp" label={t("Responsibilities")} hint={t("Used as context for the analysis.")} value={f.responsibilities} onChange={set("responsibilities")} rows={3} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("Recruitment criteria")}</CardTitle>
          <CardDescription>{t("Each line becomes a criterion checked against the CV. Keep criteria job-related and objective.")}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <ListField id="req" label={t("Required skills")} hint={t("e.g. Python, PostgreSQL")} value={f.required_skills} onChange={set("required_skills")} />
          <ListField id="opt" label={t("Optional skills")} hint={t("Nice to have.")} value={f.optional_skills} onChange={set("optional_skills")} />
          <div className="space-y-1.5">
            <Label htmlFor="exp">{t("Experience requirements")}</Label>
            <Textarea id="exp" rows={2} value={f.experience_requirements} onChange={(e) => set("experience_requirements")(e.target.value)} placeholder={t("e.g. 3+ years building REST APIs")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edu">{t("Education requirements")}</Label>
            <Textarea id="edu" rows={2} value={f.education_requirements} onChange={(e) => set("education_requirements")(e.target.value)} placeholder={t("Only if genuinely required for the job")} />
          </div>
          <ListField id="lang" label={t("Languages")} hint={t("Only if relevant to the job.")} value={f.languages} onChange={set("languages")} rows={2} />
          <ListField id="crit" label={t("Other criteria")} hint={t("Other objective, job-related criteria.")} value={f.criteria} onChange={set("criteria")} rows={2} />
        </CardContent>
      </Card>
      {err && <ErrorBanner message={err} />}
      <div className="flex justify-end"><Button type="submit" disabled={busy}><Save /> {busy ? t("Saving…") : t("Save job description")}</Button></div>
    </form>
  );
}
