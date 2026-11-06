# Recruiter Copilot — hackathon IA souveraine (AI First × 42 Paris, 2026-11-06)

## RÈGLE D'OR (non négociable)
- L'assistant de code (Claude Code) ne lit JAMAIS les candidatures : ni `kit/` (CV du kit), ni aucun CV importé, ni `data/` (base, index, exports dérivés). `.claude/settings.json` bloque `data/` et `kit/` pour Claude Code.
- CV autorisés : `cv-exemple-agent.md`, ainsi que les fixtures fictives de `backend/fixtures/` et `samples/`.
- Interdit : `cat`, `grep`, `Read`, `ls` détaillé ou tout script qui afficherait le contenu des CV dans la conversation. Pour tester sur les vrais CV du kit, c'est l'utilisateur qui lance l'application lui-même.
- Les sorties de l'application sur les CV (résumés, questions…) ne doivent pas non plus être collées ou lues ici.
- Le dépôt GitHub est **public** : aucun CV ni aucune base ne doit être commité (voir `.gitignore`).

## Contraintes imposées
- Le traitement IA des candidatures se fait en local, avec Ollama sur http://127.0.0.1:11434 et `OLLAMA_NO_CLOUD=1`.
  - Modèle par défaut : `ministral-3:3b` (« rapide »).
  - Modèle en option : `ministral-3:8b` (« précis »).
  - Jamais de modèle `-cloud`.
- Un candidat doit pouvoir être effacé de façon vérifiable : le CV et tout ce qui en dérive (texte extrait, fiche, embeddings, cache, journaux).
- L'humain décide : pas de classement automatique ni de recommandation d'embauche.
- Ne garder que les données utiles au poste : écarter l'âge, la date de naissance, la photo, la situation familiale, la nationalité, la santé, etc.

## Livrables
A. Prototype (`backend/` + `web/`), B. Carte du cycle de vie des données (`docs/cycle-de-vie.md`), C. Registre simplifié (`docs/registre.md`). Les livrables B et C doivent rester cohérents avec le code réel.

## Avant la démo
Lancer le sous-agent `privacy-auditor`. Puis, Wi-Fi coupé : `python scripts/check_local.py`, et dérouler import → réponse utile → effacement → carte → registre.
