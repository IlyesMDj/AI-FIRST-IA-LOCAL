import { useEffect, useState, type ReactNode } from "react";
import { BriefcaseBusiness, Columns3, ShieldCheck, Users } from "lucide-react";
import type { ModelKey } from "@/api";
import { TopBar } from "@/components/TopBar";
import { navigate, useHashRoute } from "@/components/common";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { JobView } from "@/views/JobView";
import { CandidatesView } from "@/views/CandidatesView";
import { CandidateView } from "@/views/CandidateView";
import { CompareView } from "@/views/CompareView";
import { ErasuresView } from "@/views/ErasuresView";

const NAV = [
  { path: "/poste", label: "Poste", icon: BriefcaseBusiness },
  { path: "/candidats", label: "Candidats", icon: Users },
  { path: "/comparer", label: "Comparer", icon: Columns3 },
  { path: "/effacements", label: "Journal des effacements", icon: ShieldCheck },
];

export default function App() {
  const route = useHashRoute();
  // Préférences d'UI non sensibles : gardées en mémoire uniquement (aucun stockage navigateur).
  const [model, setModel] = useState<ModelKey>("rapide");
  const [dark, setDark] = useState(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const candidateMatch = route.match(/^\/candidats\/([^/]+)$/);
  const section = "/" + (route.split("/")[1] ?? "");

  let view: ReactNode;
  if (candidateMatch) view = <CandidateView key={candidateMatch[1]} id={decodeURIComponent(candidateMatch[1])} model={model} />;
  else if (section === "/poste") view = <JobView model={model} />;
  else if (section === "/comparer") view = <CompareView />;
  else if (section === "/effacements") view = <ErasuresView />;
  else view = <CandidatesView model={model} />;

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex min-h-screen flex-col">
        <TopBar model={model} onModelChange={setModel} dark={dark} onToggleDark={() => setDark((d) => !d)} />
        <header className="bg-card/80 sticky top-0 z-30 border-b backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 sm:px-6">
            <button onClick={() => navigate("/candidats")} className="flex cursor-pointer items-center gap-2 py-3">
              <span className="logo-badge grid size-8 place-items-center rounded-lg text-xs font-bold text-white shadow-sm">RC</span>
              <span className="hidden font-semibold tracking-tight sm:inline">Recruiter Copilot</span>
            </button>
            <nav className="flex gap-1 overflow-x-auto" aria-label="Navigation principale">
              {NAV.map((n) => {
                const active = section === n.path;
                const Icon = n.icon;
                return (
                  <a
                    key={n.path}
                    href={`#${n.path}`}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "my-2 inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium whitespace-nowrap transition-all duration-200",
                      active
                        ? "bg-primary text-primary-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground hover:bg-accent",
                    )}
                  >
                    <Icon className="size-4" aria-hidden />
                    {n.label}
                  </a>
                );
              })}
            </nav>
          </div>
        </header>
        <main key={route} className="view-anim mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">{view}</main>
        <footer className="text-muted-foreground border-t py-4 text-center text-xs">
          Recruiter Copilot · Atelier Nova · aucune donnée ne quitte cet ordinateur
        </footer>
      </div>
    </TooltipProvider>
  );
}
