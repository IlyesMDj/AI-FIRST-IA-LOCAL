"""Candidate import and processing pipeline.

Pipeline (run by the worker, sequentially):
  imported → pending → processing[reading document → redacting → extracting
  information → indexing] → completed | failed
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.gateway import LLMGateway
from app.llm.ollama_client import OllamaError
from app.llm.prompts import PROMPT_VERSION, extraction_messages
from app.models import Candidate, CandidateProfile, CandidateStatus, CandidateText
from app.schemas.llm import CVExtraction
from app.services import events, storage
from app.services.documents import (
    DocumentError,
    detect_sections,
    detect_type,
    extract_text,
    sanitize_filename,
    section_at,
)
from app.services.evidence import find_quote, normalise, term_in_text
from app.services.privacy import detect_injection, find_email, find_phone, redact_sensitive
from app.services.settings_service import AISettings, get_ai_settings
from app.services.vector_store import attach_embeddings, store_chunks

log = logging.getLogger(__name__)


class ImportResult(dict):
    pass


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def import_file(db: Session, filename: str, content: bytes, *, allow_duplicate: bool = False) -> dict[str, Any]:
    """Validate and store one uploaded file. Returns a per-file result dict."""
    s = get_settings()
    safe_name = sanitize_filename(filename)
    if len(content) > s.max_upload_mb * 1024 * 1024:
        return {"filename": safe_name, "status": "rejected", "error": f"File larger than {s.max_upload_mb} MB."}
    try:
        file_type = detect_type(safe_name, content)
    except DocumentError as e:
        return {"filename": safe_name, "status": "rejected", "error": e.user_message}

    digest = sha256(content)
    existing = db.execute(select(Candidate).where(Candidate.file_hash == digest)).scalars().first()
    if existing and not allow_duplicate:
        return {
            "filename": safe_name,
            "status": "duplicate",
            "error": "This exact file was already imported. It was not imported again.",
            "existing_candidate_id": existing.id,
        }

    cand = Candidate(
        file_hash=digest,
        original_filename=safe_name,
        file_type=file_type,
        file_size=len(content),
        status=CandidateStatus.IMPORTED,
    )
    db.add(cand)
    db.flush()
    try:
        cand.stored_filename = storage.save_original(cand.id, file_type, content)
    except Exception:
        db.rollback()
        log.exception("could not store upload")
        return {"filename": safe_name, "status": "rejected", "error": "The file could not be saved locally."}
    events.record(db, "document_imported", candidate_id=cand.id, file_type=file_type, size=len(content))
    db.commit()
    return {"filename": safe_name, "status": "imported", "candidate_id": cand.id}


def mark_pending(db: Session, cand: Candidate) -> None:
    cand.status = CandidateStatus.PENDING
    cand.processing_step = None
    cand.error_message = None
    db.commit()


# ----------------------------------------------------------------- pipeline
def _set_step(db: Session, cand: Candidate, step: str) -> None:
    cand.processing_step = step
    db.commit()


def max_chars_for_ctx(num_ctx: int) -> int:
    # ~3 chars/token for FR/EN CVs; keep room for prompt (~900 tok) and output (~3000 tok)
    return max(4000, min(get_settings().max_text_chars, (num_ctx - 4000) * 3))


def process_candidate(db: Session, candidate_id: str, gateway: LLMGateway | None = None) -> None:
    cand = db.get(Candidate, candidate_id)
    if cand is None:
        return  # deleted meanwhile
    ai = get_ai_settings(db)
    gateway = gateway or LLMGateway(ai)
    cand.status = CandidateStatus.PROCESSING
    cand.error_message = None
    cand.warnings = []
    db.commit()
    try:
        _read_document(db, cand, ai)
        _extract_profile(db, cand, gateway, ai)
        _index(db, cand, gateway, ai)
        _check_possible_duplicates(db, cand, ai)
        cand.status = CandidateStatus.COMPLETED
        cand.processing_step = None
        cand.processed_at = datetime.now(timezone.utc)
        events.record(db, "processing_completed", candidate_id=cand.id)
        db.commit()
    except (DocumentError, OllamaError) as e:
        db.rollback()
        cand = db.get(Candidate, candidate_id)
        if cand is None:
            return
        cand.status = CandidateStatus.FAILED
        cand.error_message = e.user_message
        events.record(db, "processing_failed", candidate_id=cand.id, code=getattr(e, "code", "error"))
        db.commit()
    except Exception:  # noqa: BLE001 - never crash the worker
        log.exception("unexpected processing error candidate=%s", candidate_id)
        db.rollback()
        cand = db.get(Candidate, candidate_id)
        if cand is None:
            return
        cand.status = CandidateStatus.FAILED
        cand.error_message = "Unexpected error while processing this document. See the application logs."
        events.record(db, "processing_failed", candidate_id=cand.id, code="unexpected")
        db.commit()


def _read_document(db: Session, cand: Candidate, ai: AISettings) -> None:
    _set_step(db, cand, "Reading document")
    content = storage.read_original(cand.id, cand.stored_filename or "")
    doc = extract_text(cand.file_type, content, max_pages=get_settings().max_pdf_pages, ocr_enabled=ai.ocr_enabled)
    _set_step(db, cand, "Removing unnecessary personal data")
    red = redact_sensitive(doc.text)
    sections = detect_sections(red.text)
    flags = detect_injection(red.text)
    row = db.get(CandidateText, cand.id)
    if row is None:
        row = CandidateText(candidate_id=cand.id, text=red.text, char_count=len(red.text), method=doc.method)
        db.add(row)
    row.text, row.char_count, row.method = red.text, len(red.text), doc.method
    row.redactions, row.sections = red.counts, sections
    cand.page_count = doc.page_count
    cand.ocr_used = doc.method == "ocr"
    cand.injection_flags = flags
    cand.email = find_email(red.text)
    cand.phone = find_phone(red.text)
    cand.warnings = list(doc.warnings)
    if flags:
        cand.warnings.append(
            "This document contains text that looks like instructions addressed to an AI. "
            "It was treated as plain content and ignored as an instruction."
        )
    if not ai.keep_original_files:
        storage.remove_candidate_files(cand.id)
        cand.stored_filename = None
    events.record(
        db, "text_extracted", candidate_id=cand.id, method=doc.method, chars=len(red.text),
        redactions=sum(red.counts.values()), injection_flags=len(flags),
    )
    db.commit()


def _annotate(item: dict, quote_field: str, src, sections: list[dict], *, fallback_terms: list[str] = ()) -> str:
    quote = item.get(quote_field)
    status = "missing"
    loc = None
    if quote:
        m = find_quote(src, quote)
        status = m.status
        if m.start is not None:
            loc = {"start": m.start, "end": m.end, "section": section_at(sections, m.start)}
    if status in ("missing", "not_found"):
        for term in fallback_terms:
            if term and term_in_text(src, term):
                status = "term_found"
                break
    item["verification"] = {"status": status, "location": loc}
    return status


_SENSITIVE_SKILL_RE = re.compile(
    r"(?i)\b(mari[ée]|married|c[ée]libataire|enfants?|children|religio|catholi|musulman|muslim|juif|jewish|"
    r"chr[ée]tien|christian|nationalit|handicap|disabilit|sant[ée]|health|[âa]ge\b|n[ée] le|born)"
)


def postprocess_extraction(obj: CVExtraction, text: str, sections: list[dict]) -> tuple[dict, float, list[str]]:
    """Verify evidence, drop sensitive items, compute confidence."""
    data = obj.model_dump()
    src = normalise(text)
    warnings: list[str] = []
    before = len(data["skills"])
    data["skills"] = [s for s in data["skills"] if not _SENSITIVE_SKILL_RE.search(s["name"] or "")]
    if len(data["skills"]) != before:
        warnings.append("Some extracted items unrelated to the job were discarded (data minimisation).")
    if data.get("professional_summary"):
        data["professional_summary"] = redact_sensitive(data["professional_summary"]).text

    checked = verified = 0
    for s in data["skills"]:
        st = _annotate(s, "evidence", src, sections, fallback_terms=[s["name"]])
        checked += 1
        verified += st in ("verified", "approximate", "term_found")
    for e in data["experience"]:
        st = _annotate(e, "evidence", src, sections, fallback_terms=[e.get("company") or "", e.get("position") or ""])
        checked += 1
        verified += st in ("verified", "approximate", "term_found")
    for e in data["education"]:
        st = _annotate(e, "evidence", src, sections, fallback_terms=[e.get("institution") or "", e.get("degree") or ""])
        checked += 1
        verified += st in ("verified", "approximate", "term_found")
    for key, name_field in (("languages", "language"), ("certifications", "name"), ("projects", "name")):
        for it in data[key]:
            st = _annotate(it, "evidence", src, sections, fallback_terms=[it.get(name_field) or ""])
            checked += 1
            verified += st in ("verified", "approximate", "term_found")
    confidence = round(verified / checked, 2) if checked else None
    unverified = checked - verified
    if unverified:
        warnings.append(
            f"{unverified} extracted item(s) could not be matched with the CV text. They are marked "
            "'unverified' and should be checked against the original document."
        )
    if checked == 0:
        warnings.append("No professional information could be extracted from this document.")
    return data, confidence if confidence is not None else 0.0, warnings


_NAME_LINE_RE = re.compile(r"^[A-ZÀ-Ý][\w'’\-]+(?:\s+[A-ZÀ-Ý][\w'’\-]+){1,3}$")


def guess_name(text: str) -> str | None:
    """Fallback: first short line that looks like 'Firstname Lastname'."""
    for line in text.split("\n")[:3]:
        line = line.strip()
        if _NAME_LINE_RE.match(line) and not re.search(r"\d|@", line):
            return line
    return None


def _extract_profile(db: Session, cand: Candidate, gateway: LLMGateway, ai: AISettings) -> None:
    _set_step(db, cand, "Extracting professional information")
    trow = db.get(CandidateText, cand.id)
    assert trow is not None
    limit = max_chars_for_ctx(ai.num_ctx)
    text = trow.text
    pre_warnings: list[str] = []
    if len(text) > limit:
        pre_warnings.append(f"The CV is long: only the first {limit} characters were analysed by the AI model.")
        text = text[:limit]
    obj, meta = gateway.generate_structured(CVExtraction, extraction_messages(text), num_predict=3500)
    data, confidence, warnings = postprocess_extraction(obj, trow.text, trow.sections)
    db.refresh(cand)  # may have been deleted in the meantime
    data["extraction_metadata"] = {
        "model": meta["model"],
        "confidence": confidence,
        "confidence_method": "share of extracted items whose evidence was found in the CV text",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "prompt_version": PROMPT_VERSION,
        "attempts": meta["attempts"],
        "duration_s": meta["duration_s"],
        "text_method": trow.method,
    }
    profile = db.get(CandidateProfile, cand.id)
    if profile is None:
        profile = CandidateProfile(candidate_id=cand.id, data=data, model=meta["model"], confidence=confidence)
        db.add(profile)
    else:
        profile.data, profile.model, profile.confidence = data, meta["model"], confidence
    name = data.get("candidate_name") or guess_name(trow.text)
    data["candidate_name"] = name
    cand.display_name = name if name else cand.display_name
    cand.warnings = cand.warnings + pre_warnings + warnings
    events.record(
        db, "profile_extracted", candidate_id=cand.id, model=meta["model"], attempts=meta["attempts"],
        duration_s=meta["duration_s"], confidence=confidence,
    )
    db.commit()


def _index(db: Session, cand: Candidate, gateway: LLMGateway, ai: AISettings) -> None:
    _set_step(db, cand, "Indexing for search")
    trow = db.get(CandidateText, cand.id)
    assert trow is not None
    rows = store_chunks(db, cand.id, trow.text, trow.sections)
    try:
        vecs = gateway.embed([r.text for r in rows])
        attach_embeddings(rows, vecs, ai.embedding_model)
        events.record(db, "embeddings_created", candidate_id=cand.id, chunks=len(rows), model=ai.embedding_model)
    except OllamaError as e:
        # Keyword search still works; semantic search is degraded.
        cand.warnings = cand.warnings + ["Semantic indexing failed; keyword search only. " + e.user_message]
        events.record(db, "embeddings_failed", candidate_id=cand.id, code=e.code)
    db.commit()


def _check_possible_duplicates(db: Session, cand: Candidate, ai: AISettings) -> None:
    """Flag (never merge) other candidates that may be the same person."""
    rules = ai.duplicate_rules
    found: list[dict] = []
    if rules.email and cand.email:
        for other in db.execute(
            select(Candidate).where(func.lower(Candidate.email) == cand.email.lower(), Candidate.id != cand.id)
        ).scalars():
            found.append({"candidate_id": other.id, "rule": "same email address"})
    if rules.name_and_phone and cand.display_name and cand.phone:
        digits = re.sub(r"\D", "", cand.phone)
        for other in db.execute(
            select(Candidate).where(func.lower(Candidate.display_name) == cand.display_name.lower(), Candidate.id != cand.id)
        ).scalars():
            if other.phone and re.sub(r"\D", "", other.phone) == digits:
                found.append({"candidate_id": other.id, "rule": "same name and phone number"})
    cand.possible_duplicates = found
    if found:
        cand.warnings = cand.warnings + [
            "This profile may correspond to an existing candidate. Profiles were NOT merged: please review."
        ]
