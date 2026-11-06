"""Data minimisation and prompt-injection detection.

Redaction runs on the raw document text *before* it is stored or sent to any
model, so data that is not needed for recruitment (date of birth, age,
marital status, nationality, gender, religion, health, home address…) never
reaches the LLM, the database or the embeddings.

This is heuristic (regex on common FR/EN CV wording). It is documented as a
limitation: unusual phrasings may slip through; the extraction schema also has
no field for these categories, and the extraction prompt forbids them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

REDACTION_TOKEN = "[redacted:{}]"

# (category, compiled regex). Each regex matches the sensitive *span*.
_LABEL = r"(?:\s*[:\-–]\s*|\s+)"
_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "birth_date",
        re.compile(
            r"(?im)\b(?:date\s+de\s+naissance|n[ée]e?\s+le|date\s+of\s+birth|born\s+on|d\.?o\.?b\.?|birthdate)"
            + _LABEL
            + r"[^\n]{0,40}"
        ),
    ),
    (
        "age",
        re.compile(
            r"(?im)(?:\b(?:[âa]ge|age)\s*[:\-–]\s*\d{1,2}\s*(?:ans|years?)?\b|\b[âa]g[ée]e?\s+de\s+\d{1,2}\s*ans\b|\b\d{1,2}\s*years\s+old\b)"
        ),
    ),
    (
        "marital_status",
        re.compile(
            r"(?im)(?:\b(?:situation\s+(?:familiale|matrimoniale)|[ée]tat\s+civil|marital\s+status)"
            + _LABEL
            + r"[^\n]{0,40}|^\s*(?:mari[ée]e?|c[ée]libataire|divorc[ée]e?|pacs[ée]e?|veu[fv]e?|married|single|divorced)"
            r"(?:\s*,?\s*\d+\s*enfants?)?\s*$|\b\d+\s+enfants?\b)"
        ),
    ),
    (
        "nationality",
        re.compile(r"(?im)\b(?:nationalit[ée]|nationality|citizenship)" + _LABEL + r"[^\n]{0,40}"),
    ),
    (
        "gender",
        re.compile(r"(?im)\b(?:sexe|genre|gender|sex)\s*[:\-–]\s*[^\n]{0,20}"),
    ),
    (
        "religion",
        re.compile(r"(?im)\b(?:religion|confession)\s*[:\-–]\s*[^\n]{0,40}"),
    ),
    (
        "health",
        re.compile(
            r"(?im)\b(?:sant[ée]|health|handicap|disability|rqth)\s*[:\-–]\s*[^\n]{0,60}"
        ),
    ),
    (
        "social_security",
        re.compile(r"(?i)\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}(?:\s?\d{2})?\b"),
    ),
    (
        "address",
        re.compile(
            r"(?im)(?:\b(?:adresse|address)\s*[:\-–]\s*[^\n]{0,80}|\b\d{1,4}\s*(?:bis|ter)?,?\s+"
            r"(?:rue|avenue|av\.|boulevard|bd|chemin|all[ée]e|impasse|place|quai|route|cours|street|st\.|road|rd\.)"
            r"\s[^\n]{0,60})"
        ),
    ),
    (
        "photo_reference",
        re.compile(r"(?im)\b(?:photo(?:graph(?:ie|y))?)\s*[:\-–][^\n]{0,40}"),
    ),
]


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)


def redact_sensitive(text: str) -> RedactionResult:
    counts: dict[str, int] = {}
    out = text
    for category, pattern in _SENSITIVE_PATTERNS:
        out, n = pattern.subn(REDACTION_TOKEN.format(category), out)
        if n:
            counts[category] = counts.get(category, 0) + n
    return RedactionResult(out, counts)


# ------------------------------------------------------------------ contacts
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s.\-]?)?(?:\(?\d{1,4}\)?[\s.\-]?){2,5}\d{2,4}")


def find_email(text: str) -> str | None:
    m = EMAIL_RE.search(text)
    return m.group(0) if m else None


def find_phone(text: str) -> str | None:
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 9 <= len(digits) <= 15 and not re.fullmatch(r"(19|20)\d{2}(19|20)\d{2}", digits):
            return m.group(0).strip()
    return None


# ------------------------------------------------------- prompt injection
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_instructions", re.compile(r"(?i)\b(ignore|disregard|forget|oublie[zr]?|ignore[zr]?)\b.{0,40}\b(instructions?|prompts?|r[èe]gles|consignes|rules|above|pr[ée]c[ée]dent)")),
    ("role_override", re.compile(r"(?i)\b(you are now|act as|tu es (?:maintenant|d[ée]sormais)|vous [êe]tes (?:maintenant|d[ée]sormais)|new instructions|nouvelles instructions)\b")),
    ("system_prompt", re.compile(r"(?i)\b(system prompt|prompt syst[èe]me|<\|?system\|?>|\[INST\]|<<SYS>>|###\s*(?:system|instruction))")),
    ("decision_manipulation", re.compile(r"(?i)\b(recommend|hire|select|shortlist|rank|recrute[rz]?|embauche[rz]?|s[ée]lectionne[rz]?|classe[rz]?)\b.{0,30}\b(this candidate|me|ce candidat|moi)\b")),
    ("evaluation_manipulation", re.compile(r"(?i)\b(rate|score|note|[ée]value)\b.{0,30}\b(10/10|100|maximum|highest|excellent|parfait)")),
    ("hidden_ai_address", re.compile(r"(?i)\b(dear|cher|ch[èe]re)\s+(ai|ia|llm|chatgpt|assistant|model|mod[èe]le)\b")),
]


def detect_injection(text: str) -> list[dict[str, str]]:
    """Return a list of {type, excerpt}. The excerpt is short and kept only to
    explain the warning to the recruiter (it is deleted with the candidate)."""
    flags: list[dict[str, str]] = []
    for kind, pattern in _INJECTION_PATTERNS:
        for m in pattern.finditer(text):
            s = max(0, m.start() - 20)
            flags.append({"type": kind, "excerpt": text[s : m.end() + 20].replace("\n", " ")[:120]})
            break
    return flags


_DELIM_RE = re.compile(r"<{2,}|>{2,}|\[/?(?:INST|SYS)\]|<\|[^|>]{0,20}\|>", re.IGNORECASE)


def neutralise_delimiters(text: str) -> str:
    """Remove sequences that could close our document delimiters or mimic chat
    template tokens."""
    return _DELIM_RE.sub(" ", text)
