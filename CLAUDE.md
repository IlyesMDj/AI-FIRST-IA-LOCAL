# Recruiter Copilot — hackathon IA souveraine (2026-11-06)

## RÈGLE D'OR (non négociable)
- L'assistant de code (Claude Code) ne lit JAMAIS le dossier des candidatures (`cv/` du kit, ni aucun CV importé, ni la base / l'index / les exports dérivés).
- Seul fichier CV autorisé : `cv-exemple-agent.md`.
- Pas de `cat`, `grep`, `Read`, `ls` détaillé ni d'exécution de script qui afficherait le contenu des CV dans la conversation. Pour tester sur les vrais CV du kit, c'est l'utilisateur qui lance l'application lui-même.
- Les sorties de l'application sur les CV (résumés, questions…) ne doivent pas non plus être collées ou lues ici.

## Contraintes imposées
- Le traitement IA des candidatures se fait en local : Ollama sur http://localhost:11434, modèle `ministral-3:8b` (repli : `ministral-3:3b`).
- Un candidat doit pouvoir être effacé de façon vérifiable (CV + tout ce qui en dérive : texte extrait, fiche, embeddings, cache, journaux).
- L'humain décide : pas de classement automatique ni de recommandation d'embauche.
- Ne garder que les données utiles au poste (écarter âge, date de naissance, photo, situation familiale, nationalité, santé, etc.).

## Livrables
A. Prototype — B. Carte du cycle de vie des données — C. Registre simplifié (cohérent avec le code réel).
