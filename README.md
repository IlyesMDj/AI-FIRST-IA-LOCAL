# Recruiter Copilot — IA souveraine, 100 % locale

Un assistant RH qui aide une recruteuse à lire, comprendre et comparer des candidatures, et à préparer ses entretiens, **sans qu'aucun CV ne quitte la machine**. Le modèle (Ministral 3, Mistral AI, Apache 2.0) tourne en local via Ollama.

Projet du hackathon AI First × 42 Paris, édition 11 ([brief](https://ai-first-42-recruiter-copilot.trybailey.app/)).

## ⚠️ Dépôt public : aucune donnée candidat
- Le kit du soir va dans `kit/` et la base dans `data/`. Les deux sont ignorés par git : ne forcez jamais leur ajout avec `git add -f`.
- Avant chaque push, `git status` ne doit lister aucun CV ni aucune base.
- Ne faites jamais lire `kit/cv/` ni `data/` à un agent IA distant (Claude Code, Cursor, Copilot…). Pour Claude Code, c'est bloqué par `.claude/settings.json`.

## En deux minutes
- **Rien ne sort** : API, interface et modèle écoutent sur `127.0.0.1`. La démo se fait Wi-Fi coupé.
- **On ne garde que l'utile** : coordonnées, âge, nationalité, famille, santé et religion sont masqués *avant* le stockage et *avant* l'IA. Le fichier d'origine n'est jamais écrit sur disque : l'upload est traité en mémoire.
- **L'humain décide** : ni score, ni classement, ni recommandation.
  - Chaque critère de la fiche de poste est évalué *présent / partiel / non trouvé*.
  - « Présent » exige une **citation mot pour mot retrouvée dans le CV**. Sinon, le critère est affiché « non étayé ».
  - Le Q&A refuse « je le prends ? » et coupe toute réponse qui formulerait un verdict.
- **Effacement prouvé** : en un clic, suppression en cascade, `secure_delete`, `VACUUM`, puis vérification que des extraits du CV sont introuvables **dans les octets mêmes de la base**. La preuve est affichée et journalisée sans donnée personnelle.
- **Résistant aux CV piégés** : le texte du CV est traité comme une donnée délimitée, les marqueurs sont neutralisés et les sorties validées par schéma.

## Méthode
1. Contrat d'interfaces figé d'abord (`CONTRACTS.md`).
2. Agents en parallèle sur des fichiers disjoints : extraction / masquage / effacement, IA, interface, intégration.
3. **Deux relectures indépendantes**, qui ont trouvé 21 défauts démontrés, tous corrigés. Exemples : verdict d'embauche en Q&A, CV long tronqué en silence, espace insécable qui faisait fuir l'âge, journal SQLite contenant le CV en clair.

Résultat : 397 tests. Règle d'or respectée : l'assistant de code n'a jamais lu un CV du kit.

## Lancer
Prérequis : Python 3.12+, Node 20+, Ollama.

1. **Ollama, cloud coupé.** Définissez la variable, puis quittez et relancez Ollama :
   - Windows : `setx OLLAMA_NO_CLOUD 1`
   - macOS : `launchctl setenv OLLAMA_NO_CLOUD 1`

   Téléchargez ensuite le modèle : `ollama pull ministral-3:3b` (en option : `ministral-3:8b`). Astuce : copiez le dossier `.ollama/models` d'un PC à l'autre avec une clé USB plutôt que de retélécharger 3 Go sur le Wi-Fi.
2. **Kit du soir.** Dézippez `2026-11-06-recruiter-copilot-kit.zip` à la racine du dépôt, pour obtenir `kit/fiche-de-poste.md` et `kit/cv/`.
   - La fiche de poste est chargée au démarrage.
   - Les CV s'importent par glisser-déposer dans l'interface.
3. **Installation et lancement :**
   ```powershell
   python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
   cd web; npm install; cd ..
   powershell -ExecutionPolicy Bypass -File .\start.ps1     # → http://127.0.0.1:5173
   ```
4. **Vérifications :**
   ```powershell
   .\.venv\Scripts\python.exe scripts\check_local.py       # chaîne IA locale ; à relancer Wi-Fi coupé
   .\.venv\Scripts\python.exe -m pytest backend/tests -q   # tests (sans modèle)
   ```

## Livrables
- Prototype : `backend/` (FastAPI, SQLite) + `web/` (React, Vite, Tailwind, shadcn/ui)
- Carte du cycle de vie des données : [`docs/cycle-de-vie.md`](docs/cycle-de-vie.md)
- Registre simplifié : [`docs/registre.md`](docs/registre.md)
- Avant la démo : sous-agent `privacy-auditor` (`.claude/agents/`)

## Limites assumées
- **Lenteur sur CPU seul** : ~85 s par CV, ~3 min pour un scan.
- **Masquage par règles** : il peut rater une formulation inédite.
- **Sens des citations non vérifié** : une citation comme « jamais pratiqué Python » est retrouvée dans le CV, mais son sens n'est pas contrôlé.
- **Hors périmètre de l'effacement** : le fichier source et la mémoire d'Ollama.
- **Pas de comptes utilisateurs ni de chiffrement de la base** (BitLocker recommandé).
