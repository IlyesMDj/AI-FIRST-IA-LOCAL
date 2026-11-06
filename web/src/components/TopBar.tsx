import { useEffect, useState } from "react";
import { Cpu, HardDrive, Moon, Sun } from "lucide-react";
import { api, MOCK, type Health, type ModelKey } from "@/api";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

function HealthIndicator({ model }: { model: ModelKey }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const h = await api.health();
        if (alive) {
          setHealth(h);
          setDown(false);
        }
      } catch {
        if (alive) setDown(true);
      }
    };
    tick();
    const t = setInterval(tick, 15_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  let tone: "ok" | "warn" | "bad" | "wait" = "wait";
  let label = "Vérification…";
  let detail = "Interrogation de /health";
  if (down) {
    tone = "bad";
    label = "Serveur local injoignable";
    detail = "Le back-end ne répond pas sur le port 8000.";
  } else if (health) {
    const wanted = health.model_keys?.[model];
    const missingWanted = wanted ? !health.models.includes(wanted) || health.missing.includes(model) : false;
    if (!health.ok) {
      tone = "bad";
      label = "Ollama indisponible";
      detail = "Ollama ne répond pas sur localhost:11434.";
    } else if (missingWanted) {
      tone = "warn";
      label = "Modèle manquant";
      detail = `Le modèle ${wanted} n'est pas installé dans Ollama.`;
    } else {
      tone = "ok";
      label = "Ollama prêt";
      detail = `Modèles installés : ${health.models.join(", ") || "aucun"}`;
    }
  }

  const dot = { ok: "bg-emerald-500", warn: "bg-amber-500", bad: "bg-red-500", wait: "bg-zinc-400" }[tone];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-default items-center gap-2 rounded-md border bg-card px-2.5 py-1 text-xs font-medium">
          <span className="relative flex size-2">
            {tone === "ok" && <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-50", dot)} />}
            <span className={cn("relative inline-flex size-2 rounded-full", dot)} />
          </span>
          {label}
        </span>
      </TooltipTrigger>
      <TooltipContent>{detail}</TooltipContent>
    </Tooltip>
  );
}

function ModelSelector({ value, onChange }: { value: ModelKey; onChange: (m: ModelKey) => void }) {
  const opts: { key: ModelKey; label: string }[] = [
    { key: "rapide", label: "Rapide (3b)" },
    { key: "precis", label: "Précis (8b)" },
  ];
  return (
    <div role="radiogroup" aria-label="Modèle d'IA local" className="bg-muted inline-flex items-center rounded-md p-0.5">
      <Cpu className="text-muted-foreground mx-1.5 size-3.5" aria-hidden />
      {opts.map((o) => (
        <button
          key={o.key}
          role="radio"
          aria-checked={value === o.key}
          onClick={() => onChange(o.key)}
          className={cn(
            "cursor-pointer rounded px-2.5 py-1 text-xs font-medium transition-colors",
            value === o.key ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function TopBar({
  model,
  onModelChange,
  dark,
  onToggleDark,
}: {
  model: ModelKey;
  onModelChange: (m: ModelKey) => void;
  dark: boolean;
  onToggleDark: () => void;
}) {
  return (
    <div className="border-b bg-primary/[0.06] dark:bg-primary/[0.08]">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-2 md:flex-row md:items-center md:justify-between sm:px-6">
        <p className="flex items-start gap-2 text-sm">
          <HardDrive className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            <strong className="font-semibold">Traitement 100 % local</strong>
            <span className="text-muted-foreground"> · </span>
            Aide à la lecture — l'outil ne classe pas et ne recommande pas : <strong className="font-semibold">vous décidez.</strong>
          </span>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {MOCK && (
            <span className="rounded-md border border-dashed border-amber-500/60 px-2 py-1 text-xs font-medium text-amber-700 dark:text-amber-400">
              Mode démo (données fictives)
            </span>
          )}
          <HealthIndicator model={model} />
          <ModelSelector value={model} onChange={onModelChange} />
          <button
            onClick={onToggleDark}
            className="hover:bg-accent text-muted-foreground inline-flex size-7 cursor-pointer items-center justify-center rounded-md"
            aria-label={dark ? "Passer en thème clair" : "Passer en thème sombre"}
            title={dark ? "Thème clair" : "Thème sombre"}
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}
