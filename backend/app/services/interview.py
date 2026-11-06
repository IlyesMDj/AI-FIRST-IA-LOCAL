"""Interview preparation (stored as an Analysis row with kind='interview')."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.gateway import LLMGateway
from app.llm.ollama_client import OllamaError
from app.llm.prompts import PROMPT_VERSION, interview_messages
from app.models import Analysis
from app.services import events
from app.services.analysis import _load, job_context
from app.services.candidates import max_chars_for_ctx
from app.services.documents import section_at
from app.services.evidence import find_quote, normalise
from app.services.settings_service import get_ai_settings
from app.models import CandidateStatus

log = logging.getLogger(__name__)

CATEGORY_LABELS = {
    "technical": "Technical questions",
    "experience": "Experience questions",
    "project": "Project questions",
    "problem_solving": "Problem-solving questions",
    "clarification": "Questions to clarify CV information",
}

# Last-resort guard against discriminatory questions slipping through.
_FORBIDDEN_Q = re.compile(
    r"(?i)\b(âge|age|how old|enfants?|children|kids|enceinte|pregnan|mari[ée]|married|wife|husband|"
    r"religio|origine|origin|nationalit|santé|health|handicap|disabilit|syndica|union member|politi)"
)


def _gaps_from_analysis(db: Session, candidate_id: str, job_id: str) -> str:
    a = db.execute(
        select(Analysis)
        .where(Analysis.candidate_id == candidate_id, Analysis.job_id == job_id,
               Analysis.kind == "analysis", Analysis.status == "completed")
        .order_by(Analysis.created_at.desc())
    ).scalars().first()
    if not a or not a.result:
        return ""
    lines = []
    for c in a.result.get("criteria", []):
        if c["status"] != "demonstrated":
            line = f"- {c['requirement']}: {c['status_label']}"
            if c.get("missing_information"):
                line += f" ({c['missing_information']})"
            lines.append(line)
    return "\n".join(lines[:12])


def run_interview(db: Session, analysis_id: str, gateway: LLMGateway | None = None) -> None:
    a, cand, job, trow = _load(db, analysis_id)
    if a is None:
        return
    if cand is None or job is None or trow is None or cand.status != CandidateStatus.COMPLETED:
        a.status, a.error_message = "failed", "The candidate's CV has not been processed yet."
        db.commit()
        return
    ai = get_ai_settings(db)
    gateway = gateway or LLMGateway(ai)
    a.status, a.progress = "processing", 10
    db.commit()
    try:
        from app.schemas.llm import InterviewPlan

        text = trow.text[: max_chars_for_ctx(ai.num_ctx)]
        gaps = _gaps_from_analysis(db, a.candidate_id, a.job_id)
        plan, meta = gateway.generate_structured(InterviewPlan, interview_messages(text, job_context(job), gaps), num_predict=3000)
        src = normalise(trow.text)
        groups: dict[str, list] = {k: [] for k in CATEGORY_LABELS}
        removed = 0
        for q in plan.questions:
            if _FORBIDDEN_Q.search(q.question):
                removed += 1
                continue
            ev = None
            if q.cv_evidence:
                m = find_quote(src, q.cv_evidence)
                ev = {
                    "quote": q.cv_evidence,
                    "verified": m.status in ("verified", "approximate"),
                    "location": {"start": m.start, "end": m.end, "section": section_at(trow.sections, m.start)}
                    if m.start is not None else None,
                }
            groups[q.category].append(
                {"question": q.question, "why_relevant": q.why_relevant, "competency": q.competency, "evidence": ev}
            )
        a.result = {
            "categories": [
                {"key": k, "label": CATEGORY_LABELS[k], "questions": v} for k, v in groups.items()
            ],
            "used_analysis_gaps": bool(gaps),
            "removed_questions": removed,
            "model": meta["model"],
            "prompt_version": PROMPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": "Questions are suggestions to support a structured, job-related interview. "
                          "Review them before use.",
        }
        a.status, a.progress, a.model = "completed", 100, meta["model"]
        a.completed_at = datetime.now(timezone.utc)
        events.record(db, "interview_completed", candidate_id=a.candidate_id, job_id=a.job_id,
                      questions=len(plan.questions) - removed)
        db.commit()
    except OllamaError as e:
        db.rollback()
        a = db.get(Analysis, analysis_id)
        if a:
            a.status, a.error_message = "failed", e.user_message
            db.commit()
    except Exception:  # noqa: BLE001
        log.exception("interview generation failed id=%s", analysis_id)
        db.rollback()
        a = db.get(Analysis, analysis_id)
        if a:
            a.status, a.error_message = "failed", "Unexpected error while preparing the interview."
            db.commit()
