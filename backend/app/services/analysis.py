"""Candidate ↔ job analysis (per criterion, evidence-based, no score)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.llm.gateway import LLMGateway
from app.llm.ollama_client import OllamaError
from app.llm.prompts import PROMPT_VERSION, analysis_messages
from app.models import Analysis, Candidate, CandidateStatus, CandidateText, JobDescription
from app.schemas.llm import CriterionAssessment
from app.services import events
from app.services.candidates import max_chars_for_ctx
from app.services.documents import section_at
from app.services.evidence import find_quote, normalise
from app.services.settings_service import get_ai_settings

log = logging.getLogger(__name__)

DISCLAIMER = (
    "This analysis lists evidence found in the CV for each job requirement. It is not a score, "
    "a ranking or a hiring recommendation. 'Not found in the CV' only means the CV does not mention it; "
    "it does not prove the candidate lacks the skill. The decision remains with the recruiter."
)

STATUS_LABELS = {
    "demonstrated": "Clearly demonstrated",
    "partial": "Partially demonstrated",
    "not_found": "Not found in the CV",
    "undetermined": "Cannot be determined",
}


def build_criteria(job: JobDescription) -> list[dict]:
    crit: list[dict] = []

    def add(kind: str, importance: str, text: str) -> None:
        text = (text or "").strip()
        if text:
            crit.append({"id": f"c{len(crit) + 1}", "kind": kind, "importance": importance, "requirement": text})

    for s in job.required_skills or []:
        add("skill", "required", s)
    for s in job.optional_skills or []:
        add("skill", "optional", s)
    add("experience", "required", job.experience_requirements)
    add("education", "required", job.education_requirements)
    for lang in job.languages or []:
        add("language", "required", lang)
    for c in job.criteria or []:
        add("criterion", "required", c)
    return crit


def job_context(job: JobDescription) -> str:
    parts = [f"Title: {job.title}"]
    if job.description:
        parts.append(f"Description: {job.description[:1500]}")
    if job.responsibilities:
        parts.append("Responsibilities: " + "; ".join(job.responsibilities)[:800])
    return "\n".join(parts)


def postprocess_assessment(a: CriterionAssessment, text: str, sections: list[dict]) -> dict:
    src = normalise(text)
    evidence = []
    for q in a.evidence_quotes[:3]:
        m = find_quote(src, q)
        evidence.append(
            {
                "quote": q,
                "verified": m.status in ("verified", "approximate"),
                "match": m.status,
                "location": (
                    {"start": m.start, "end": m.end, "section": section_at(sections, m.start)}
                    if m.start is not None
                    else None
                ),
            }
        )
    status = a.status
    notes: list[str] = []
    verified = [e for e in evidence if e["verified"]]
    if status in ("demonstrated", "partial") and not verified:
        status = "undetermined"
        notes.append(
            "The model claimed evidence, but the quoted text could not be found in the CV. "
            "Status changed to 'cannot be determined'. Please check the CV manually."
        )
    elif evidence and len(verified) < len(evidence):
        notes.append("Some quotes could not be found verbatim in the CV and are marked as unverified.")
    return {
        "status": status,
        "status_label": STATUS_LABELS[status],
        "model_status": a.status,
        "evidence": evidence,
        "relevant_experience": a.relevant_experience,
        "missing_information": a.missing_information,
        "explanation": a.explanation,
        "verification_notes": notes,
    }


def create_analysis(db: Session, candidate_id: str, job_id: str, kind: str = "analysis") -> Analysis:
    a = Analysis(candidate_id=candidate_id, job_id=job_id, kind=kind, status="pending")
    db.add(a)
    events.record(db, f"{kind}_requested", candidate_id=candidate_id, job_id=job_id)
    db.commit()
    return a


def _load(db: Session, analysis_id: str):
    a = db.get(Analysis, analysis_id)
    if a is None:
        return None, None, None, None
    cand = db.get(Candidate, a.candidate_id)
    job = db.get(JobDescription, a.job_id)
    trow = db.get(CandidateText, a.candidate_id)
    return a, cand, job, trow


def run_analysis(db: Session, analysis_id: str, gateway: LLMGateway | None = None) -> None:
    a, cand, job, trow = _load(db, analysis_id)
    if a is None:
        return
    if cand is None or job is None or trow is None or cand.status != CandidateStatus.COMPLETED:
        a.status, a.error_message = "failed", "The candidate's CV has not been processed yet."
        db.commit()
        return
    ai = get_ai_settings(db)
    gateway = gateway or LLMGateway(ai)
    a.status, a.progress, a.error_message = "processing", 0, None
    db.commit()
    criteria = build_criteria(job)
    if not criteria:
        a.status, a.error_message = "failed", "The job description has no requirement to analyse."
        db.commit()
        return
    text = trow.text[: max_chars_for_ctx(ai.num_ctx)]
    ctx = job_context(job)
    results = []
    try:
        for i, c in enumerate(criteria):
            obj, meta = gateway.generate_structured(
                CriterionAssessment,
                analysis_messages(text, ctx, c["requirement"], f"{c['importance']} {c['kind']}"),
                num_predict=700,
            )
            results.append({**c, **postprocess_assessment(obj, trow.text, trow.sections)})
            db.refresh(a)
            a.progress = int((i + 1) * 100 / len(criteria))
            db.commit()
        a.result = {
            "job_snapshot": {"title": job.title, "criteria_count": len(criteria)},
            "criteria": results,
            "disclaimer": DISCLAIMER,
            "model": ai.active_model,
            "prompt_version": PROMPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        a.status, a.model, a.progress = "completed", ai.active_model, 100
        a.completed_at = datetime.now(timezone.utc)
        events.record(db, "analysis_completed", candidate_id=a.candidate_id, job_id=a.job_id, criteria=len(criteria))
        db.commit()
    except OllamaError as e:
        db.rollback()
        a = db.get(Analysis, analysis_id)
        if a:
            a.status, a.error_message = "failed", e.user_message
            db.commit()
    except Exception:  # noqa: BLE001
        log.exception("analysis failed id=%s", analysis_id)
        db.rollback()
        a = db.get(Analysis, analysis_id)
        if a:
            a.status, a.error_message = "failed", "Unexpected error during the analysis."
            db.commit()
