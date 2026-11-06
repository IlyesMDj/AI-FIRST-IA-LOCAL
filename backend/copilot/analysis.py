"""Analyse d'un CV masqué au regard des critères + ancrage des citations dans le texte.

Enveloppe stricte, items souples : la structure globale de la sortie du modèle est validée (1 retry puis
LLMError) ; un item de preuve invalide est simplement écarté. Jamais de score global ni de rang.

Arbitrage « présent » : exige une citation ancrée, non faible. Sinon l'évaluation devient « partiel »
(le front l'affiche « non étayé » quand il n'y a pas de citation).

Limite connue : une citation qui contient une négation (« jamais pratiqué Python ») est ancrée comme les autres ;
le prompt demande de citer le passage qui PROUVE, mais le code ne vérifie pas le sens.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, ValidationError

from . import llm, prompts
from .assist import contains_verdict
from .config import MODELS
from .types import Analysis, Criterion, Evidence

ANALYSIS_TIMEOUT_S = llm.JSON_TIMEOUT_S  # 300 s : défaut de chat_json (worker mono-thread)
SUMMARY_REJECTED = "Résumé indisponible (formulation évaluative rejetée)"

# --- Ancrage --------------------------------------------------------------------

_CHAR_MAP = {
    # apostrophes
    "’": "'", "‘": "'", "‛": "'", "ʼ": "'", "´": "'", "`": "'", "′": "'",
    # guillemets
    "“": '"', "”": '"', "„": '"', "‟": '"', "«": '"', "»": '"',
    "‹": '"', "›": '"', "″": '"',
    # tirets
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    "­": "",  # trait d'union conditionnel : invisible
    # ligatures (NFKC les traite aussi, explicite pour la lisibilité)
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
    "œ": "oe", "Œ": "oe", "æ": "ae", "Æ": "ae",
    # zéro-largeur
    "​": "", "‌": "", "‍": "", "⁠": "", "﻿": "",
}

_EDGE_STRIP = " \t\r\n\"'.,;:…«»“”‘’"
MIN_QUOTE_CHARS = 3
# Mentions de masquage : « [email retiré] », « [adresse retirée] », « [marqueur retiré] »…
_REDACTION_RE = re.compile(r"\[[^\[\]\n]{0,60}retir[ée]e?s?\]", re.IGNORECASE)


def _norm_char(ch: str) -> str:
    if ch in _CHAR_MAP:
        return _CHAR_MAP[ch]
    out = unicodedata.normalize("NFKC", ch)
    return "".join(_CHAR_MAP.get(c, c) for c in out).lower()


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Texte normalisé + pour chaque caractère normalisé, l'index du caractère source dans `text`."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = True  # supprime les espaces de tête
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
                prev_space = True
            continue
        if unicodedata.combining(ch) and out:
            # accent décomposé (e + ◌́) : recompose avec le caractère précédent
            composed = unicodedata.normalize("NFC", out[-1] + ch)
            if len(composed) == 1:
                out[-1] = composed
                continue
        for c in _norm_char(ch):
            if c.isspace():
                if not prev_space:
                    out.append(" ")
                    idx.append(i)
                    prev_space = True
                continue
            out.append(c)
            idx.append(i)
            prev_space = False
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def _normalize(text: str) -> str:
    return _normalize_with_map(text)[0]


def _clean_quote(quote: str) -> str:
    q = quote.strip()
    for ell in ("...", "…"):
        while q.startswith(ell):
            q = q[len(ell):].lstrip()
        while q.endswith(ell):
            q = q[: -len(ell)].rstrip()
    return q.strip(_EDGE_STRIP)


def _overlaps_redaction(text: str, start: int, end: int) -> bool:
    return any(m.start() < end and start < m.end() for m in _REDACTION_RE.finditer(text))


def anchor(quote: str, text: str) -> tuple[int, int] | None:
    """Position (start, end) de `quote` dans `text` (offsets du texte ORIGINAL), ou None.

    Tolérance : casse, espaces/sauts de ligne multiples, apostrophes et guillemets typographiques, ligatures,
    tirets, accents décomposés, ponctuation/ellipse en bordure de citation. Aucune correspondance approximative.
    Refus : frontière de mot non respectée (« SQL » dans « NoSQL »), début/fin au milieu d'une ligature,
    tranche qui touche une mention « [… retiré(e)] ». Première occurrence valide retenue.
    """
    if not quote or not text:
        return None
    nq = _normalize(_clean_quote(quote))
    if len(nq) < MIN_QUOTE_CHARS:
        return None
    nt, idx = _normalize_with_map(text)
    n = len(nq)
    pos = nt.find(nq)
    while pos >= 0:
        e = pos + n  # fin exclusive dans le texte normalisé
        ok = True
        if pos > 0 and (nq[0].isalnum() and nt[pos - 1].isalnum() or idx[pos - 1] == idx[pos]):
            ok = False
        if ok and e < len(nt) and (nq[-1].isalnum() and nt[e].isalnum() or idx[e] == idx[e - 1]):
            ok = False
        if ok:
            start = idx[pos]
            end = idx[e - 1] + 1
            while end < len(text) and unicodedata.combining(text[end]):
                end += 1  # inclut un accent décomposé final
            if not _overlaps_redaction(text, start, end):
                return start, end
        pos = nt.find(nq, pos + 1)
    return None


def is_weak_quote(quote: str) -> bool:
    """Citation trop faible pour étayer « présent » : moins de 2 mots ET moins de 12 caractères."""
    q = _clean_quote(quote or "")
    return len(re.findall(r"\w+", q)) < 2 and len(q) < 12


# --- Sortie brute du modèle ------------------------------------------------------

class RawEvidence(BaseModel):
    criterion_id: str = Field(max_length=4)
    quote: str | None = Field(default=None, max_length=200)
    assessment: Literal["présent", "partiel", "non trouvé"]


class RawAnalysis(BaseModel):
    """Schéma envoyé au modèle (format=). Petit : la génération est lente sur CPU."""
    display_name: str | None = Field(default=None, max_length=80)
    summary: str = Field(max_length=500)
    evidence: list[RawEvidence] = Field(max_length=12)
    points_to_clarify: list[Annotated[str, Field(max_length=160)]] = Field(default_factory=list, max_length=4)


class _Envelope(BaseModel):
    """Validation stricte de l'enveloppe seule ; les items sont validés un par un ensuite."""
    display_name: Any = None
    summary: str
    evidence: list[Any]
    points_to_clarify: list[Any] = Field(default_factory=list)


