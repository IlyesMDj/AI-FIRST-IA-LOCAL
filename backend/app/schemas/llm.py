"""Schemas for LLM outputs (also sent to Ollama as JSON-schema constraints).

Strings are truncated rather than rejected, so that a slightly too long
answer does not trigger an unnecessary repair round-trip.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field


def _trunc(n: int):
    def f(v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v[:n] if v else None

    return f


def _none_if_empty(v):
    if isinstance(v, str) and v.strip().lower() in {"", "null", "none", "n/a", "unknown", "inconnu"}:
        return None
    return v


Short = Annotated[str, AfterValidator(_trunc(120))]
OptShort = Annotated[str | None, BeforeValidator(_none_if_empty), AfterValidator(_trunc(120))]
OptText = Annotated[str | None, BeforeValidator(_none_if_empty), AfterValidator(_trunc(1200))]
OptQuote = Annotated[str | None, BeforeValidator(_none_if_empty), AfterValidator(_trunc(400))]
Quote = Annotated[str, AfterValidator(_trunc(400))]

_DATE_RE = re.compile(r"^(\d{4})(?:[-/.](\d{1,2}))?$")


def _norm_date(v):
    v = _none_if_empty(v)
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"present", "current", "aujourd'hui", "actuel", "en cours", "now", "présent", "ce jour"}:
        return "present"
    m = _DATE_RE.match(s)
    if m:
        y, mo = m.group(1), m.group(2)
        return f"{y}-{int(mo):02d}" if mo and 1 <= int(mo) <= 12 else y
    m = re.search(r"(19|20)\d{2}", s)
    return m.group(0) if m else None


DateStr = Annotated[str | None, BeforeValidator(_norm_date)]


def _year(v):
    v = _none_if_empty(v)
    if v is None:
        return None
    m = re.search(r"(19|20)\d{2}", str(v))
    return int(m.group(0)) if m else None


Year = Annotated[int | None, BeforeValidator(_year)]

SkillCategory = Literal["technical", "tool", "methodology", "domain", "soft", "other"]
Basis = Literal["explicit", "inferred"]


class LLMSkill(BaseModel):
    name: Short
    category: SkillCategory = "other"
    basis: Basis = "explicit"
    evidence: OptQuote = None


class LLMExperience(BaseModel):
    position: OptShort = None
    company: OptShort = None
    description: OptText = None
    start_date: DateStr = None
    end_date: DateStr = None
    evidence: OptQuote = None


class LLMEducation(BaseModel):
    degree: OptShort = None
    field: OptShort = None
    institution: OptShort = None
    graduation_year: Year = None
    evidence: OptQuote = None


class LLMLanguage(BaseModel):
    language: Short
    level: OptShort = None
    evidence: OptQuote = None


class LLMCertification(BaseModel):
    name: Short
    issuer: OptShort = None
    year: Year = None
    evidence: OptQuote = None


class LLMProject(BaseModel):
    name: Short
    description: OptText = None
    technologies: list[Short] = Field(default_factory=list)
    evidence: OptQuote = None


class CVExtraction(BaseModel):
    candidate_name: OptShort = None
    professional_summary: OptText = None
    skills: list[LLMSkill] = Field(default_factory=list)
    experience: list[LLMExperience] = Field(default_factory=list)
    education: list[LLMEducation] = Field(default_factory=list)
    languages: list[LLMLanguage] = Field(default_factory=list)
    certifications: list[LLMCertification] = Field(default_factory=list)
    projects: list[LLMProject] = Field(default_factory=list)


AssessmentStatus = Literal["demonstrated", "partial", "not_found", "undetermined"]


class CriterionAssessment(BaseModel):
    status: AssessmentStatus
    evidence_quotes: list[Quote] = Field(default_factory=list)
    relevant_experience: OptText = None
    missing_information: OptText = None
    explanation: Annotated[str, AfterValidator(_trunc(1200))]


InterviewCategory = Literal["technical", "experience", "project", "problem_solving", "clarification"]


class InterviewQuestion(BaseModel):
    category: InterviewCategory
    question: Annotated[str, AfterValidator(_trunc(500))]
    why_relevant: Annotated[str, AfterValidator(_trunc(500))]
    competency: Short
    cv_evidence: OptQuote = None


class InterviewPlan(BaseModel):
    questions: list[InterviewQuestion] = Field(default_factory=list)
