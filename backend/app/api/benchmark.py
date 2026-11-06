from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm.gateway import get_client
from app.llm.ollama_client import OllamaError
from app.services import benchmark
from app.services.settings_service import get_ai_settings

router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])


class BenchmarkRequest(BaseModel):
    models: list[str] = Field(min_length=1, max_length=6)


@router.post("/run", status_code=202)
def run(body: BenchmarkRequest, db: Session = Depends(get_db)):
    try:
        installed = {m["name"] for m in get_client().list_models()}
    except OllamaError as e:
        raise HTTPException(503, e.user_message)
    missing = [m for m in body.models if m not in installed]
    if missing:
        raise HTTPException(400, f"Not installed: {', '.join(missing)}. Models are never downloaded automatically.")
    if not benchmark.start_background(body.models, get_ai_settings(db)):
        raise HTTPException(409, "A benchmark is already running.")
    return {"status": "started"}


@router.get("/status")
def status():
    return benchmark.status()


@router.get("/results")
def results():
    return benchmark.list_results()
