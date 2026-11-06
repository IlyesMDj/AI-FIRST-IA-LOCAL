"""Conversational assistant with candidate-isolated retrieval and citations."""
from __future__ import annotations

import json
import logging
import re
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import new_session
from app.i18n import tr
from app.llm.gateway import LLMGateway
from app.llm.ollama_client import OllamaError
from app.llm.prompts import ASSISTANT_SYSTEM, wrap_document
from app.models import Candidate, CandidateProfile, CandidateStatus, ChatMessage, Conversation, ConversationCandidate, JobDescription
from app.services import events
from app.services.settings_service import get_ai_settings
from app.services.vector_store import search

log = logging.getLogger(__name__)


class AssistantError(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.user_message = msg


def create_conversation(db: Session, candidate_ids: list[str], job_id: str | None) -> Conversation:
    ids = list(dict.fromkeys(candidate_ids))
    cands = [db.get(Candidate, i) for i in ids]
    if any(c is None for c in cands):
        raise AssistantError("Candidate not found.")
    if any(c.status != CandidateStatus.COMPLETED for c in cands):
        raise AssistantError("All candidates must have a processed CV.")
    if job_id and db.get(JobDescription, job_id) is None:
        raise AssistantError("Job description not found.")
    title = " vs ".join((c.display_name or c.original_filename)[:40] for c in cands)
    conv = Conversation(title=title[:200], job_id=job_id)
    db.add(conv)
    db.flush()
    for c in cands:
        db.add(ConversationCandidate(conversation_id=conv.id, candidate_id=c.id))
        events.record(db, "conversation_started", candidate_id=c.id, job_id=job_id)
    db.commit()
    return conv


def scope_of(db: Session, conv_id: str) -> list[str]:
    return list(
        db.execute(select(ConversationCandidate.candidate_id).where(ConversationCandidate.conversation_id == conv_id)).scalars()
    )


def _profile_digest(data: dict) -> str:
    lines = []
    if data.get("professional_summary"):
        lines.append("Summary: " + data["professional_summary"])
    skills = [s["name"] for s in data.get("skills", [])][:40]
    if skills:
        lines.append("Skills: " + ", ".join(skills))
    for e in data.get("experience", [])[:8]:
        lines.append(f"Experience: {e.get('position') or '?'} at {e.get('company') or '?'} ({e.get('start_date') or '?'} – {e.get('end_date') or '?'})")
    for e in data.get("education", [])[:4]:
        lines.append(f"Education: {e.get('degree') or '?'} – {e.get('institution') or '?'} ({e.get('graduation_year') or '?'})")
    for p in data.get("projects", [])[:5]:
        lines.append(f"Project: {p.get('name')}: {(p.get('description') or '')[:200]}")
    langs = [f"{lng['language']} ({lng.get('level') or '?'})" for lng in data.get("languages", [])]
    if langs:
        lines.append("Languages: " + ", ".join(langs))
    certs = [c["name"] for c in data.get("certifications", [])]
    if certs:
        lines.append("Certifications: " + ", ".join(certs))
    return "\n".join(lines)


_REF_RE = re.compile(r"\[(C\d+-(?:\d+|P))\]")


def build_context(db: Session, conv: Conversation, question: str, gateway: LLMGateway) -> tuple[str, dict[str, dict]]:
    ids = scope_of(db, conv.id)
    labels = {cid: f"C{i + 1}" for i, cid in enumerate(ids)}
    try:
        qvec = gateway.embed([question], prefix="search_query: ")[0]
    except OllamaError:
        qvec = None  # keyword fallback
    hits = search(db, ids, question, qvec, top_k=6, per_candidate=4 if len(ids) > 1 else None)
    refs: dict[str, dict] = {}
    blocks = []
    for cid in ids:
        cand = db.get(Candidate, cid)
        prof = db.get(CandidateProfile, cid)
        lab = labels[cid]
        name = cand.display_name or cand.original_filename
        parts = []
        if prof:
            ref = f"{lab}-P"
            refs[ref] = {"ref": ref, "candidate_id": cid, "candidate_label": name, "section": "extracted profile", "text": None}
            parts.append(f"[{ref}] Extracted profile:\n{_profile_digest(prof.data)}")
        for h in [h for h in hits if h.candidate_id == cid]:
            ref = f"{lab}-{h.ordinal}"
            refs[ref] = {"ref": ref, "candidate_id": cid, "candidate_label": name, "section": h.section,
                         "text": h.text[:500], "start": h.start, "end": h.end}
            parts.append(f"[{ref}] CV excerpt (section: {h.section}):\n{h.text}")
        blocks.append(f"Candidate {lab}: {name}\n" + wrap_document("\n\n".join(parts), f"CV_EXCERPTS_{lab}"))
    return "\n\n".join(blocks), refs


def stream_answer(conv_id: str, question: str, lang: str = "en") -> Iterator[str]:
    """Yields NDJSON lines. Runs with its own DB session (streaming response)."""
    db = new_session()
    try:
        conv = db.get(Conversation, conv_id)
        if conv is None:
            yield json.dumps({"type": "error", "message": tr("Conversation not found.", lang)}) + "\n"
            return
        ai = get_ai_settings(db)
        gateway = LLMGateway(ai)
        history = db.execute(
            select(ChatMessage).where(ChatMessage.conversation_id == conv_id).order_by(ChatMessage.id.desc()).limit(6)
        ).scalars().all()[::-1]
        db.add(ChatMessage(conversation_id=conv_id, role="user", content=question))
        db.commit()
        try:
            context, refs = build_context(db, conv, question, gateway)
            job_txt = ""
            if conv.job_id:
                job = db.get(JobDescription, conv.job_id)
                if job:
                    job_txt = (
                        f"\n\nJob description in scope (trusted): {job.title}\nRequired skills: {', '.join(job.required_skills)}\n"
                        f"Optional skills: {', '.join(job.optional_skills)}\nExperience: {job.experience_requirements}\n"
                    )
            messages = [{"role": "system", "content": ASSISTANT_SYSTEM}]
            for m in history:
                messages.append({"role": m.role, "content": m.content[:2000]})
            messages.append({
                "role": "user",
                "content": f"Candidates in scope and their excerpts:\n\n{context}{job_txt}\n\nRecruiter question: {question}",
            })
            yield json.dumps({"type": "sources", "sources": list(refs.values())}) + "\n"
            answer = []
            for piece in gateway.stream_chat(messages):
                answer.append(piece)
                yield json.dumps({"type": "token", "text": piece}) + "\n"
            text = "".join(answer).strip() or tr("No answer was produced.", lang)
            used = [refs[r] for r in dict.fromkeys(_REF_RE.findall(text)) if r in refs]
            if db.get(Conversation, conv_id) is not None:  # not deleted meanwhile
                db.add(ChatMessage(conversation_id=conv_id, role="assistant", content=text, citations=used))
                db.commit()
            yield json.dumps({"type": "done", "citations": used}) + "\n"
        except OllamaError as e:
            db.rollback()
            yield json.dumps({"type": "error", "message": tr(e.user_message, lang)}) + "\n"
        except Exception:  # noqa: BLE001
            log.exception("assistant failed conv=%s", conv_id)
            db.rollback()
            yield json.dumps({"type": "error", "message": tr("Unexpected error while answering.", lang)}) + "\n"
    finally:
        db.close()
