"""Aide à l'entretien : questions proposées et Q&A en streaming sur UN CV. Jamais de décision.

Garde-fous « pas de verdict » en 3 couches pour le Q&A :
  (a) filtre d'entrée `is_decision_request` (FR + EN, tolérant aux fautes courantes) ;
  (b) consigne dans le prompt (prompts.ANSWER_SYSTEM) ;
  (c) filtre de sortie en streaming (`contains_verdict` / `starts_with_bare_yes_no`) qui coupe le flux.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from . import llm, prompts
from .types import Analysis, Criterion, InterviewQuestion

MIN_QUESTIONS, MAX_QUESTIONS = 5, 8


# --- Garde-fous (fonctions pures) -------------------------------------------------

def fold(text: str) -> str:
    """minuscules, sans accents, apostrophes droites, espaces simples (pour les filtres seulement)."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    return " ".join(t.lower().split())


_DECISION_PATTERNS = [
    # FR — embaucher / recruter / sélectionner (sauf passif factuel « a été embauché chez X »)
    r"(?<!ete )\bembauch", r"(?<!ete )\brecrut(?:er|e|es|ez|erais|erait|eriez|erions)\b",
    r"\b(?:le|la|l'|les|lui)\s*(?:prend|prends|prendre|prendrais|prendriez|prendrait|garde|gardes|gardez|garder|"
    r"garderais|garderiez|convoque|convoques|convoquez|convoquer|convoquerais|retiens|retient|retenez|retenir|"
    r"retiendrais|choisis|choisir|choisirais|selectionne|selectionner|ecarte|ecarter|elimine|eliminer|"
    r"recale|recaler|rejette|rejeter|embauche)\b",
    r"\b(?:lequel|laquelle|lesquels|lesquelles|qui)\b.{0,40}\b(?:prendr|choisi|retien|retenir|garder|embauch|"
    r"recrut|convoqu|privilegi|selectionn)",
    r"\ba retenir\b", r"\bretenir\b", r"\bshortlist", r"\bpresélection|\bpreselection",
    r"\brecomm?[ae]nd", r"\bconseill(?:es|ez|erais)\b",
    r"\bclass(?:er|ez|erais|e[- ]les|e[- ]le|e[- ]la|es[- ]les)\b", r"\bdepartag",
    r"\brank(?:e|er|ez|es|s)?\b", r"\branke[- ]les\b",
    r"\bmei?ll?i?eu?re?s?\b", r"\btop\s*\d+\b(?!\s*%)",
    r"\bnot(?:e|er|es|ez)[- ](?:le|la|les|l')\b", r"\b(?:donne|donner|mets|mettre|attribue|attribuer)\w*\s+"
    r"(?:lui\s+)?(?:une\s+)?(?:note|score)\b", r"\bquel(?:le)?\s+(?:note|score)\s+(?:lui|tu|vous|donner|mettre|"
    r"donnerais|mettrais|attribuer)\b",
    r"\b\d+(?:[.,]\d+)?\s*/\s*(?:5|10|20|100)\b", r"\bsur\s+(?:5|10|20|100)\b(?!\s*(?:ans|mois|%|personnes))",
    r"\bde\s+[01]\s+a\s+(?:5|10|20|100)\b", r"\bapprecia(?:tion)?\b", r"\bevalue[rz]?[- ](?:le|la|les)\b",
    r"\bscor(?:e|er)[- ](?:le|la|les)\b",
    r"\bbon(?:ne)?s?\s+(?:candidat|candidate|profil|choix|recrue|fit)\b",
    r"\bmauvais(?:e)?\s+(?:candidat|profil|choix)\b", r"\bideal", r"\bmerite", r"\bconvient\b",
    r"\ba la hauteur\b", r"\ble plus adapte\b", r"\bfait[- ]il l'affaire\b", r"\bvaut[- ]il\b",
    r"\bfaut[- ]il\s+(?:le|la|l')", r"\bcompar\w*\b.{0,30}\bcandidat",
    # EN
    r"\bhire\b", r"\bhiring\b", r"\bhired?\s+(?:him|her|them)\b", r"\brecruit\b", r"\bshould i (?:take|pick|choose|keep|"
    r"select|interview|reject)\b", r"\bwould you (?:take|hire|pick|choose|keep|select|recommend)\b",
    r"\b(?:good|bad|great|right|best|strong|perfect|ideal)\s+(?:fit|candidate|hire|match|choice|pick)\b",
    r"\bfit for\b", r"\bculture fit\b", r"\bpick (?:him|her|them|one)\b", r"\bwhich one\b", r"\bwho should\b",
    r"\brate (?:him|her|them|this|the)\b", r"\brating\b", r"\bbest\b", r"\breject\b",
    r"\bworth (?:hiring|interviewing)\b", r"\bgo with\b",
]
_DECISION_RE = re.compile("|".join(f"(?:{p})" for p in _DECISION_PATTERNS))


