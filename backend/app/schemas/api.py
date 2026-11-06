"""API request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CandidateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    display_name: str | None
    email: str | None
    status: str
    processing_step: str | None
    error_message: str | None
    original_filename: str
    file_type: str
    file_size: int
    ocr_used: bool
    has_warnings: bool = False
    confidence: float | None = None
    created_at: datetime
    processed_at: datetime | None


class CandidateDetail(CandidateSummary):
    phone: str | None
    page_count: int | None
    injection_flags: list[dict]
    warnings: list[str]
    possible_duplicates: list[dict]
    profile: dict | None = None
    text_method: str | None = None
    redactions: dict | None = None


def _clean_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = [x for x in v.replace(";", "\n").split("\n")]
    return [str(x).strip()[:300] for x in v if str(x).strip()][:40]


class JobIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=10000)
    required_skills: list[str] = Field(default_factory=list)
    optional_skills: list[str] = Field(default_factory=list)
    experience_requirements: str = Field(default="", max_length=1000)
    education_requirements: str = Field(default="", max_length=1000)
    languages: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list)

    _v = field_validator("required_skills", "optional_skills", "languages", "responsibilities", "criteria", mode="before")(
        _clean_list
    )

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class JobOut(JobIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    updated_at: datetime


class AnalysisRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=50)
    job_id: str


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    candidate_id: str
    job_id: str
    kind: str
    status: str
    progress: int
    result: dict | None
    model: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    candidate_name: str | None = None
    job_title: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ConversationCreate(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=4)
    job_id: str | None = None


class CompareRequest(BaseModel):
    candidate_ids: list[str] = Field(min_length=2, max_length=4)
    job_id: str | None = None
