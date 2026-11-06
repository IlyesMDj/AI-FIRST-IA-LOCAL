# Recruiter Copilot — IA souveraine, 100 % locale

Un assistant RH qui aide une recruteuse à lire, comprendre et comparer des candidatures, et à préparer ses entretiens, **sans qu'aucun CV ne quitte la machine**. Le modèle (Ministral 3, Mistral AI, Apache 2.0) tourne en local via Ollama.

## En deux minutes
- **Rien ne sort** : API, interface et modèle écoutent sur `127.0.0.1`. Démo Wi-Fi coupé.
- **On ne garde que l'utile** : coordonnées, âge, nationalité, famille, santé, religion sont masqués *avant* le stockage et *avant* l'IA. Le fichier d'origine n'est jamais écrit sur disque (upload traité en mémoire).
- **L'humain décide** : ni score, ni classement, ni recommandation. Chaque critère de la fiche de poste est évalué *présent / partiel / non trouvé*, et « présent » exige une **citation mot pour mot retrouvée dans le CV** ; sinon c'est affiché « non étayé ». Le Q&A refuse « je le prends ? » et coupe toute réponse qui formulerait un verdict.
- **Effacement prouvé** : un clic → suppression en cascade, `secure_delete`, `VACUUM`, puis vérification que des extraits du CV sont introuvables **dans les octets mêmes de la base**. La preuve est affichée et journalisée sans donnée personnelle.
- **Résistant aux CV piégés** : texte du CV traité comme une donnée délimitée, marqueurs neutralisés, sorties validées par schéma.

## Méthode
Contrat d'interfaces figé d'abord (`CONTRACTS.md`), puis agents en parallèle sur des fichiers disjoints (extraction/masquage/effacement · IA · interface · intégration), et **deux relectures indépendantes** qui ont trouvé 21 défauts démontrés (verdict d'embauche en Q&A, CV long tronqué en silence, espace insécable qui faisait fuir l'âge, journal SQLite contenant le CV en clair…), tous corrigés. 397 tests. Règle d'or respectée : l'assistant de code n'a jamais lu un CV du kit.

## Lancer
Prérequis : Ollama + `ollama pull ministral-3:3b` (et `ministral-3:8b`), Python 3.12+, Node 20+.
```powershell
python -m venv .venv; .\.venv\Scripts\pip install fastapi uvicorn python-multipart pymupdf pydantic ollama httpx pytest
cd web; npm install; cd ..
powershell -ExecutionPolicy Bypass -File .\start.ps1     # → http://127.0.0.1:5173
.\.venv\Scripts\python.exe -m pytest backend/tests -q   # tests (sans modèle)
```

## Livrables
- Prototype : `backend/` (FastAPI, SQLite) + `web/` (React, Vite, Tailwind, shadcn/ui)
- Carte du cycle de vie des données : [`docs/cycle-de-vie.md`](docs/cycle-de-vie.md)
- Registre simplifié : [`docs/registre.md`](docs/registre.md)

## Limites assumées
CPU seul : ~85 s par CV, ~3 min pour un scan · masquage par règles (peut rater une formulation inédite) · le sens d'une citation n'est pas vérifié (« jamais pratiqué Python ») · fichier source et mémoire d'Ollama hors du périmètre de l'effacement · pas de comptes utilisateurs ni de chiffrement de la base (BitLocker recommandé).
