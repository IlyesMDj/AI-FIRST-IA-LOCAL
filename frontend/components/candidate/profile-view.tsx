"use client";

import { Award, BookOpen, Briefcase, FolderGit2, Languages, Sparkles } from "lucide-react";
import { Notice, VerificationMark } from "@/components/common";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import type { Profile, Skill, Verification } from "@/lib/api";
import { N_, useI18n } from "@/lib/i18n";

type Locate = (loc: { start: number; end: number; section: string }) => void;

const CATEGORY_LABELS: Record<string, string> = {
  technical: N_("Technical"), tool: N_("Tools"), methodology: N_("Methods"), domain: N_("Domain"), soft: N_("Interpersonal"), other: N_("Other"),
};

function Evidence({ text, v, onLocate }: { text: string | null; v?: Verification; onLocate?: Locate }) {
  const { t } = useI18n();
  if (!text) return null;
  return (
    <p className="mt-1 text-xs text-muted-foreground">
      <span className="italic">“{text}”</span>
      {v?.location && onLocate && (
        <button type="button" className="ml-2 text-primary hover:underline" onClick={() => onLocate(v.location!)}>{t("show in CV")}</button>
      )}
    </p>
  );
}

function Section({ icon: Icon, title, count, children }: { icon: React.ElementType; title: string; count?: number; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 pb-3">
        <Icon className="size-4 text-muted-foreground" />
        <CardTitle>{title}</CardTitle>
        {count !== undefined && <span className="text-xs text-muted-foreground">{count}</span>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Empty() {
  const { t } = useI18n();
  return <p className="text-sm text-muted-foreground">{t("Not mentioned in the CV.")}</p>;
}

function SkillChip({ s, onLocate }: { s: Skill; onLocate?: Locate }) {
  const { t } = useI18n();
  const title = [s.evidence ? `“${s.evidence}”` : null, s.basis === "inferred" ? t("Inferred by the AI (not stated explicitly)") : t("Stated in the CV")].filter(Boolean).join("\n");
  return (
    <button
      type="button"
      title={title}
      onClick={() => { if (s.verification?.location) onLocate?.(s.verification.location); }}
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${s.basis === "inferred" ? "border-dashed text-muted-foreground" : "bg-card"}`}
    >
      {s.name}
      <VerificationMark v={s.verification} />
    </button>
  );
}

export function ProfileView({ profile, onLocate }: { profile: Profile; onLocate?: Locate }) {
  const { t } = useI18n();
  const groups: Record<string, Skill[]> = {};
  profile.skills.forEach((s) => (groups[s.category] ||= []).push(s));
  const unverified = [...profile.skills, ...profile.experience, ...profile.education, ...profile.projects, ...profile.certifications, ...profile.languages]
    .filter((x) => x.verification?.status === "not_found").length;
  const present = (d: string | null) => (d === "present" ? t("present") : d || "?");

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {profile.professional_summary && (
          <Card>
            <CardHeader className="flex-row items-center gap-2 pb-3">
              <Sparkles className="size-4 text-muted-foreground" />
              <CardTitle>{t("Professional summary")}</CardTitle>
              <Badge variant="outline">{t("AI-generated")}</Badge>
            </CardHeader>
            <CardContent><p className="text-sm leading-relaxed">{profile.professional_summary}</p></CardContent>
          </Card>
        )}

        <Section icon={Briefcase} title={t("Professional experience")} count={profile.experience.length}>
          {profile.experience.length === 0 ? <Empty /> : (
            <ol className="relative space-y-5 border-l pl-5">
              {profile.experience.map((e, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[25px] top-1.5 size-2.5 rounded-full border-2 border-primary bg-card" />
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="font-medium">{e.position || t("Position not specified")}</span>
                    {e.company && <span className="text-muted-foreground">· {e.company}</span>}
                    <VerificationMark v={e.verification} />
                  </div>
                  <div className="text-xs text-muted-foreground">{present(e.start_date)} – {present(e.end_date)}</div>
                  {e.description && <p className="mt-1 text-sm">{e.description}</p>}
                  <Evidence text={e.evidence} v={e.verification} onLocate={onLocate} />
                </li>
              ))}
            </ol>
          )}
        </Section>

        <Section icon={FolderGit2} title={t("Projects")} count={profile.projects.length}>
          {profile.projects.length === 0 ? <Empty /> : (
            <ul className="space-y-3">
              {profile.projects.map((p, i) => (
                <li key={i}>
                  <div className="flex items-center gap-2 font-medium">{p.name} <VerificationMark v={p.verification} /></div>
                  {p.description && <p className="text-sm">{p.description}</p>}
                  {p.technologies.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">{p.technologies.map((x) => <Badge key={x}>{x}</Badge>)}</div>
                  )}
                  <Evidence text={p.evidence} v={p.verification} onLocate={onLocate} />
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <div className="space-y-4">
        <Section icon={Sparkles} title={t("Skills")} count={profile.skills.length}>
          {profile.skills.length === 0 ? <Empty /> : (
            <div className="space-y-3">
              {Object.entries(groups).map(([cat, list]) => (
                <div key={cat}>
                  <div className="mb-1.5 text-xs font-medium text-muted-foreground">{CATEGORY_LABELS[cat] ? t(CATEGORY_LABELS[cat]) : cat}</div>
                  <div className="flex flex-wrap gap-1.5">{list.map((s, i) => <SkillChip key={i} s={s} onLocate={onLocate} />)}</div>
                </div>
              ))}
              <p className="text-xs text-muted-foreground">{t("Dashed = inferred by the AI, not stated explicitly. Click a skill to see it in the CV.")}</p>
            </div>
          )}
        </Section>

        <Section icon={BookOpen} title={t("Education")} count={profile.education.length}>
          {profile.education.length === 0 ? <Empty /> : (
            <ul className="space-y-3 text-sm">
              {profile.education.map((e, i) => (
                <li key={i}>
                  <div className="flex items-center gap-1.5 font-medium">{e.degree || t("Degree not specified")} <VerificationMark v={e.verification} /></div>
                  <div className="text-muted-foreground">{[e.field, e.institution, e.graduation_year].filter(Boolean).join(" · ")}</div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section icon={Languages} title={t("Languages")} count={profile.languages.length}>
          {profile.languages.length === 0 ? <Empty /> : (
            <ul className="space-y-1 text-sm">
              {profile.languages.map((l, i) => (
                <li key={i} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5">{l.language} <VerificationMark v={l.verification} /></span>
                  <span className="text-muted-foreground">{l.level || t("level not stated")}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section icon={Award} title={t("Certifications")} count={profile.certifications.length}>
          {profile.certifications.length === 0 ? <Empty /> : (
            <ul className="space-y-1 text-sm">
              {profile.certifications.map((c, i) => (
                <li key={i} className="flex items-center gap-1.5">
                  {c.name} {c.year && <span className="text-muted-foreground">({c.year})</span>} <VerificationMark v={c.verification} />
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Notice>
          {t("Extracted by {model}. {pct}% of items were matched with the CV text.", {
            model: profile.extraction_metadata.model,
            pct: Math.round((profile.extraction_metadata.confidence || 0) * 100),
          })}{" "}
          {unverified > 0 && <strong>{t("{n} unverified item(s) are marked with ⚠.", { n: unverified })} </strong>}
          {t("Always check important facts against the original document.")}
        </Notice>
      </div>
    </div>
  );
}
