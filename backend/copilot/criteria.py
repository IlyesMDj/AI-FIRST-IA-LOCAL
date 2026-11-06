"""Critères d'évaluation dérivés de la fiche de poste."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from . import config, llm, prompts
from .assist import fold
from .types import Criterion

DEFAULT_CRITERIA: list[Criterion] = [
    Criterion(id="C1", label="Compétences techniques clés du poste",
              description="Maîtrise des outils, langages ou méthodes cités dans la fiche de poste."),
    Criterion(id="C2", label="Expérience professionnelle pertinente",
              description="Postes ou missions comparables, durée et niveau de responsabilité."),
    Criterion(id="C3", label="Formation ou certifications",
              description="Diplômes, formations ou certifications en lien avec le poste."),
    Criterion(id="C4", label="Réalisations concrètes",
              description="Projets livrés, résultats mesurables, contributions identifiables."),
    Criterion(id="C5", label="Langues utiles au poste",
              description="Niveau dans les langues demandées par la fiche de poste."),
    Criterion(id="C6", label="Travail en équipe et transmission",
              description="Collaboration, encadrement, mentorat ou partage de connaissances attestés."),
]

# --- Critères discriminatoires ------------------------------------------------------
# Texte « replié » (minuscules, sans accents) via assist.fold. REJECT = caractéristique protégée sans ambiguïté
# (jamais proposé par suggest_criteria) ; WARN = terme ambigu (« Expérience en santé (secteur) », « jeunes
# enfants »…) : conservé mais signalé au recruteur.
_NOT_EXPERIENCE = r"(?!\s*(?:d'|de\s+)?(?:experience|pratique|anciennete|metier|carriere))"
_REJECT = [
    (r"\bage(?:e|es|s)?\b|\bages?\s+de\b|\byears old\b|\b\d+\s*yo\b", "âge"),
    (rf"\b(?:moins|plus) de \d+\s*ans\b{_NOT_EXPERIENCE}|\bentre \d+ et \d+\s*ans\b{_NOT_EXPERIENCE}"
     rf"|\b(?:under|over) \d+\b", "âge"),
    (r"\bjeunes?\b(?!\s+(?:enfants|public|publics|pousses))|\byoung\b", "âge (« jeune »)"),
    (r"\bnati(?:f|fs|ve|ves)\b|\blangue maternelle\b|\bnative speaker\b|\bmother tongue\b",
     "origine (langue maternelle / natif)"),
    (r"\bculture fit\b|\bfit culturel\b|\bfit\b", "« fit » (subjectif, source de biais)"),
    (r"\bpersonnalite\b|\bpersonality\b", "personnalité"),
    (r"\bgender\b|\bsexe\b|\bsex\b|\bmale\b|\bfemale\b", "sexe / genre"),
    (r"\bnationalit|\bcitizenship\b|\bcitoyennete\b", "nationalité"),
    (r"\borigines?\s+(?:ethnique|raciale|sociale|etrangere)|\bethni|\brace\b|\bracial", "origine"),
    (r"\breligi", "religion"),
    (r"\bsituation (?:familiale|matrimoniale)\b|\bmarital\b|\bmarie(?:e|es|s)?\b|\bcelibataire|\benceinte\b"
     r"|\bgrossesse\b|\bpregnan|\bsans enfants?\b|\bmarried\b|\bfamily status\b", "situation familiale"),
    (r"\bphotos?\b|\bapparence\b|\bappearance\b|\bphysique (?:agreable|avantageux)|\bbelle presentation\b"
     r"|\blook\b", "photo / apparence"),
    (r"\bbonne sante\b|\betat de sante\b|\bhealth status\b|\bsans handicap\b|\bpas de handicap\b", "santé / handicap"),
]
_WARN = [
    (r"\bsante\b|\bhealth\b", "santé"),
    (r"\bhandicap|\bdisabilit", "handicap"),
    (r"\bjeunes?\s+(?:enfants|public|publics|pousses)\b", "« jeune »"),
    (r"\bhommes?\b|\bfemmes?\b|\bgenre\b", "sexe / genre"),
    (r"\borigines?\b", "origine"),
    (r"\bdynamique\b", "« dynamique » (peut viser l'âge ou la personnalité)"),
    (rf"\b\d+\s*ans\b{_NOT_EXPERIENCE}", "durée en années sans lien explicite avec l'expérience (âge ?)"),
]
_REJECT_RE = [(re.compile(p), why) for p, why in _REJECT]
_WARN_RE = [(re.compile(p), why) for p, why in _WARN]
_EXPERIENCE_WORDS = re.compile(r"\b(?:experience|pratique|anciennete|en production|metier)\b")


def _criterion_issue(c: Criterion) -> tuple[str, str] | None:
    text = fold(f"{c.label} {c.description}")
    for rx, why in _REJECT_RE:
        if rx.search(text):
            return "reject", why
    for rx, why in _WARN_RE:
        if rx.search(text):
            if "annees" in why or "durée" in why:
                if _EXPERIENCE_WORDS.search(text):
                    continue  # « Python en production (4 ans et plus) » : durée d'expérience, pas un âge
            return "warn", why
    return None


def is_discriminatory(c: Criterion) -> bool:
    """Vrai si le critère vise une caractéristique protégée sans ambiguïté (rejeté par suggest_criteria)."""
    issue = _criterion_issue(c)
    return issue is not None and issue[0] == "reject"


def criterion_warning(c: Criterion) -> str | None:
    """Message en français si le critère est discriminatoire (rejet) ou ambigu (à vérifier), sinon None."""
    issue = _criterion_issue(c)
    if issue is None:
        return None
    level, why = issue
    if level == "reject":
        return f"Critère discriminatoire ({why}) : à retirer ou reformuler sur des compétences vérifiables."
    return f"À vérifier : ce critère mentionne {why} ; il doit porter sur une compétence ou une expérience utile au poste."


def load_job_text() -> tuple[str, str]:
    """(title, text) du premier fichier existant de JOB_FILE_CANDIDATES. FileNotFoundError sinon."""
    for path in config.JOB_FILE_CANDIDATES:
        if path.is_file():
            raw = path.read_bytes()
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("cp1252", errors="replace")
            return _title_of(text, path.stem), text
    raise FileNotFoundError("aucune fiche de poste trouvée")


def _title_of(text: str, fallback: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        s = s.lstrip("#").strip().strip("*_ ").strip()
        if s:
            return s[:200]
    return fallback


class RawCriterion(BaseModel):
    label: str = Field(max_length=80)
    description: str = Field(default="", max_length=200)


class RawCriteria(BaseModel):
    criteria: list[RawCriterion] = Field(min_length=4, max_length=8)


def raw_schema() -> dict:
    s = RawCriteria.model_json_schema()
    defs = s.pop("$defs", {})
    s.pop("title", None)
    item = dict(defs["RawCriterion"])
    item.pop("title", None)
    s["properties"]["criteria"]["items"] = item
    s["properties"]["criteria"].pop("title", None)
    return s


def _clean(items: list[Any]) -> list[Criterion]:
    out: list[Criterion] = []
    seen: set[str] = set()
    for it in items:
        try:
            rc = RawCriterion.model_validate(it)
        except ValidationError:
            continue
        label = " ".join(rc.label.split())[:80]
        if "_" in label and " " not in label:  # identifiant snake_case -> intitulé lisible
            label = label.replace("_", " ").strip().capitalize()
        desc = " ".join(rc.description.split())[:300]
        key = label.lower()
        if not label or key in seen or is_discriminatory(Criterion(id="C1", label=label, description=desc)):
            continue
        seen.add(key)
        out.append(Criterion(id=f"C{len(out) + 1}", label=label, description=desc))
        if len(out) == 8:
            break
    return out


def suggest_criteria(job_text: str, model_key: str) -> list[Criterion]:
    """4 à 8 critères (ids C1..Cn). 1 retry si sortie inexploitable, puis LLMError."""
    last: Exception | None = None
    for _ in range(2):
        try:
            raw = llm.chat_json(model_key, prompts.CRITERIA_SYSTEM, prompts.criteria_user(job_text), raw_schema())
        except llm.LLMOutputError as e:
            last = e
            continue
        items = raw.get("criteria")
        if isinstance(items, list):
            crits = _clean(items)
            if len(crits) >= 4:
                return crits
        last = ValueError("moins de 4 critères exploitables")
    raise llm.LLMError("critères : sortie du modèle inexploitable après 1 retry") from None
