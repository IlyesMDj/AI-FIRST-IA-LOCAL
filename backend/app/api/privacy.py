from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.i18n import Lang, get_lang, tr
from app.models import (
    Analysis,
    Candidate,
    CandidateProfile,
    CandidateText,
    ChatMessage,
    Chunk,
    Conversation,
    DeletionReport,
    LifecycleEvent,
)

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


def _dir_size(path) -> tuple[int, int]:
    files = [p for p in path.rglob("*") if p.is_file()] if path.exists() else []
    return len(files), sum(p.stat().st_size for p in files)


@router.get("/inventory")
def inventory(db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    """What personal data is stored, where, and how much."""
    s = get_settings()

    def n(model, *where) -> int:
        stmt = select(func.count()).select_from(model)
        for w in where:
            stmt = stmt.where(w)
        return int(db.execute(stmt).scalar() or 0)

    up_files, up_bytes = _dir_size(s.uploads_dir)
    tmp_files, tmp_bytes = _dir_size(s.tmp_dir)
    db_bytes = s.db_path.stat().st_size if s.db_path.exists() else 0
    redactions: dict[str, int] = {}
    for (r,) in db.execute(select(CandidateText.redactions)).all():
        for k, v in (r or {}).items():
            redactions[k] = redactions.get(k, 0) + v
    return {
        "stores": [
            {"name": tr("Original documents", lang), "location": "data/uploads/<candidate-id>/", "items": up_files, "bytes": up_bytes},
            {"name": tr("Temporary processing files", lang), "location": "data/tmp/", "items": tmp_files, "bytes": tmp_bytes},
            {"name": tr("Database (profiles, text, vectors, analyses, chats)", lang), "location": "data/db/recruiter.sqlite3", "items": None, "bytes": db_bytes},
        ],
        "records": {
            "candidates": n(Candidate),
            "extracted_texts": n(CandidateText),
            "structured_profiles": n(CandidateProfile),
            "text_chunks": n(Chunk),
            "embeddings": n(Chunk, Chunk.embedding.is_not(None)),
            "analyses": n(Analysis, Analysis.kind == "analysis"),
            "interview_preparations": n(Analysis, Analysis.kind == "interview"),
            "conversations": n(Conversation),
            "chat_messages": n(ChatMessage),
            "lifecycle_events": n(LifecycleEvent),
            "deletion_reports": n(DeletionReport),
        },
        "redactions_applied": redactions,
        "network": {
            "inference_endpoint": s.ollama_url,
            "allowed_inference_hosts": s.allowed_ollama_hosts,
            "telemetry": tr("none", lang),
            "external_calls": tr("none (the backend only calls the local Ollama endpoint)", lang),
        },
    }