def is_decision_request(question: str) -> bool:
    """Vrai si la question demande d'embaucher, sélectionner, classer, noter, comparer ou recommander."""
    return bool(_DECISION_RE.search(fold(question)))


_VERDICT_PATTERNS = [
    r"\ba retenir\b", r"\ba recruter\b", r"\ba embaucher\b", r"\ba convoquer\b", r"\ba ecarter\b", r"\ba rejeter\b",
    r"\bje\s+(?:le\s+|la\s+|vous\s+|l')?recommande\b", r"\b(?:fortement|vivement|chaudement)\s+recommande",
    r"\brecommande(?:e)?\s+pour\s+(?:le|ce)\s+poste\b",
    r"\bmei?ll?i?eu?re?s?\s+(?:candidat|candidate|profil|choix|option)\b",
    r"\b(?:candidat|candidate|profil)\s+(?:ideal|parfait|exceptionnel|excellent|idoine)\b",
    r"\bje\s+(?:l'|le\s+|la\s+)?(?:embaucherais|recruterais|prendrais|retiendrais|garderais|choisirais)\b",
    r"\b\d+(?:[.,]\d+)?\s*/\s*(?:5|10|20|100)\b", r"\bnote\s+(?:de\s+|globale\s+|finale\s+)?\d",
    r"\bscore\s+(?:de\s+|global\s+|final\s+)?\d",
    r"\ba (?:recruter|convoquer|rencontrer|embaucher) en priorite\b", r"\bbon fit\b",
    r"\b(?:should|would|must)\s+(?:definitely\s+|certainly\s+)?(?:hire|recommend|be hired)\b",
    r"\bi (?:would )?recommend\b", r"\b(?:strong|perfect|ideal|great|good|best)\s+(?:candidate|hire|fit)\b",
    r"\bhire (?:him|her|them)\b",
]
_VERDICT_RE = re.compile("|".join(f"(?:{p})" for p in _VERDICT_PATTERNS))
VERDICT_MAX_LEN = 60  # longueur max d'une expression de verdict (tampon de retenue en streaming)

_BARE_YES_NO_RE = re.compile(r"^[\W_]*(?:oui|non|yes|no|nope|absolument|certainement)\s*(?:$|[.!?(]|\.\.\.)")


def contains_verdict(text: str) -> bool:
    """Vrai si le texte contient un avis de sélection : « à retenir », « je recommande », note x/10…"""
    return bool(_VERDICT_RE.search(fold(text)))


def starts_with_bare_yes_no(text: str) -> bool:
    """Vrai si la réponse commence par un oui/non isolé (« Non. », « Oui ! », « Non (… »)."""
    return bool(_BARE_YES_NO_RE.match(fold(text)))


# --- Questions d'entretien ---------------------------------------------------------

class RawQuestion(BaseModel):
    criterion_id: str | None = Field(default=None, max_length=4)
    question: str = Field(max_length=250)
    rationale: str = Field(max_length=180)


class RawQuestions(BaseModel):
    questions: list[RawQuestion] = Field(min_length=MIN_QUESTIONS, max_length=MAX_QUESTIONS)


def raw_schema(criteria: list[Criterion] | None = None) -> dict:
    s = RawQuestions.model_json_schema()
    defs = s.pop("$defs", {})
    s.pop("title", None)
    item = dict(defs["RawQuestion"])
    item.pop("title", None)
    item["properties"] = {k: {kk: vv for kk, vv in v.items() if kk != "title"} for k, v in item["properties"].items()}
    if criteria:
        item["properties"]["criterion_id"] = {"anyOf": [{"type": "string", "enum": [c.id for c in criteria]},
                                                        {"type": "null"}]}
    s["properties"]["questions"]["items"] = item
    s["properties"]["questions"].pop("title", None)
    return s


def _evidence_lines(analysis: Analysis, criteria: list[Criterion]) -> str:
    by_id = {e.criterion_id: e for e in analysis.evidence}
    lines = []
    for c in criteria:
        e = by_id.get(c.id)
        assessment = e.assessment if e else "non trouvé"
        quote = f" (« {e.quote} »)" if e and e.quote else ""
        lines.append(f"- {c.id} {c.label} : {assessment}{quote}")
    return "\n".join(lines)


