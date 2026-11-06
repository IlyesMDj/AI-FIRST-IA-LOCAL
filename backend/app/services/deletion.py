"""Candidate deletion with verification report.

Steps
1. One DB transaction deletes every row linked to the candidate (explicit
   deletes, plus ON DELETE CASCADE as a safety net): conversations that
   involved the candidate (with all their messages), analyses & interview
   preparations, chunks + embeddings, extracted text, structured profile,
   lifecycle events, the candidate row.
2. WAL checkpoint (TRUNCATE) so deleted pages do not linger in the WAL file;
   ``secure_delete`` zeroes freed pages inside the DB file.
3. Files: original document + temp directory are overwritten then removed.
4. Verification: every table is re-queried, files re-checked, semantic search
   and the API-level repository lookup are re-run for the candidate id.
5. A deletion report (no personal data, only the former UUID) is stored.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import checkpoint_wal
from app.models import (
    Analysis,
    Candidate,
    CandidateProfile,
    CandidateText,
    ChatMessage,
    Chunk,
    Conversation,
    ConversationCandidate,
    DeletionReport,
    LifecycleEvent,
)
from app.services import storage
from app.services.vector_store import search

log = logging.getLogger(__name__)

LIMITATIONS = [
    "Files are overwritten with zeros before removal, but on SSDs (wear levelling, TRIM) and journaling "
    "filesystems the physical blocks may persist until reused by the drive: this is not forensic erasure.",
    "Copies outside the application (e-mail attachments, Downloads folder, system or cloud backups, "
    "antivirus quarantine) are not managed by the application and must be handled separately.",
    "Ollama keeps no prompt history on disk, but model memory (KV cache) is only released when the model "
    "is unloaded or overwritten by later requests.",
]


class CandidateNotFound(Exception):
    pass


def _counts(db: Session, cid: str, conv_ids: list[str]) -> dict[str, int]:
    def c(stmt) -> int:
        return int(db.execute(stmt).scalar() or 0)

    out = {
        "candidate": c(select(func.count()).select_from(Candidate).where(Candidate.id == cid)),
        "extracted_text": c(select(func.count()).select_from(CandidateText).where(CandidateText.candidate_id == cid)),
        "structured_profile": c(select(func.count()).select_from(CandidateProfile).where(CandidateProfile.candidate_id == cid)),
        "chunks_and_embeddings": c(select(func.count()).select_from(Chunk).where(Chunk.candidate_id == cid)),
        "embeddings": c(select(func.count()).select_from(Chunk).where(Chunk.candidate_id == cid, Chunk.embedding.is_not(None))),
        "analyses_and_interview_preps": c(select(func.count()).select_from(Analysis).where(Analysis.candidate_id == cid)),
        "conversation_links": c(
            select(func.count()).select_from(ConversationCandidate).where(ConversationCandidate.candidate_id == cid)
        ),
        "lifecycle_events": c(select(func.count()).select_from(LifecycleEvent).where(LifecycleEvent.candidate_id == cid)),
    }
    if conv_ids:
        out["conversations"] = c(select(func.count()).select_from(Conversation).where(Conversation.id.in_(conv_ids)))
        out["chat_messages"] = c(
            select(func.count()).select_from(ChatMessage).where(ChatMessage.conversation_id.in_(conv_ids))
        )
    else:
        out["conversations"] = 0
        out["chat_messages"] = 0
    return out


def delete_candidate(db: Session, candidate_id: str) -> DeletionReport:
    cand = db.get(Candidate, candidate_id)
    if cand is None:
        raise CandidateNotFound(candidate_id)

    conv_ids = list(
        db.execute(
            select(ConversationCandidate.conversation_id).where(ConversationCandidate.candidate_id == candidate_id)
        ).scalars()
    )
    before = _counts(db, candidate_id, conv_ids)
    files_before = storage.candidate_files_exist(candidate_id)

    # ---- 1. database (single transaction)
    try:
        if conv_ids:
            db.execute(delete(ChatMessage).where(ChatMessage.conversation_id.in_(conv_ids)))
            db.execute(delete(ConversationCandidate).where(ConversationCandidate.conversation_id.in_(conv_ids)))
            db.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))
        db.execute(delete(Analysis).where(Analysis.candidate_id == candidate_id))
        db.execute(delete(Chunk).where(Chunk.candidate_id == candidate_id))
        db.execute(delete(CandidateText).where(CandidateText.candidate_id == candidate_id))
        db.execute(delete(CandidateProfile).where(CandidateProfile.candidate_id == candidate_id))
        db.execute(delete(LifecycleEvent).where(LifecycleEvent.candidate_id == candidate_id))
        db.execute(delete(Candidate).where(Candidate.id == candidate_id))
        db.commit()
    except Exception:
        db.rollback()
        log.exception("deletion transaction failed candidate=%s", candidate_id)
        raise
    db.expunge_all()

    # ---- 2. WAL
    wal_ok = True
    try:
        checkpoint_wal()
    except Exception:  # noqa: BLE001
        wal_ok = False

    # ---- 3. files
    file_result = storage.remove_candidate_files(candidate_id)

    # ---- 4. verification
    after = _counts(db, candidate_id, conv_ids)
    files_after = storage.candidate_files_exist(candidate_id)
    search_hits = len(search(db, [candidate_id], "experience skills", None, top_k=5))
    api_lookup = db.get(Candidate, candidate_id) is not None
    checks = [
        {"check": "Database records (all tables)", "passed": all(v == 0 for v in after.values()), "details": after},
        {"check": "Original document and temporary files", "passed": not files_after and not file_result["failed"],
         "details": {"removed": len(file_result["removed"]), "failed": file_result["failed"], "remaining": files_after}},
        {"check": "Search and semantic retrieval", "passed": search_hits == 0, "details": {"hits": search_hits}},
        {"check": "API / interface lookup", "passed": not api_lookup, "details": {"found": api_lookup}},
        {"check": "Database journal (WAL) checkpoint", "passed": wal_ok, "details": {}},
    ]
    success = all(c["passed"] for c in checks)
    report = {
        "candidate_ref": candidate_id,
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "removed": {"records": before, "files": files_before},
        "verification": checks,
        "secure_delete": "SQLite secure_delete=ON (freed pages are zeroed)",
        "limitations": LIMITATIONS,
    }
    rep = DeletionReport(candidate_ref=candidate_id, success=success, report=report)
    db.add(rep)
    db.commit()
    log.info("candidate deleted ref=%s success=%s", candidate_id, success)
    return rep
