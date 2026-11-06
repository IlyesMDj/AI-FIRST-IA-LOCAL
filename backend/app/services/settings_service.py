"""Runtime AI settings (env defaults + persisted overrides)."""
from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting

AI_SETTINGS_KEY = "ai_settings"


class DuplicateRules(BaseModel):
    file_hash: bool = True  # always blocks identical files
    email: bool = True  # flags (never merges) profiles sharing an email
    name_and_phone: bool = True  # flags profiles sharing name + phone


class AISettings(BaseModel):
    active_model: str
    embedding_model: str
    vision_model: str
    num_ctx: int = Field(ge=2048, le=32768)
    temperature: float = Field(ge=0.0, le=1.5)
    top_p: float = Field(ge=0.05, le=1.0)
    keep_alive: str = Field(pattern=r"^(0|-1|\d+[smh])$")
    request_timeout_s: float = Field(ge=10, le=1800)
    max_repair_attempts: int = Field(ge=0, le=4)
    auto_process_on_import: bool
    ocr_enabled: bool
    keep_original_files: bool = True
    duplicate_rules: DuplicateRules = DuplicateRules()


def default_ai_settings() -> AISettings:
    s = get_settings()
    return AISettings(
        active_model=s.primary_model,
        embedding_model=s.embedding_model,
        vision_model=s.vision_model,
        num_ctx=s.num_ctx,
        temperature=s.temperature,
        top_p=s.top_p,
        keep_alive=s.keep_alive,
        request_timeout_s=s.request_timeout_s,
        max_repair_attempts=s.max_repair_attempts,
        auto_process_on_import=s.auto_process_on_import,
        ocr_enabled=s.ocr_enabled,
    )


def get_ai_settings(db: Session) -> AISettings:
    row = db.get(AppSetting, AI_SETTINGS_KEY)
    base = default_ai_settings().model_dump()
    if row and isinstance(row.value, dict):
        base.update({k: v for k, v in row.value.items() if k in base})
    try:
        return AISettings.model_validate(base)
    except Exception:
        return default_ai_settings()


def save_ai_settings(db: Session, new: AISettings) -> AISettings:
    row = db.get(AppSetting, AI_SETTINGS_KEY)
    if row is None:
        row = AppSetting(key=AI_SETTINGS_KEY, value=new.model_dump())
        db.add(row)
    else:
        row.value = new.model_dump()
    db.commit()
    return new
