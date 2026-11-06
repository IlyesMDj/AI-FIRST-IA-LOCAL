from __future__ import annotations

import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.i18n import Lang, get_lang, tr, tr_list, tr_report
from app.models import Candidate, CandidateProfile, CandidateStatus, CandidateText, DeletionReport
from app.schemas.api import CandidateDetail, CandidateSummary
from app.services import storage
from app.services.candidates import import_file, mark_pending
from app.services.deletion import CandidateNotFound, delete_candidate
from app.services.settings_service import get_ai_settings
from app.worker import worker

router = APIRouter(prefix="/api/candidates", tags=["candidates"])

_UUID = re.compile(r"^[0-9a-f-]{36}$")


def get_candidate_or_404(db: Session, candidate_id: str) -> Candidate:
    if not _UUID.match(candidate_id):
        raise HTTPException(404, "Candidate not found")
    c = db.get(Candidate, candidate_id)
    if c is None:
        raise HTTPException(404, "Candidate not found")
    return c


def to_summary(c: Candidate, confidence: float | None = None, lang: str = "en") -> CandidateSummary:
    s = CandidateSummary.model_validate(c)
    s.has_warnings = bool(c.warnings or c.injection_flags or c.possible_duplicates)
    s.confidence = confidence
    s.error_message = tr(s.error_message, lang)
    s.processing_step = tr(s.processing_step, lang)
    return s


@router.get("", response_model=list[CandidateSummary])
def list_candidates(
    q: str | None = Query(None, max_length=100),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    lang: Lang = Depends(get_lang),
):
    stmt = select(Candidate, CandidateProfile.confidence).outerjoin(
        CandidateProfile, CandidateProfile.candidate_id == Candidate.id
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Candidate.display_name.ilike(like), Candidate.original_filename.ilike(like), Candidate.email.ilike(like)))
    if status in CandidateStatus.ALL:
        stmt = stmt.where(Candidate.status == status)
    stmt = stmt.order_by(Candidate.created_at.desc())
    return [to_summary(c, conf, lang) for c, conf in db.execute(stmt).all()]


@router.post("/upload")
async def upload(
    files: list[UploadFile] = File(...),
    allow_duplicates: bool = Form(False),
    db: Session = Depends(get_db),
    lang: Lang = Depends(get_lang),
):
    s = get_settings()
    if len(files) > s.max_files_per_batch:
        raise HTTPException(400, f"At most {s.max_files_per_batch} files can be imported at once.")
    ai = get_ai_settings(db)
    results = []
    limit = s.max_upload_mb * 1024 * 1024
    for f in files:
        content = await f.read(limit + 1)
        res = import_file(db, f.filename or "document", content, allow_duplicate=allow_duplicates)
        if res["status"] == "imported" and ai.auto_process_on_import:
            cand = db.get(Candidate, res["candidate_id"])
            mark_pending(db, cand)
            worker.enqueue("candidate", cand.id)
        if res.get("error"):
            res["error"] = tr(res["error"], lang)
        results.append(res)
    return {"results": results}


@router.get("/{candidate_id}", response_model=CandidateDetail)
def get_candidate(candidate_id: str, db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    c = get_candidate_or_404(db, candidate_id)
    d = CandidateDetail.model_validate(c)
    d.has_warnings = bool(c.warnings or c.injection_flags or c.possible_duplicates)
    d.error_message = tr(d.error_message, lang)
    d.processing_step = tr(d.processing_step, lang)
    d.warnings = tr_list(d.warnings, lang)
    d.possible_duplicates = [{**p, "rule": tr(p.get("rule"), lang)} for p in d.possible_duplicates]
    prof = db.get(CandidateProfile, c.id)
    if prof:
        d.profile, d.confidence = prof.data, prof.confidence
    t = db.get(CandidateText, c.id)
    if t:
        d.text_method, d.redactions = t.method, t.redactions
    return d


@router.get("/{candidate_id}/text")
def get_text(candidate_id: str, db: Session = Depends(get_db)):
    c = get_candidate_or_404(db, candidate_id)
    t = db.get(CandidateText, c.id)
    if t is None:
        raise HTTPException(404, "The document has not been read yet.")
    return {"text": t.text, "sections": t.sections, "method": t.method, "redactions": t.redactions}


@router.get("/{candidate_id}/document")
def get_document(candidate_id: str, db: Session = Depends(get_db)):
    c = get_candidate_or_404(db, candidate_id)
    if not c.stored_filename:
        raise HTTPException(404, "The original document is not kept (see AI settings).")
    path = storage.original_path(c.id, c.stored_filename)
    if not path.exists():
        raise HTTPException(404, "Original document not found.")
    media = {"pdf": "application/pdf", "txt": "text/plain; charset=utf-8", "jpg": "image/jpeg", "png": "image/png",
             "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}[c.file_type]
    disp = "attachment" if c.file_type == "docx" else "inline"
    return FileResponse(
        path, media_type=media, filename=c.original_filename, content_disposition_type=disp,
        # PDFs are rendered by the browser's built-in viewer (which refuses CSP sandbox);
        # text is shown sandboxed so it can never execute as a page.
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
                 **({"Content-Security-Policy": "sandbox"} if c.file_type == "txt" else {})},
    )


@router.post("/{candidate_id}/process")
def process(candidate_id: str, db: Session = Depends(get_db)):
    c = get_candidate_or_404(db, candidate_id)
    if c.status == CandidateStatus.PROCESSING:
        raise HTTPException(409, "This candidate is already being processed.")
    if not c.stored_filename:
        raise HTTPException(409, "The original document is no longer stored; it cannot be processed again.")
    mark_pending(db, c)
    worker.enqueue("candidate", c.id)
    return {"status": "pending"}


@router.delete("/{candidate_id}")
def delete(candidate_id: str, db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    get_candidate_or_404(db, candidate_id)
    try:
        rep = delete_candidate(db, candidate_id)
    except CandidateNotFound:
        raise HTTPException(404, "Candidate not found")
    return {"report_id": rep.id, "success": rep.success, "report": tr_report(rep.report, lang)}


deletion_router = APIRouter(prefix="/api/deletion-reports", tags=["privacy"])


@deletion_router.get("")
def list_reports(db: Session = Depends(get_db)):
    rows = db.execute(select(DeletionReport).order_by(DeletionReport.deleted_at.desc()).limit(200)).scalars()
    return [{"id": r.id, "candidate_ref": r.candidate_ref, "deleted_at": r.deleted_at, "success": r.success} for r in rows]


@deletion_router.get("/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    r = db.get(DeletionReport, report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    return {"id": r.id, "candidate_ref": r.candidate_ref, "deleted_at": r.deleted_at, "success": r.success,
            "report": tr_report(r.report, lang)}