def _inline_refs(schema: dict) -> dict:
    """Remplace les $ref/$defs par leur contenu (schéma autonome, plus simple pour Ollama)."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k not in ("$defs", "title", "description")}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def raw_schema(criteria: list[Criterion] | None = None) -> dict:
    schema = _inline_refs(RawAnalysis.model_json_schema())
    if criteria:
        item = schema["properties"]["evidence"]["items"]
        item["properties"]["criterion_id"] = {"type": "string", "enum": [c.id for c in criteria]}
        schema["properties"]["evidence"]["maxItems"] = len(criteria)
    return schema


def _model_label(model_key: str) -> str:
    return MODELS.get(model_key, model_key)


def _call_with_retry(system: str, user: str, schema: dict, model_key: str) -> _Envelope:
    for _ in range(2):  # 1 essai + 1 retry
        try:
            raw = llm.chat_json(model_key, system, user, schema)
            return _Envelope.model_validate(raw)
        except (llm.LLMOutputError, ValidationError):
            continue
    # `from None` : ne pas chaîner une ValidationError dont le message contient la sortie (donc du CV).
    raise llm.LLMError("sortie du modèle invalide après 1 retry") from None


# --- Nom affiché ------------------------------------------------------------------

_NAME_TOKEN_RE = re.compile(r"[^\W\d_][^\W\d_'’-]*(?:['’-][^\W\d_]+)*")
_NOT_A_NAME = {
    "curriculum", "vitae", "cv", "profil", "resume", "développeur", "développeuse", "developpeur", "developer",
    "ingénieur", "ingénieure", "engineer", "chef", "manager", "consultant", "consultante", "stagiaire", "data",
    "web", "full", "stack", "back", "front", "end", "senior", "junior", "analyste", "technicien", "technicienne",
    "assistant", "assistante", "responsable", "directeur", "directrice", "designer", "projet", "python",
    "expérience", "experience", "formation", "compétences", "contact",
}


def _name_from_header(text: str) -> str | None:
    """Repli si le modèle ne rend pas de nom : 1re ligne non vide du CV si elle ressemble à « Prénom Nom »."""
    for line in text.splitlines()[:5]:
        s = line.strip()
        if not s:
            continue
        words = s.split()
        if not 2 <= len(words) <= 4 or "[" in s:
            return None
        if all(_NAME_TOKEN_RE.fullmatch(w) and w[0].isupper() and w.lower() not in _NOT_A_NAME for w in words):
            return " ".join(words)[:80]
        return None
    return None


def _clean_display_name(value: Any, text: str) -> str | None:
    """Nom conservé seulement s'il figure réellement dans le CV (évite un nom inventé ou injecté).

    1) nom complet ancré ; 2) sinon chaque mot du nom retrouvé (mot entier) dans l'en-tête du CV, quel que soit
    l'ordre (« BELKACEM Yanis ») ; 3) sinon, 1re ligne du CV si elle a la forme « Prénom Nom ».
    """
    if isinstance(value, str):
        name = " ".join(value.split())[:80]
        if len(name) >= 3 and "retir" not in name.lower():
            span = anchor(name, text)
            if span is not None:
                return " ".join(text[span[0]:span[1]].split())[:80] or None
            tokens = _NAME_TOKEN_RE.findall(name)
            head = text[:600]
            if 2 <= len(tokens) <= 4:
                spans = [anchor(t, head) for t in tokens]
                if all(spans):
                    return " ".join(head[s:e] for s, e in spans)[:80]  # type: ignore[misc]
    return _name_from_header(text)


# --- Construction de l'analyse -----------------------------------------------------

def build_analysis(env: _Envelope, redacted_text: str, criteria: list[Criterion], model_key: str,
                   summary_override: str | None = None) -> Analysis:
    valid_ids = [c.id for c in criteria]
    by_id: dict[str, RawEvidence] = {}
    for item in env.evidence:
        try:
            ev = RawEvidence.model_validate(item)
        except ValidationError:
            continue  # item invalide écarté, l'analyse continue
        cid = ev.criterion_id.strip().upper()
        if cid not in valid_ids or cid in by_id:
            continue
        by_id[cid] = ev

    evidence: list[Evidence] = []
    dropped = 0
    for cid in valid_ids:
        ev = by_id.get(cid)
        if ev is None:
            evidence.append(Evidence(criterion_id=cid, assessment="non trouvé"))
            continue
        assessment = ev.assessment
        quote = start = end = None
        if assessment != "non trouvé" and ev.quote and ev.quote.strip():
            span = anchor(ev.quote, redacted_text)
            if span is None:
                dropped += 1
            else:
                start, end = span
                quote = redacted_text[start:end]
        # Arbitrage : « présent » exige une citation ancrée et non faible.
        if assessment == "présent" and (quote is None or is_weak_quote(quote)):
            assessment = "partiel"
        evidence.append(Evidence(criterion_id=cid, assessment=assessment, quote=quote, start=start, end=end))

    points = [" ".join(p.split())[:300] for p in env.points_to_clarify
              if isinstance(p, str) and p.strip() and not contains_verdict(p)][:6]
    summary = summary_override or " ".join(env.summary.split())[:1200]
    return Analysis(
        display_name=_clean_display_name(env.display_name, redacted_text),
        summary=summary,
        evidence=evidence,
        points_to_clarify=points,
        dropped_quotes=dropped,
        model=_model_label(model_key),
        prompt_version=prompts.PROMPT_VERSION,
    )


def analyze(redacted_text: str, criteria: list[Criterion], model_key: str) -> Analysis:
    """1 appel LLM (+1 retry si enveloppe invalide, +1 si le résumé est évaluatif). 1 Evidence par critère.

    ContextTooLongError (LLMError) si le CV ne tient pas dans le contexte : jamais d'analyse partielle.
    """
    if not criteria:
        raise ValueError("aucun critère")
    llm.check_cv_fits(redacted_text, prompts.ANALYSIS_SYSTEM + prompts.analysis_user("", criteria))
    user = prompts.analysis_user(redacted_text, criteria)
    schema = raw_schema(criteria)
    env = _call_with_retry(prompts.ANALYSIS_SYSTEM, user, schema, model_key)
    override = None
    if contains_verdict(env.summary):
        env = _call_with_retry(prompts.ANALYSIS_SYSTEM, user, schema, model_key)
        if contains_verdict(env.summary):
            override = SUMMARY_REJECTED
    return build_analysis(env, redacted_text, criteria, model_key, summary_override=override)
