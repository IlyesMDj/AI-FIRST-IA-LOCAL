import { useEffect, useState } from "react";
import { api, type ErasureProof } from "@/api";
import { ErrorNote, PageHeader, Spinner } from "@/components/common";
import { ErasureProofCard } from "@/components/ErasureProofCard";

export function ErasuresView() {
  const [list, setList] = useState<ErasureProof[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.erasures().then(setList).catch(setError);
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Journal des effacements"
        description="Preuves d'effacement, de la plus récente à la plus ancienne. Le journal ne contient ni nom ni texte de CV : uniquement l'empreinte de l'identifiant et le résultat des vérifications."
      />
      <ErrorNote error={error} />
      {!list && !error && <Spinner />}
      {list && list.length === 0 && <p className="text-muted-foreground text-sm">Aucun effacement enregistré.</p>}
      <div className="space-y-4">
        {list?.map((p) => (
          <ErasureProofCard key={p.candidate_id_hash + p.erased_at} proof={p} compact />
        ))}
      </div>
    </div>
  );
}
