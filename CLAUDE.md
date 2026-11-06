# Recruiter Copilot local · hackathon AI First × 42 Paris (édition 11)

Assistant RH qui analyse 20 CV fictifs et une fiche de poste avec un modèle **local**. Brief : https://ai-first-42-recruiter-copilot.trybailey.app/

## Règles non négociables
- **Aucun CV vers une IA distante.** Le seul modèle appelé est Ollama sur `http://127.0.0.1:11434`. Jamais de modèle `-cloud`.
- **Claude Code est une IA distante.** Ne lis jamais `data/` : CV, base, index, exports. Pour tester, écris toi-même de faux CV dans `samples/`.
- **Minimisation.** N'extraire que ce qui sert au poste : expériences, compétences, formations, langues, liens professionnels. Jamais l'adresse, la date de naissance, l'âge, la photo ou la situation familiale.
- **La décision reste humaine.** L'app compare sur des critères visibles tirés de la fiche de poste. Elle sépare les faits du CV des interprétations du modèle.
- **Supprimer efface tout.** Supprimer un candidat efface toutes ses copies : fichier original, lignes SQLite avec `PRAGMA secure_delete = ON`, cache, session et index éventuel.

## Stack
- Python 3.12 dans `.venv/`. Lancer l'app : `.venv\Scripts\streamlit run app.py`, puis ouvrir http://127.0.0.1:8501
- Streamlit : télémétrie coupée et écoute locale seulement (voir `.streamlit/config.toml`)
- Ollama avec `ministral-3:3b` (Mistral AI, Apache 2.0) : sorties JSON structurées via le paramètre `format`, et `OLLAMA_NO_CLOUD=1`
- SQLite pour les données structurées ; `pypdf` et `python-docx` pour extraire le texte des CV

## Livrables, dans `docs/`
- `data-lifecycle-map.md` : flux réels, copies, accès et effacement, en Mermaid
- `registre.md` : les 7 champs (finalité, personnes et données, base légale, accès, stockage, durée et suppression, sécurité)

## Avant la démo
Lancer le sous-agent `privacy-auditor`. Puis couper le réseau et dérouler : import d'un CV, réponse utile, suppression, carte des flux, registre.
