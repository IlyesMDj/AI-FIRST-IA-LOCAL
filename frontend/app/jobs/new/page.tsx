"use client";

import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/common";
import { JobForm } from "@/components/job-form";
import { useI18n } from "@/lib/i18n";

export default function NewJobPage() {
  const { t } = useI18n();
  const router = useRouter();
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title={t("New job description")} description={t("Requirements are checked one by one against each CV — no score is computed.")} />
      <JobForm onSaved={(j) => router.push(`/jobs/${j.id}`)} />
    </div>
  );
}
