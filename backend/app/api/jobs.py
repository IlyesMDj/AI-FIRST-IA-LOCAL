from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.i18n import Lang, get_lang, tr, tr_result
from app.models import Analysis, Candidate, CandidateStatus, JobDescription
from app.schemas.api import AnalysisOut, AnalysisRequest, JobIn, JobOut
from app.services import events
from app.services.analysis import build_criteria, create_analysis
from app.worker import worker

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_or_404(db: Session, job_id: str) -> JobDescription:
    j = db.get(JobDescription, job_id)
    if j is None:
        raise HTTPException(404, "Job description not found")
    return j


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.execute(select(JobDescription).order_by(JobDescription.updated_at.desc())).scalars().all()


@router.post("", response_model=JobOut, status_code=201)
def create_job(body: JobIn, db: Session = Depends(get_db)):
    j = JobDescription(**body.model_dump())
    db.add(j)
    db.flush()
    events.record(db, "job_created", job_id=j.id)
    db.commit()
    return j


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    return _job_or_404(db, job_id)


@router.get("/{job_id}/criteria")
def get_criteria(job_id: str, db: Session = Depends(get_db)):
    return build_criteria(_job_or_404(db, job_id))


@router.put("/{job_id}", response_model=JobOut)
def update_job(job_id: str, body: JobIn, db: Session = Depends(get_db)):
    j = _job_or_404(db, job_id)
    for k, v in body.model_dump().items():
        setattr(j, k, v)
    events.record(db, "job_updated", job_id=j.id)
    db.commit()
    return j


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    j = _job_or_404(db, job_id)
    db.delete(j)
    events.record(db, "job_deleted", job_id=job_id)
    db.commit()


analysis_router = APIRouter(prefix="/api/analyses", tags=["analysis"])


def _out(db: Session, a: Analysis, lang: str = "en") -> AnalysisOut:
    o = AnalysisOut.model_validate(a)
    o.error_message = tr(o.error_message, lang)
    o.result = tr_result(o.result, lang)
    c = db.get(Candidate, a.candidate_id)
    j = db.get(JobDescription, a.job_id)
    o.candidate_name = (c.display_name or c.original_filename) if c else None
    o.job_title = j.title if j else None
    return o


def _request(db: Session, body: AnalysisRequest, kind: str) -> list[AnalysisOut]:
    _job_or_404(db, body.job_id)
    out = []
    for cid in dict.fromkeys(body.candidate_ids):
        c = db.get(Candidate, cid)
        if c is None:
            raise HTTPException(404, "Candidate not found")
        if c.status != CandidateStatus.COMPLETED:
            raise HTTPException(409, f"The CV '{c.display_name or c.original_filename}' has not been processed yet.")
    for cid in dict.fromkeys(body.candidate_ids):
        a = create_analysis(db, cid, body.job_id, kind)
        worker.enqueue(kind, a.id)
        out.append(_out(db, a))
    return out


@analysis_router.post("", response_model=list[AnalysisOut], status_code=202)
def request_analysis(body: AnalysisRequest, db: Session = Depends(get_db)):
    return _request(db, body, "analysis")


@analysis_router.post("/interview", response_model=list[AnalysisOut], status_code=202)
def request_interview(body: AnalysisRequest, db: Session = Depends(get_db)):
    return _request(db, body, "interview")


@analysis_router.get("", response_model=list[AnalysisOut])
def list_analyses(
    candidate_id: str | None = Query(None),
    job_id: str | None = Query(None),
    kind: str | None = Query(None),
    db: Session = Depends(get_db),
    lang: Lang = Depends(get_lang),
):
    stmt = select(Analysis).order_by(Analysis.created_at.desc()).limit(500)
    if candidate_id:
        stmt = stmt.where(Analysis.candidate_id == candidate_id)
    if job_id:
        stmt = stmt.where(Analysis.job_id == job_id)
    if kind:
        stmt = stmt.where(Analysis.kind == kind)
    return [_out(db, a, lang) for a in db.execute(stmt).scalars()]


@analysis_router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: str, db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    a = db.get(Analysis, analysis_id)
    if a is None:
        raise HTTPException(404, "Analysis not found")
    return _out(db, a, lang)


@analysis_router.delete("/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, db: Session = Depends(get_db)):
    a = db.get(Analysis, analysis_id)
    if a is None:
        raise HTTPException(404, "Analysis not found")
    db.delete(a)
    db.commit()
