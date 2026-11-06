"use client";

import { useState } from "react";
import { BarChart3, Loader2, Play } from "lucide-react";
import { EmptyState, ErrorBanner, Notice, PageHeader } from "@/components/common";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/primitives";
import { api, type SystemStatus } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { N_, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

interface Result {
  file: string;
  model: string;
  finished_at: string;
  error?: string;
  metrics?: Record<string, number | null>;
  cases: Record<string, unknown>[];
}

const METRICS: { key: string; label: string; fmt: "pct" | "s" | "mb" | "num"; better: "high" | "low" | null; help: string }[] = [
  { key: "extraction_recall", label: N_("Extraction accuracy"), fmt: "pct", better: "high", help: N_("Expected skills, employers and schools found") },
  { key: "french_recall", label: N_("French CVs accuracy"), fmt: "pct", better: "high", help: N_("Same, on French CVs only") },
  { key: "json_first_try_rate", label: N_("Valid JSON first try"), fmt: "pct", better: "high", help: N_("Schema compliance without repair") },
  { key: "matching_accuracy", label: N_("Job matching accuracy"), fmt: "pct", better: "high", help: N_("Criterion status equals the expected one") },
  { key: "summary_ok_rate", label: N_("Summaries OK"), fmt: "pct", better: "high", help: N_("Present, right language, ≤ 4 sentences") },
  { key: "hallucination_probe_rate", label: N_("Invented skills"), fmt: "pct", better: "low", help: N_("Absent skills that were extracted") },
  { key: "unverified_item_rate", label: N_("Unverifiable items"), fmt: "pct", better: "low", help: N_("Items whose evidence is not in the CV") },
  { key: "mean_extraction_s", label: N_("Extraction time"), fmt: "s", better: "low", help: N_("Mean per CV") },
  { key: "mean_criterion_s", label: N_("Time per criterion"), fmt: "s", better: "low", help: N_("Mean per requirement") },
  { key: "model_vram_mb", label: N_("GPU memory used by model"), fmt: "mb", better: null, help: N_("From Ollama") },
  { key: "gpu_offload_pct", label: N_("Share on GPU"), fmt: "num", better: "high", help: N_("% of the model in VRAM") },
  { key: "system_ram_available_mb", label: N_("Free RAM after load"), fmt: "mb", better: null, help: N_("System-wide") },
];

export default function BenchmarkPage() {
  const { t, formatDate, gb, num } = useI18n();
  const sys = useResource<SystemStatus>("/api/system/status");
  const status = useResource<{ running: boolean; progress: string; error: string | null }>("/api/benchmark/status", { pollMs: 3000, pollWhile: (d) => d.running });
  const results = useResource<Result[]>("/api/benchmark/results", { pollMs: 5000, pollWhile: () => !!status.data?.running });
  const [sel, setSel] = useState<string[]>(["qwen3:8b", "qwen2.5:7b"]);
  const [err, setErr] = useState<string | null>(null);

  const fmt = (v: number | null | undefined, f: string) => {
    if (v === null || v === undefined) return "—";
    if (f === "pct") return `${num(v * 100)} %`;
    if (f === "s") return `${num(v, 1)} s`;
    if (f === "mb") return gb(v);
    return `${num(v)} %`;
  };

  const models = sys.data?.installed_models.filter((m) => !m.capabilities.includes("embedding") && !m.capabilities.includes("vision")) || [];
  // latest result per model
  const latest = Object.values((results.data || []).reduce<Record<string, Result>>((acc, r) => (acc[r.model] ? acc : { ...acc, [r.model]: r }), {}));

  const run = async () => {
    setErr(null);
    try {
      await api.post("/api/benchmark/run", { models: sel });
      status.reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const best = (key: string, better: "high" | "low" | null) => {
    if (!better) return null;
    const vals = latest.map((r) => r.metrics?.[key]).filter((v): v is number => typeof v === "number");
    if (vals.length < 2) return null;
    return better === "high" ? Math.max(...vals) : Math.min(...vals);
  };

  return (
    <>
      <PageHeader title={t("Model benchmark")} description={t("Evaluate installed models on a fixed set of synthetic CVs. Results are stored locally in data/benchmarks.")} />
      <Card className="mb-4">
        <CardHeader>
          <CardTitle>{t("Run a benchmark")}</CardTitle>
          <CardDescription>{t("Models run one after the other (never simultaneously). Count about 2–4 minutes per model. Avoid using the app meanwhile.")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {models.map((m) => {
              const on = sel.includes(m.name);
              return (
                <button key={m.name} type="button" aria-pressed={on} onClick={() => setSel((s) => (on ? s.filter((x) => x !== m.name) : [...s, m.name]))}
                  className={cn("rounded-full border px-3 py-1 text-sm", on ? "border-primary bg-accent text-accent-foreground" : "hover:bg-secondary")}>
                  {m.name} <span className="text-xs text-muted-foreground">{m.parameter_size}</span>
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={run} disabled={!sel.length || status.data?.running}><Play /> {t("Run benchmark")}</Button>
            {status.data?.running && <span className="inline-flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> {status.data.progress}</span>}
          </div>
          {err && <ErrorBanner message={err} />}
          {status.data?.error && <ErrorBanner message={status.data.error} />}
        </CardContent>
      </Card>

      {latest.length === 0 ? (
        <EmptyState icon={BarChart3} title={t("No benchmark results yet")}>{t("Run a benchmark to compare models on this computer.")}</EmptyState>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-medium">{t("Metric")}</th>
                {latest.map((r) => <th key={r.model} className="px-4 py-2.5 font-medium">{r.model}<div className="font-normal">{formatDate(r.finished_at)}</div></th>)}
              </tr>
            </thead>
            <tbody className="divide-y">
              {METRICS.map((m) => {
                const b = best(m.key, m.better);
                return (
                  <tr key={m.key}>
                    <td className="px-4 py-2.5"><div className="font-medium">{t(m.label)}</div><div className="text-xs text-muted-foreground">{t(m.help)}</div></td>
                    {latest.map((r) => {
                      const v = r.metrics?.[m.key];
                      return <td key={r.model} className={cn("px-4 py-2.5 tabular", b !== null && v === b && "font-semibold text-success")}>{r.error ? <span className="text-destructive">{r.error}</span> : fmt(v, m.fmt)}</td>;
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
      <div className="mt-4"><Notice>{t("The dataset is small and synthetic: use these numbers to compare models on this machine, not as an absolute quality measure. See docs/model-benchmark.md.")}</Notice></div>
    </>
  );
}
