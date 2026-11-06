from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.i18n import Lang, get_lang, tr
from app.models import (
    Analysis,
    Candidate,
    CandidateProfile,
    ChatMessage,
    Conversation,
    ConversationCandidate,
    JobDescription,
    LifecycleEvent,
)
from app.schemas.api import ChatRequest, CompareRequest, ConversationCreate
from app.services.analysis import build_criteria
from app.services.assistant import AssistantError, create_conversation, scope_of, stream_answer

router = APIRouter(prefix="/api", tags=["assistant"])


def _conv_out(db: Session, conv: Conversation) -> dict:
    ids = scope_of(db, conv.id)
    cands = []
    for cid in ids:
        c = db.get(Candidate, cid)
        if c:
            cands.append({"id": c.id, "label": c.display_name or c.original_filename})
    return {"id": conv.id, "title": conv.title, "job_id": conv.job_id, "created_at": conv.created_at, "candidates": cands}


@router.post("/conversations", status_code=201)
def new_conversation(body: ConversationCreate, db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    try:
        conv = create_conversation(db, body.candidate_ids, body.job_id)
    except AssistantError as e:
        raise HTTPException(400, tr(e.user_message, lang))
    return _conv_out(db, conv)


@router.get("/conversations")
def list_conversations(candidate_id: str | None = Query(None), db: Session = Depends(get_db)):
    stmt = select(Conversation).order_by(Conversation.created_at.desc()).limit(100)
    if candidate_id:
        stmt = stmt.join(ConversationCandidate).where(ConversationCandidate.candidate_id == candidate_id)
    return [_conv_out(db, c) for c in db.execute(stmt).scalars()]


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    out = _conv_out(db, conv)
    out["messages"] = [
        {"id": m.id, "role": m.role, "content": m.content, "citations": m.citations, "created_at": m.created_at}
        for m in db.execute(select(ChatMessage).where(ChatMessage.conversation_id == conv_id).order_by(ChatMessage.id)).scalars()
    ]
    return out


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, db: Session = Depends(get_db)):
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    db.delete(conv)
    db.commit()


@router.post("/conversations/{conv_id}/messages")
def post_message(conv_id: str, body: ChatRequest, db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    if db.get(Conversation, conv_id) is None:
        raise HTTPException(404, "Conversation not found")
    return StreamingResponse(stream_answer(conv_id, body.message.strip(), lang), media_type="application/x-ndjson")


# ---------------------------------------------------------------- compare
@router.post("/compare")
def compare(body: CompareRequest, db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    """Side-by-side, deterministic (no AI call, no winner, no score)."""
    job = db.get(JobDescription, body.job_id) if body.job_id else None
    if body.job_id and job is None:
        raise HTTPException(404, "Job description not found")
    columns = []
    for cid in dict.fromkeys(body.candidate_ids):
        c = db.get(Candidate, cid)
        if c is None:
            raise HTTPException(404, "Candidate not found")
        prof = db.get(CandidateProfile, cid)
        data = prof.data if prof else {}
        analysis = None
        if job:
            a = db.execute(
                select(Analysis).where(Analysis.candidate_id == cid, Analysis.job_id == job.id,
                                       Analysis.kind == "analysis", Analysis.status == "completed")
                .order_by(Analysis.created_at.desc())
            ).scalars().first()
            if a and a.result:
                analysis = {"id": a.id, "created_at": a.created_at,
                            "criteria": {cr["requirement"]: cr for cr in a.result.get("criteria", [])}}
        columns.append({
            "candidate_id": cid,
            "label": c.display_name or c.original_filename,
            "status": c.status,
            "skills": data.get("skills", []),
            "experience": data.get("experience", []),
            "projects": data.get("projects", []),
            "education": data.get("education", []),
            "certifications": data.get("certifications", []),
            "languages": data.get("languages", []),
            "analysis": analysis,
        })
    criteria = build_criteria(job) if job else []
    return {
        "job": {"id": job.id, "title": job.title} if job else None,
        "criteria": criteria,
        "columns": columns,
        "disclaimer": tr("Side-by-side view of the evidence in each CV. No overall score or winner is computed; "
                         "the comparison and the decision remain with the recruiter.", lang),
    }


# ---------------------------------------------------------------- lifecycle
@router.get("/candidates/{candidate_id}/lifecycle")
def lifecycle(candidate_id: str, db: Session = Depends(get_db)):
    if db.get(Candidate, candidate_id) is None:
        raise HTTPException(404, "Candidate not found")
    rows = db.execute(
        select(LifecycleEvent).where(LifecycleEvent.candidate_id == candidate_id).order_by(LifecycleEvent.id)
    ).scalars()
    return [{"ts": e.ts, "type": e.event_type, "details": e.details, "job_id": e.job_id} for e in rows]
