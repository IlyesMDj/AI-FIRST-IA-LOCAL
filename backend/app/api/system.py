from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.i18n import Lang, get_lang, tr, tr_list
from app.llm.gateway import INFERENCE_LOCK, get_client
from app.llm.ollama_client import OllamaError
from app.models import Analysis, Candidate, CandidateStatus, JobDescription, LifecycleEvent
from app.services import hardware
from app.services.ocr import ocr_available
from app.services.settings_service import AISettings, get_ai_settings, save_ai_settings
from app.worker import worker

router = APIRouter(prefix="/api", tags=["system"])

MODEL_ROLES = {
    "qwen3:8b": "Recommended primary model (best structured extraction & French; fits in 8 GB VRAM)",
    "qwen2.5:7b": "Secondary model (fast, reliable JSON)",
    "mistral-nemo:latest": "Alternative (12B, strong French; partially offloaded to CPU on 8 GB VRAM, slower)",
    "nomic-embed-text:latest": "Embedding model for semantic search",
    "moondream:latest": "Small vision model (optional image understanding)",
}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/system/status")
def system_status(db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    ai = get_ai_settings(db)
    s = get_settings()
    ollama: dict = {"url": s.ollama_url, "reachable": False}
    models: list[dict] = []
    running: list[dict] = []
    try:
        client = get_client()
        ollama["version"] = client.version()
        ollama["reachable"] = True
        for m in client.list_models():
            d = m.get("details", {})
            models.append({
                "name": m["name"], "size_mb": int(m.get("size", 0) / 1048576),
                "parameter_size": d.get("parameter_size"), "quantization": d.get("quantization_level"),
                "family": d.get("family"), "capabilities": m.get("capabilities", []),
                "role": tr(MODEL_ROLES.get(m["name"]), lang),
            })
        for m in client.running_models():
            running.append({
                "name": m.get("name"), "size_mb": int(m.get("size", 0) / 1048576),
                "vram_mb": int(m.get("size_vram", 0) / 1048576), "context_length": m.get("context_length"),
                "expires_at": m.get("expires_at"),
            })
    except OllamaError as e:
        ollama["error"] = tr(e.user_message, lang)
    names = {m["name"] for m in models}
    issues = []
    if ollama["reachable"]:
        for role, name in (("Active model", ai.active_model), ("Embedding model", ai.embedding_model)):
            if name not in names:
                alt = [n for n in ("qwen3:8b", "qwen2.5:7b", "mistral-nemo:latest") if n in names]
                issues.append(
                    f"{role} '{name}' is not installed. "
                    + (f"Select an installed model such as {alt[0]} in AI settings." if alt else "Install a model with 'ollama pull'.")
                )
    else:
        issues.append("The local AI engine (Ollama) is not reachable. Start Ollama, then refresh.")
    return {
        "ollama": ollama,
        "active_model": ai.active_model,
        "embedding_model": ai.embedding_model,
        "active_model_available": ai.active_model in names,
        "embedding_model_available": ai.embedding_model in names,
        "installed_models": models,
        "running_models": running,
        "hardware": hardware.snapshot(),
        "queue": {"pending": worker.pending_count(), "current": worker.current[0] if worker.current else None},
        "ocr_available": ocr_available(),
        "issues": tr_list(issues, lang),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    def count(stmt) -> int:
        return int(db.execute(stmt).scalar() or 0)

    by_status = dict(db.execute(select(Candidate.status, func.count()).group_by(Candidate.status)).all())
    pending_analyses = count(select(func.count()).select_from(Analysis).where(Analysis.status.in_(["pending", "processing"])))
    recent = db.execute(
        select(LifecycleEvent, Candidate.display_name, Candidate.original_filename, JobDescription.title)
        .outerjoin(Candidate, Candidate.id == LifecycleEvent.candidate_id)
        .outerjoin(JobDescription, JobDescription.id == LifecycleEvent.job_id)
        .order_by(LifecycleEvent.id.desc())
        .limit(12)
    ).all()
    return {
        "total_applications": sum(by_status.values()),
        "active_candidates": by_status.get(CandidateStatus.COMPLETED, 0),
        "processed_cvs": by_status.get(CandidateStatus.COMPLETED, 0),
        "failed_cvs": by_status.get(CandidateStatus.FAILED, 0),
        "pending_extractions": sum(by_status.get(s, 0) for s in (CandidateStatus.IMPORTED, CandidateStatus.PENDING, CandidateStatus.PROCESSING)),
        "pending_analyses": pending_analyses,
        "job_descriptions": count(select(func.count()).select_from(JobDescription)),
        "completed_analyses": count(select(func.count()).select_from(Analysis).where(Analysis.status == "completed")),
        "by_status": by_status,
        "recent_activity": [
            {
                "id": ev.id, "ts": ev.ts, "type": ev.event_type, "candidate_id": ev.candidate_id,
                "candidate_label": name or fname, "job_id": ev.job_id, "job_title": title,
            }
            for ev, name, fname, title in recent
        ],
    }


# ----------------------------------------------------------------- settings
@router.get("/settings/ai")
def get_settings_ai(db: Session = Depends(get_db), lang: Lang = Depends(get_lang)):
    return {"settings": get_ai_settings(db), "model_roles": {k: tr(v, lang) for k, v in MODEL_ROLES.items()}}


@router.put("/settings/ai")
def put_settings_ai(body: AISettings, db: Session = Depends(get_db)):
    previous = get_ai_settings(db)
    try:
        client = get_client()
        names = {m["name"] for m in client.list_models()}
        for label, name in (("Active model", body.active_model), ("Embedding model", body.embedding_model)):
            if name not in names:
                raise HTTPException(400, f"{label} '{name}' is not installed in Ollama. Models are never downloaded automatically.")
        if previous.active_model != body.active_model:
            with INFERENCE_LOCK:
                client.unload(previous.active_model)
    except OllamaError:
        pass  # allow saving settings while Ollama is offline
    return {"settings": save_ai_settings(db, body)}


class ModelAction(BaseModel):
    model: str


@router.post("/system/models/unload")
def unload_model(body: ModelAction):
    try:
        with INFERENCE_LOCK:
            get_client().unload(body.model)
    except OllamaError as e:
        raise HTTPException(503, e.user_message)
    return {"status": "unloaded"}


@router.post("/system/models/load")
def load_model(body: ModelAction, db: Session = Depends(get_db)):
    from app.llm.gateway import LLMGateway

    try:
        gw = LLMGateway(get_ai_settings(db))
        with INFERENCE_LOCK:
            gw.prepare_model(body.model, is_embedding="embed" in body.model)
            gw.client.load(body.model, keep_alive=gw.ai.keep_alive)
    except OllamaError as e:
        raise HTTPException(503, e.user_message)
    return {"status": "loaded"}
