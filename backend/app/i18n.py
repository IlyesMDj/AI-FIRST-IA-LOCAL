"""Translation of user-facing backend messages (English source → French).

Messages are produced in English everywhere in the backend (including
warnings persisted in the database by the worker) and translated **at
response time** according to the request language (``X-Lang`` header, then
``Accept-Language``). Unknown messages fall back to English.

``tests/test_i18n.py`` checks that every message raised by the code has a
French translation.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import Request

Lang = Literal["en", "fr"]

EXACT: dict[str, str] = {
    # --- generic / not found ------------------------------------------------
    "Candidate not found": "Candidat introuvable",
    "Candidate not found.": "Candidat introuvable.",
    "Conversation not found": "Conversation introuvable",
    "Conversation not found.": "Conversation introuvable.",
    "Job description not found": "Fiche de poste introuvable",
    "Job description not found.": "Fiche de poste introuvable.",
    "Analysis not found": "Analyse introuvable",
    "Report not found": "Rapport introuvable",
    "Not Found": "Introuvable",
    # --- candidates API -----------------------------------------------------
    "The document has not been read yet.": "Le document n'a pas encore été lu.",
    "The original document is not kept (see AI settings).": "Le document original n'est pas conservé (voir les réglages IA).",
    "Original document not found.": "Document original introuvable.",
    "This candidate is already being processed.": "Ce candidat est déjà en cours de traitement.",
    "The original document is no longer stored; it cannot be processed again.":
        "Le document original n'est plus conservé : il ne peut pas être traité à nouveau.",
    "This exact file was already imported. It was not imported again.":
        "Ce fichier exact a déjà été importé. Il n'a pas été importé une seconde fois.",
    "The file could not be saved locally.": "Le fichier n'a pas pu être enregistré localement.",
    "Unexpected error while processing this document. See the application logs.":
        "Erreur inattendue pendant le traitement de ce document. Consultez les journaux de l'application.",
    # --- processing steps -----------------------------------------------------
    "Reading document": "Lecture du document",
    "Removing unnecessary personal data": "Suppression des données personnelles inutiles",
    "Extracting professional information": "Extraction des informations professionnelles",
    "Indexing for search": "Indexation pour la recherche",
    # --- warnings (persisted) -----------------------------------------------
    "This document contains text that looks like instructions addressed to an AI. It was treated as plain content and ignored as an instruction.":
        "Ce document contient un texte qui ressemble à des instructions adressées à une IA. Il a été traité comme du simple contenu et ignoré en tant qu'instruction.",
    "Some extracted items unrelated to the job were discarded (data minimisation).":
        "Certains éléments extraits sans rapport avec le poste ont été écartés (minimisation des données).",
    "No professional information could be extracted from this document.":
        "Aucune information professionnelle n'a pu être extraite de ce document.",
    "This profile may correspond to an existing candidate. Profiles were NOT merged: please review.":
        "Ce profil correspond peut-être à un candidat existant. Les profils n'ont PAS été fusionnés : merci de vérifier.",
    "Text obtained by local OCR: check it for recognition errors.":
        "Texte obtenu par OCR local : vérifiez les erreurs de reconnaissance.",
    "same email address": "même adresse e-mail",
    "same name and phone number": "même nom et même numéro de téléphone",
    # --- documents --------------------------------------------------------------
    "The file is empty.": "Le fichier est vide.",
    "The file has an image extension but is not a valid JPEG or PNG image.":
        "Le fichier porte une extension d'image mais n'est pas une image JPEG ou PNG valide.",
    "This file is an image: reading it requires OCR, which is disabled in settings.":
        "Ce fichier est une image : sa lecture nécessite l'OCR, désactivé dans les réglages.",
    "The image is corrupted and cannot be read.": "L'image est corrompue et ne peut pas être lue.",
    "The image is too large to be processed.": "L'image est trop grande pour être traitée.",
    "No readable text could be found in this image.": "Aucun texte lisible n'a été trouvé dans cette image.",
    "The text file contains binary data.": "Le fichier texte contient des données binaires.",
    "The document contains no usable text.": "Le document ne contient aucun texte exploitable.",
    "The file has a .pdf extension but is not a valid PDF.": "Le fichier porte l'extension .pdf mais n'est pas un PDF valide.",
    "The file has a .docx extension but is not a valid Word document.":
        "Le fichier porte l'extension .docx mais n'est pas un document Word valide.",
    "The Word document is corrupted.": "Le document Word est corrompu.",
    "The Word document could not be read.": "Le document Word n'a pas pu être lu.",
    "The Word document is abnormally large once decompressed.": "Le document Word est anormalement volumineux une fois décompressé.",
    "The Word document is invalid (missing content).": "Le document Word est invalide (contenu manquant).",
    "The PDF is corrupted or malformed and cannot be read.": "Le PDF est corrompu ou mal formé et ne peut pas être lu.",
    "The PDF has no pages.": "Le PDF ne contient aucune page.",
    "The PDF is password-protected.": "Le PDF est protégé par un mot de passe.",
    "This PDF appears to be scanned (no selectable text) and OCR is disabled in settings.":
        "Ce PDF semble scanné (pas de texte sélectionnable) et l'OCR est désactivé dans les réglages.",
    "No readable text could be found in this scanned PDF.": "Aucun texte lisible n'a été trouvé dans ce PDF scanné.",
    "This PDF appears to be scanned and the local OCR engine is not installed (pip install rapidocr-onnxruntime).":
        "Ce PDF semble scanné et le moteur OCR local n'est pas installé (pip install rapidocr-onnxruntime).",
    "Unsupported file type.": "Type de fichier non pris en charge.",
    # --- AI engine ---------------------------------------------------------------
    "Cannot reach the local AI engine (Ollama). Make sure Ollama is running.":
        "Impossible de joindre le moteur d'IA local (Ollama). Vérifiez qu'Ollama est démarré.",
    "Cannot reach the local AI engine (Ollama).": "Impossible de joindre le moteur d'IA local (Ollama).",
    "The local AI engine did not answer in time. Try again, reduce the context size or choose a smaller model in AI settings.":
        "Le moteur d'IA local n'a pas répondu à temps. Réessayez, réduisez la taille du contexte ou choisissez un modèle plus léger dans les réglages IA.",
    "The local AI engine did not answer in time.": "Le moteur d'IA local n'a pas répondu à temps.",
    "Communication error with the local AI engine.": "Erreur de communication avec le moteur d'IA local.",
    "The selected model is not installed in Ollama. Choose another model in AI settings.":
        "Le modèle sélectionné n'est pas installé dans Ollama. Choisissez un autre modèle dans les réglages IA.",
    "The selected model is not installed in Ollama.": "Le modèle sélectionné n'est pas installé dans Ollama.",
    "Not enough memory to load the model. Close other applications or select a smaller model.":
        "Mémoire insuffisante pour charger le modèle. Fermez d'autres applications ou choisissez un modèle plus léger.",
    "The local AI engine returned an error.": "Le moteur d'IA local a renvoyé une erreur.",
    "The embedding model returned an unexpected response.": "Le modèle d'embedding a renvoyé une réponse inattendue.",
    "The AI model returned an invalid response several times. Try again or select another model.":
        "Le modèle d'IA a renvoyé plusieurs fois une réponse invalide. Réessayez ou choisissez un autre modèle.",
    "The local AI engine (Ollama) is not reachable. Start Ollama, then refresh.":
        "Le moteur d'IA local (Ollama) est injoignable. Démarrez Ollama puis actualisez.",
    "Install a model with 'ollama pull'.": "Installez un modèle avec « ollama pull ».",
    "A benchmark is already running.": "Un banc d'essai est déjà en cours.",
    # --- analysis / interview / assistant -------------------------------------
    "The candidate's CV has not been processed yet.": "Le CV du candidat n'a pas encore été traité.",
    "The job description has no requirement to analyse.": "La fiche de poste ne contient aucune exigence à analyser.",
    "Unexpected error during the analysis.": "Erreur inattendue pendant l'analyse.",
    "Unexpected error while preparing the interview.": "Erreur inattendue pendant la préparation de l'entretien.",
    "Unexpected error while answering.": "Erreur inattendue pendant la réponse.",
    "No answer was produced.": "Aucune réponse n'a été produite.",
    "All candidates must have a processed CV.": "Tous les candidats doivent avoir un CV traité.",
    "The model claimed evidence, but the quoted text could not be found in the CV. Status changed to 'cannot be determined'. Please check the CV manually.":
        "Le modèle a avancé une preuve, mais le texte cité est introuvable dans le CV. Statut changé en « impossible à déterminer ». Vérifiez le CV manuellement.",
    "Some quotes could not be found verbatim in the CV and are marked as unverified.":
        "Certaines citations sont introuvables telles quelles dans le CV et sont marquées comme non vérifiées.",
    "Clearly demonstrated": "Clairement démontré",
    "Partially demonstrated": "Partiellement démontré",
    "Not found in the CV": "Non trouvé dans le CV",
    "Cannot be determined": "Impossible à déterminer",
    "Technical questions": "Questions techniques",
    "Experience questions": "Questions sur l'expérience",
    "Project questions": "Questions sur les projets",
    "Problem-solving questions": "Questions de résolution de problèmes",
    "Questions to clarify CV information": "Questions pour clarifier le CV",
    # --- deletion report --------------------------------------------------------
    "Database records (all tables)": "Enregistrements en base (toutes les tables)",
    "Original document and temporary files": "Document original et fichiers temporaires",
    "Search and semantic retrieval": "Recherche et recherche sémantique",
    "API / interface lookup": "Accès par l'API / l'interface",
    "Database journal (WAL) checkpoint": "Vidage du journal de la base (WAL)",
    "SQLite secure_delete=ON (freed pages are zeroed)": "SQLite secure_delete=ON (pages libérées remises à zéro)",
    "Files are overwritten with zeros before removal, but on SSDs (wear levelling, TRIM) and journaling filesystems the physical blocks may persist until reused by the drive: this is not forensic erasure.":
        "Les fichiers sont écrasés par des zéros avant suppression, mais sur les SSD (répartition de l'usure, TRIM) et les systèmes de fichiers journalisés, les blocs physiques peuvent subsister jusqu'à leur réutilisation : ce n'est pas un effacement forensique.",
    "Copies outside the application (e-mail attachments, Downloads folder, system or cloud backups, antivirus quarantine) are not managed by the application and must be handled separately.":
        "Les copies hors de l'application (pièces jointes, dossier Téléchargements, sauvegardes système ou cloud, quarantaine antivirus) ne sont pas gérées par l'application et doivent être traitées séparément.",
    "Ollama keeps no prompt history on disk, but model memory (KV cache) is only released when the model is unloaded or overwritten by later requests.":
        "Ollama ne conserve aucun historique de prompts sur disque, mais la mémoire du modèle (cache KV) n'est libérée qu'au déchargement du modèle ou par des requêtes ultérieures.",
    # --- system / privacy -----------------------------------------------------------
    "Recommended primary model (best structured extraction & French; fits in 8 GB VRAM)":
        "Modèle principal recommandé (meilleure extraction structurée et meilleur français ; tient dans 8 Go de VRAM)",
    "Secondary model (fast, reliable JSON)": "Modèle secondaire (rapide, JSON fiable)",
    "Alternative (12B, strong French; partially offloaded to CPU on 8 GB VRAM, slower)":
        "Alternative (12B, bon en français ; partiellement déporté sur le CPU avec 8 Go de VRAM, plus lent)",
    "Embedding model for semantic search": "Modèle d'embedding pour la recherche sémantique",
    "Small vision model (optional image understanding)": "Petit modèle de vision (compréhension d'images, optionnel)",
    "Original documents": "Documents originaux",
    "Temporary processing files": "Fichiers temporaires de traitement",
    "Database (profiles, text, vectors, analyses, chats)": "Base de données (profils, texte, vecteurs, analyses, conversations)",
    "none (the backend only calls the local Ollama endpoint)": "aucun (le serveur n'appelle que le point d'accès Ollama local)",
    "none": "aucune",
    # --- disclaimers ------------------------------------------------------------------
    "This analysis lists evidence found in the CV for each job requirement. It is not a score, a ranking or a hiring recommendation. 'Not found in the CV' only means the CV does not mention it; it does not prove the candidate lacks the skill. The decision remains with the recruiter.":
        "Cette analyse liste les preuves trouvées dans le CV pour chaque exigence du poste. Ce n'est ni une note, ni un classement, ni une recommandation d'embauche. « Non trouvé dans le CV » signifie seulement que le CV ne le mentionne pas ; cela ne prouve pas que le candidat n'a pas la compétence. La décision appartient au recruteur.",
    "Questions are suggestions to support a structured, job-related interview. Review them before use.":
        "Ces questions sont des suggestions pour un entretien structuré et lié au poste. Relisez-les avant utilisation.",
    "Side-by-side view of the evidence in each CV. No overall score or winner is computed; the comparison and the decision remain with the recruiter.":
        "Vue côte à côte des preuves de chaque CV. Aucune note globale ni aucun « gagnant » n'est calculé ; la comparaison et la décision appartiennent au recruteur.",
}

PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^At most (\d+) files can be imported at once\.$"), "Au plus {0} fichiers peuvent être importés à la fois."),
    (re.compile(r"^File larger than (\d+) MB\.$"), "Fichier de plus de {0} Mo."),
    (re.compile(r"^Unsupported file type '(.*)'\. Accepted formats: PDF, DOCX, TXT, JPG, PNG\.$"),
     "Type de fichier non pris en charge « {0} ». Formats acceptés : PDF, DOCX, TXT, JPG, PNG."),
    (re.compile(r"^Only the first (\d+) of (\d+) pages were processed\.$"), "Seules les {0} premières pages sur {1} ont été traitées."),
    (re.compile(r"^The CV is long: only the first (\d+) characters were analysed by the AI model\.$"),
     "Le CV est long : seuls les {0} premiers caractères ont été analysés par le modèle d'IA."),
    (re.compile(r"^(\d+) extracted item\(s\) could not be matched with the CV text\. They are marked 'unverified' and should be checked against the original document\.$"),
     "{0} élément(s) extrait(s) n'ont pas pu être rapprochés du texte du CV. Ils sont marqués « non vérifiés » et doivent être contrôlés dans le document original."),
    (re.compile(r"^Semantic indexing failed; keyword search only\. (.*)$", re.S),
     "L'indexation sémantique a échoué ; recherche par mots-clés uniquement. {0:tr}"),
    (re.compile(r"^Only (\d+) MB of RAM is available\. Close other applications before running the AI analysis, or select a smaller model in AI settings\.$"),
     "Seulement {0} Mo de RAM disponibles. Fermez d'autres applications avant de lancer l'analyse IA, ou choisissez un modèle plus léger dans les réglages IA."),
    (re.compile(r"^The model '(.+?)' is not installed in Ollama\. Installed models: (.*)\. Select one of them in AI settings \(models are never downloaded automatically\)\.$", re.S),
     "Le modèle « {0} » n'est pas installé dans Ollama. Modèles installés : {1}. Choisissez-en un dans les réglages IA (les modèles ne sont jamais téléchargés automatiquement)."),
    (re.compile(r"^The AI endpoint '(.*)' is not a local host\. Only local inference is allowed\.$"),
     "Le point d'accès IA « {0} » n'est pas un hôte local. Seule l'inférence locale est autorisée."),
    (re.compile(r"^(.+?) '(.+?)' is not installed\. Select an installed model such as (.+?) in AI settings\.$"),
     "{0:tr} « {1} » non installé. Choisissez un modèle installé, par exemple {2}, dans les réglages IA."),
    (re.compile(r"^(.+?) '(.+?)' is not installed\. Install a model with 'ollama pull'\.$"),
     "{0:tr} « {1} » non installé. Installez un modèle avec « ollama pull »."),
    (re.compile(r"^(.+?) '(.+?)' is not installed in Ollama\. Models are never downloaded automatically\.$"),
     "{0:tr} « {1} » non installé dans Ollama. Les modèles ne sont jamais téléchargés automatiquement."),
    (re.compile(r"^Not installed: (.*)\. Models are never downloaded automatically\.$"),
     "Non installé(s) : {0}. Les modèles ne sont jamais téléchargés automatiquement."),
    (re.compile(r"^The CV '(.+)' has not been processed yet\.$", re.S), "Le CV « {0} » n'a pas encore été traité."),
]

_WORDS = {"Active model": "Modèle d'analyse", "Embedding model": "Modèle de recherche"}


def tr(msg: Any, lang: str) -> Any:
    if lang != "fr" or not isinstance(msg, str) or not msg:
        return msg
    if msg in EXACT:
        return EXACT[msg]
    for pattern, template in PATTERNS:
        m = pattern.match(msg)
        if m:
            out = template
            for i, g in enumerate(m.groups()):
                out = out.replace(f"{{{i}:tr}}", _WORDS.get(g, tr(g, lang))).replace(f"{{{i}}}", g)
            return out
    return msg


def tr_list(items: list | None, lang: str) -> list:
    return [tr(x, lang) for x in (items or [])]


def get_lang(request: Request) -> Lang:
    """FastAPI dependency: X-Lang header, then Accept-Language."""
    h = (request.headers.get("x-lang") or request.headers.get("accept-language") or "").strip().lower()
    return "fr" if h.startswith("fr") else "en"


def tr_report(report: dict, lang: str) -> dict:
    """Translate a deletion report (check names, notes, limitations)."""
    if lang != "fr":
        return report
    r = dict(report)
    r["verification"] = [{**c, "check": tr(c["check"], lang)} for c in report.get("verification", [])]
    r["limitations"] = tr_list(report.get("limitations"), lang)
    r["secure_delete"] = tr(report.get("secure_delete"), lang)
    return r


def tr_result(result: dict | None, lang: str) -> dict | None:
    """Translate the fixed texts of an analysis / interview result."""
    if lang != "fr" or not result:
        return result
    r = dict(result)
    if "disclaimer" in r:
        r["disclaimer"] = tr(r["disclaimer"], lang)
    if "criteria" in r:
        r["criteria"] = [
            {**c, "status_label": tr(c.get("status_label"), lang), "verification_notes": tr_list(c.get("verification_notes"), lang)}
            for c in r["criteria"]
        ]
    if "categories" in r:
        r["categories"] = [{**c, "label": tr(c.get("label"), lang)} for c in r["categories"]]
    return r
