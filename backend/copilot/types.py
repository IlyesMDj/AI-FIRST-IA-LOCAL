"""Types partagés entre modules. CONTRAT : ne pas modifier sans mettre à jour CONTRACTS.md."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["pending", "analyzing", "ready", "unsupported", "error"]
Assessment = Literal["présent", "partiel", "non trouvé"]


# --- Extraction / masquage (module A) ---------------------------------------
@dataclass
class ExtractResult:
    status: Literal["ok", "unsupported", "needs_vision"]
    text: str | None = None          # texte brut, EN MÉMOIRE SEULEMENT, jamais stocké
    reason: str | None = None        # obligatoire si status != "ok"
    page_images: list[bytes] = field(default_factory=list)  # PNG en mémoire si needs_vision


@dataclass
class RedactResult:
    text: str                        # texte masqué : SEULE version du CV stockée
    removed: dict[str, int]          # catégorie -> nombre d'occurrences masquées


# --- Critères / analyse (module B) ------------------------------------------
class Criterion(BaseModel):
    id: str = Field(pattern=r"^C\d{1,2}$")   # "C1".."C99"
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)


class Evidence(BaseModel):
    criterion_id: str
    assessment: Assessment
    quote: str | None = None          # tranche EXACTE de redacted_text (pas le texte du modèle)
    start: int | None = None
    end: int | None = None


class Analysis(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)  # prénom nom si présent dans le CV
    summary: str = Field(max_length=1200)
    evidence: list[Evidence]
    points_to_clarify: list[str] = Field(default_factory=list)
    dropped_quotes: int = 0           # citations introuvables dans le texte, écartées
    model: str
    prompt_version: int


class InterviewQuestion(BaseModel):
    question: str = Field(max_length=400)
    rationale: str = Field(max_length=400)
    criterion_id: str | None = None   # doit exister dans les critères, sinon None


# --- Effacement (module A) ----------------------------------------------------
class ErasureProof(BaseModel):
    candidate_id_hash: str            # sha256(id) — jamais l'id en clair dans le journal
    erased_at: str                    # ISO 8601 UTC
    tables: dict[str, int]            # table -> lignes restantes pour ce candidat (attendu 0)
    raw_file_hits: int                # occurrences d'extraits du CV dans les octets du .db (attendu 0)
    extracts_checked: int = 0         # nb d'extraits réellement recherchés (0 = vérif. octets impossible, à afficher)
    vacuum_ok: bool = True            # False si le VACUUM a échoué : pages libres non compactées
    verified: bool                    # True ssi tables à 0, raw_file_hits == 0, vacuum_ok, et extracts_checked > 0 si le candidat avait un document