def _clean_questions(items: list[Any], valid_ids: set[str]) -> list[InterviewQuestion]:
    out: list[InterviewQuestion] = []
    seen: set[str] = set()
    for it in items:
        try:
            rq = RawQuestion.model_validate(it)
        except ValidationError:
            continue
        q = " ".join(rq.question.split())[:400]
        r = " ".join(rq.rationale.split())[:400]
        if not q or q.lower() in seen or contains_verdict(q) or contains_verdict(r):
            continue  # doublon ou formulation évaluative : écarté
        seen.add(q.lower())
        cid = rq.criterion_id.strip().upper() if rq.criterion_id else None
        out.append(InterviewQuestion(question=q, rationale=r, criterion_id=cid if cid in valid_ids else None))
        if len(out) == MAX_QUESTIONS:
            break
    return out


def interview_questions(redacted_text: str, analysis: Analysis, criteria: list[Criterion],
                        model_key: str) -> list[InterviewQuestion]:
    """5 à 8 questions, en priorité sur les critères « partiel » / « non trouvé » et les points à clarifier.

    Si moins de 5 questions valides : 1 retry ; ensuite on rend ce qu'on a (≥ 1), sinon LLMError.
    """
    lines = _evidence_lines(analysis, criteria)
    llm.check_cv_fits(redacted_text, prompts.QUESTIONS_SYSTEM
                      + prompts.questions_user("", criteria, lines, analysis.points_to_clarify))
    user = prompts.questions_user(redacted_text, criteria, lines, analysis.points_to_clarify)
    valid_ids = {c.id for c in criteria}
    best: list[InterviewQuestion] = []
    for _ in range(2):
        try:
            raw = llm.chat_json(model_key, prompts.QUESTIONS_SYSTEM, user, raw_schema(criteria))
        except llm.LLMOutputError:
            continue
        items = raw.get("questions")
        qs = _clean_questions(items, valid_ids) if isinstance(items, list) else []
        if len(qs) > len(best):
            best = qs
        if len(best) >= MIN_QUESTIONS:
            return best
    if best:
        return best
    raise llm.LLMError("questions : sortie du modèle inexploitable après 1 retry") from None


# --- Q&A en streaming ---------------------------------------------------------------

_HEAD_CHARS = 40  # on retient le début de la réponse pour détecter un « Non. » isolé


def _guard_stream(tokens: Iterator[str]) -> Iterator[str]:
    """Filtre de sortie : retient un petit tampon pour couper le flux AVANT d'émettre un verdict."""
    buf = ""        # texte reçu mais pas encore émis
    emitted = ""    # texte déjà émis (pour détecter un verdict à cheval sur la frontière)
    head_checked = False
    for tok in tokens:
        buf += tok
        if not head_checked:
            if len(buf) < _HEAD_CHARS:
                continue
            head_checked = True
            if starts_with_bare_yes_no(buf):
                yield prompts.VERDICT_CUT_MESSAGE.lstrip()
                return
        if contains_verdict(emitted[-VERDICT_MAX_LEN:] + buf):
            yield prompts.VERDICT_CUT_MESSAGE
            return
        if len(buf) > VERDICT_MAX_LEN:
            out, buf = buf[:-VERDICT_MAX_LEN], buf[-VERDICT_MAX_LEN:]
            emitted += out
            yield out
    if not head_checked and starts_with_bare_yes_no(buf):
        yield prompts.VERDICT_CUT_MESSAGE.lstrip()
        return
    if contains_verdict(emitted[-VERDICT_MAX_LEN:] + buf):
        yield prompts.VERDICT_CUT_MESSAGE
        return
    if buf:
        yield buf


def answer_stream(redacted_text: str, question: str, model_key: str) -> Iterator[str]:
    """Répond UNIQUEMENT à partir du CV fourni ; refuse de recommander / classer / noter / décider."""
    question = (question or "").strip()[:1000]
    if not question:
        yield "Posez une question sur ce CV."
        return
    llm.check_cv_fits(redacted_text, prompts.ANSWER_SYSTEM + prompts.answer_user("", question))
    if is_decision_request(question):
        yield prompts.DECISION_REFUSAL
        question = prompts.FACTUAL_FALLBACK_QUESTION
    tokens = llm.chat_stream(model_key, prompts.ANSWER_SYSTEM, prompts.answer_user(redacted_text, question))
    yield from _guard_stream(tokens)
