# Recruiter Copilot local

Assistant RH qui analyse des CV **sur la machine**, avec un modèle local et sans IA distante.
Projet du hackathon AI First × 42 Paris, édition 11 ([brief](https://ai-first-42-recruiter-copilot.trybailey.app/)).

## ⚠️ Dépôt public : aucune donnée candidat
- Les CV vont dans `data/cvs/`. Ce dossier est ignoré par git : ne forcez jamais son ajout avec `git add -f`.
- Avant chaque push, `git status` ne doit lister aucun CV ni aucune base de données.
- Si vous utilisez un agent IA distant (Claude Code, Cursor, Copilot…), ne lui faites jamais lire `data/`. Pour Claude Code, c'est bloqué par `.claude/settings.json`.

## Installation (~10 min, dont 3 Go de modèle)
1. **Installer Ollama :** https://ollama.com/download (sous Windows : `winget install Ollama.Ollama`).
2. **Couper le cloud d'Ollama**, puis quitter Ollama (icône près de l'horloge) et le relancer :
   - Windows : `setx OLLAMA_NO_CLOUD 1`
   - macOS : `launchctl setenv OLLAMA_NO_CLOUD 1`
3. **Télécharger le modèle :** `ollama pull ministral-3:3b` (Mistral AI, Apache 2.0).
   - Astuce : copiez le dossier `.ollama/models` d'un PC à l'autre avec une clé USB plutôt que de retélécharger 3 Go sur le Wi-Fi.
4. **Environnement Python :**
   ```
   python -m venv .venv
   .venv\Scripts\activate          (macOS/Linux : source .venv/bin/activate)
   pip install -r requirements.txt
   ```
5. **Vérifier :** `python scripts/check_local.py`. Toutes les lignes doivent afficher `[OK]`.
   - Sur un portable sans GPU, comptez ~45 s par CV.
   - Relancez ce script Wi-Fi coupé pour la preuve « réseau coupé ».

## Lancer l'app
`streamlit run app.py`, puis ouvrez http://127.0.0.1:8501.

L'app n'écoute que sur votre machine, et la télémétrie de Streamlit est coupée (voir `.streamlit/config.toml`).

## Règles du projet
Elles sont détaillées dans [CLAUDE.md](CLAUDE.md) :
- aucun CV vers une IA distante ;
- n'extraire que ce qui sert au poste ;
- la décision reste humaine ;
- supprimer un candidat efface toutes ses copies.

Avant la démo, l'agent `privacy-auditor` (`.claude/agents/`) vérifie ces points.
