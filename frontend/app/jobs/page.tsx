"use client";

import Link from "next/link";
import { Briefcase, Plus } from "lucide-react";
import { EmptyState, ErrorBanner, PageHeader } from "@/components/common";
import { Badge, Button, Card, CardContent, Skeleton } from "@/components/ui/primitives";
import type { Job } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { useI18n } from "@/lib/i18n";

export default function JobsPage() {
  const { t, formatDate } = useI18n();
  const { data, error } = useResource<Job[]>("/api/jobs");
  return (
    <>
      <PageHeader
        title={t("Job descriptions")}
        description={t("Define the requirements candidates are analysed against.")}
        actions={<Button asChild><Link href="/jobs/new"><Plus /> {t("New job description")}</Link></Button>}
      />
      {error && <ErrorBanner message={error} />}
      {!data && !error && <Skeleton className="h-48" />}
      {data?.length === 0 && (
        <EmptyState icon={Briefcase} title={t("No job description yet")} action={<Button asChild><Link href="/jobs/new"><Plus /> {t("Create one")}</Link></Button>}>
          {t("A job description lists the required skills, experience and other criteria used for evidence-based analysis.")}
        </EmptyState>
      )}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data?.map((j) => (
          <Link key={j.id} href={`/jobs/${j.id}`}>
            <Card className="h-full transition-colors hover:border-primary/40">
              <CardContent className="space-y-3 p-5">
                <div>
                  <div className="font-medium">{j.title}</div>
                  <div className="text-xs text-muted-foreground">{t("Updated {date}", { date: formatDate(j.updated_at, false) })}</div>
                </div>
                {j.description && <p className="line-clamp-2 text-sm text-muted-foreground">{j.description}</p>}
                <div className="flex flex-wrap gap-1">
                  {j.required_skills.slice(0, 6).map((s) => <Badge key={s} variant="primary">{s}</Badge>)}
                  {j.optional_skills.slice(0, 3).map((s) => <Badge key={s} variant="outline">{s}</Badge>)}
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}
