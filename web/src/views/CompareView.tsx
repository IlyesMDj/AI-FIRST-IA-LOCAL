import { useEffect, useState } from "react";
import { AlertTriangle, Info } from "lucide-react";
import { api, type CompareResult } from "@/api";
import { ASSESSMENT_STYLE, AssessmentLegend, isUnsupportedClaim, UNSUPPORTED_LABEL, ErrorNote, PageHeader, Spinner } from "@/components/common";
import { Card } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function CompareView() {
  const [data, setData] = useState<CompareResult | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.compare().then(setData).catch(setError);
  }, []);

  // Le contrat renvoie les candidats dans l'ordre d'import ; on n'affiche que ceux prêts, sans jamais réordonner.
  const cands = data?.candidates.filter((c) => c.status === "ready") ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Comparer"
        description="Vue d'ensemble critère par critère, candidats dans l'ordre d'import. Pas de total, pas de tri : à vous de lire chaque ligne."
      />
      <ErrorNote error={error} />
      {!data && !error && <Spinner />}
      {data && cands.length === 0 && <p className="text-muted-foreground text-sm">Aucun candidat analysé pour l'instant.</p>}
      {data && cands.length > 0 && (
        <>
          <AssessmentLegend />
          <Card className="gap-0 overflow-hidden py-0">
            <div className="overflow-x-auto">
              <table className="w-full border-separate border-spacing-0 text-sm">
                <thead>
                  <tr>
                    <th className="bg-card sticky left-0 z-10 min-w-56 border-r border-b px-4 py-3 text-left text-xs font-medium text-muted-foreground">
                      Critère
                    </th>
                    {cands.map((c) => (
                      <th key={c.id} className="min-w-40 border-b px-3 py-3 text-left font-medium">
                        <a href={`#/candidats/${encodeURIComponent(c.id)}`} className="hover:text-primary hover:underline">
                          {c.display_name}
                        </a>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.criteria.map((cr) => (
                    <tr key={cr.id}>
                      <th scope="row" className="bg-card sticky left-0 z-10 border-r border-b px-4 py-2.5 text-left align-top font-normal">
                        <div className="font-medium">{cr.label}</div>
                        <div className="text-muted-foreground font-mono text-xs">{cr.id}</div>
                      </th>
                      {cands.map((c) => {
                        const cell = c.cells[cr.id];
                        if (!cell) {
                          return (
                            <td key={c.id} className="text-muted-foreground border-b px-3 py-2.5 text-xs">
                              —
                            </td>
                          );
                        }
                        const unsupported = isUnsupportedClaim(cell.assessment, cell.quote);
                        const s = unsupported ? ASSESSMENT_STYLE["non trouvé"] : (ASSESSMENT_STYLE[cell.assessment] ?? ASSESSMENT_STYLE["non trouvé"]);
                        const Icon = unsupported ? AlertTriangle : s.icon;
                        const content = (
                          <div
                            className={cn("flex h-full items-center gap-1.5 rounded-md px-2.5 py-2 text-xs font-medium", s.cell, cell.quote && "cursor-help", unsupported && "border border-dashed")}
                            title={unsupported ? `« ${cell.assessment} » selon le modèle, mais ${UNSUPPORTED_LABEL}` : undefined}
                          >
                            <Icon className="size-3.5 shrink-0" aria-hidden />
                            {unsupported ? <span>{cell.assessment} ? <span className="font-normal">· {UNSUPPORTED_LABEL}</span></span> : cell.assessment}
                            {cell.quote && <Info className="ml-auto size-3 opacity-60" aria-label="citation disponible" />}
                          </div>
                        );
                        return (
                          <td key={c.id} className="border-b p-1.5 align-top">
                            {cell.quote ? (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <div tabIndex={0}>{content}</div>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <span className="italic">« {cell.quote} »</span>
                                </TooltipContent>
                              </Tooltip>
                            ) : (
                              content
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
