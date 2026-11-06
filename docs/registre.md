# Livrable C — Registre simplifié : Recruiter Copilot (Atelier Nova)

Rempli pendant le build, cohérent avec le code au 2026-11-06. Prototype, pas une certification. Les points marqués *à valider* relèvent du DPO.

| Rubrique | Contenu |
|---|---|
| **Finalité** | Aider la responsable RH à lire et comparer les candidatures reçues pour le poste de développeur Python confirmé, et à préparer les entretiens. **Pas de décision automatisée** : l'outil ne note pas, ne classe pas, ne recommande pas (filtres en entrée et en sortie du modèle, aucun score dans l'API ni l'interface). |
| **Personnes concernées** | Candidats au poste. |
| **Données conservées** | Texte du CV **masqué** ; nom ; résumé du profil au regard de la fiche ; pour chaque critère de la fiche, une évaluation (présent / partiel / non trouvé) et une citation exacte du CV ; questions d'entretien générées ; compte des données écartées par catégorie (pas leur valeur). |
| **Données écartées** (masquées avant tout stockage et avant l'IA) | Email, téléphone, adresse, date de naissance et âge, nationalité, situation familiale, santé et handicap, religion, numéro de sécurité sociale, liens vers réseaux personnels, mention de photo. Le fichier d'origine n'est jamais stocké. Critères discriminatoires (âge, origine, « culture fit »…) refusés ou signalés. |
| **Base légale** | *À valider* : mesures précontractuelles prises à la demande de la personne (art. 6.1.b RGPD) — le candidat a postulé ; à défaut intérêt légitime de l'employeur à gérer ses recrutements (6.1.f). Pas le consentement : il ne serait pas libre dans une relation candidat/employeur. Information des candidats à prévoir (mention dans l'accusé de réception). |
| **Accès et destinataires** | Prototype mono-poste : la personne qui utilise le poste (responsable RH). API et interface accessibles uniquement depuis la machine (`127.0.0.1`). Aucun destinataire externe ; aucun fournisseur d'IA en ligne (modèle Ministral 3, Apache 2.0, exécuté par Ollama en local). **Pas de comptes ni de rôles** (hors périmètre du brief) : limite assumée. |
| **Stockage et localisation** | Une seule base SQLite `data/copilot.db` sur le poste. Pas de fichier temporaire de CV (uploads en mémoire, testé), pas de journal SQLite sur disque, pas de cache navigateur (`no-store`), pas de stockage navigateur. Copies transitoires en mémoire : API, Ollama, onglet. Détail : `cycle-de-vie.md`. |
| **Durée et suppression** | Cible : suppression à la clôture du recrutement ; conservation d'un candidat non retenu jusqu'à 2 ans seulement s'il en est informé et ne s'y oppose pas (*à vérifier dans le référentiel CNIL recrutement*). **Purge automatique non implémentée** (limite). Effacement d'un candidat en un clic : cascade + `secure_delete` + `VACUUM`, puis preuve vérifiée (lignes restantes et recherche d'extraits dans les octets de la base) affichée et journalisée sans donnée personnelle. |
| **Sécurité** | Écoute locale uniquement ; requêtes SQL paramétrées ; défense contre les CV piégés (bloc de données délimité, marqueurs neutralisés, règle répétée, sorties validées par schéma, citations re-vérifiées dans le texte) ; aucun log contenant nom, fichier ou texte de CV ; taille d'upload bornée. **Limites** : base non chiffrée (recommandation : BitLocker), pas d'authentification, RAM d'Ollama non purgée à l'effacement, fichiers sources hors application. |

## Garde-fous « humain dans la boucle » (AI Act, système à haut risque)
- Critères de comparaison visibles et éditables par la recruteuse ; ce sont les seuls utilisés.
- Chaque affirmation « présent » s'appuie sur une citation retrouvée mot pour mot dans le CV ; sinon elle est dégradée et affichée « non étayé ».
- Version du prompt et modèle enregistrés avec chaque analyse (traçabilité).
- Le Q&A refuse les questions de décision (« je le prends ? », « classe-les ») et coupe toute réponse qui formulerait un verdict.

## Mesures et limites constatées (poste de démo : CPU seul, 16 Go, ministral-3:3b)
| Mesuré | Valeur |
|---|---|
| Analyse d'un CV texte | ~85 s |
| CV scanné (vision + analyse) | ~205 s |
| Q&A, premier token / réponse complète | ~4 s / 8-33 s |
| Effacement + vérification | ~0,1 s, 11-13 extraits recherchés, 0 trouvé |
| Données écartées sur le CV scanné de test | email, téléphone, date de naissance, nationalité, situation familiale ×2 — 0 fuite dans le texte stocké |

Limites : CV refusé au-delà de 20 000 caractères (temps CPU) ; le masquage est déterministe (regex) et peut rater une formulation inédite ; une citation peut être exacte mais négative (« jamais pratiqué Python ») — le sens n'est pas vérifié par le code ; le 3b laisse ~1/3 des critères « partiel » faute de citation retrouvée (affiché « non étayé », jamais présenté comme acquis).
