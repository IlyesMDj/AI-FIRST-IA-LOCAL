"""API HTTP (FastAPI) — conforme à CONTRACTS.md, préfixe /api.

Lancement (depuis backend/) : uvicorn copilot.api:app --host 127.0.0.1 --port 8000
Base : variable d'environnement COPILOT_DB (sinon config.DB_PATH = data/copilot.db).

Uploads EN MÉMOIRE uniquement : on n'utilise PAS le parseur de formulaire de Starlette, qui range
chaque fichier dans un SpooledTemporaryFile débordant sur disque (%TEMP%) au-delà de 1 Mo
(starlette.formparsers.MultiPartParser.spool_max_size) — ce serait une copie du CV hors de la base.
Le corps multipart est lu en flux par le parseur bas niveau de python-multipart (callbacks,
aucun fichier) dans des bytearray, avec arrêt immédiat (413) dès qu'une partie dépasse
MAX_UPLOAD_BYTES. Aucun nom de fichier n'est journalisé.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path, PurePath
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import MultipartParser, parse_options_header

from . import assist, criteria as criteria_mod, db, erase, llm
from .config import DB_PATH, DEFAULT_MODEL, MAX_UPLOAD_BYTES, MODELS
from .types import Analysis, Criterion, ErasureProof
from .worker import Worker

# python-multipart journalise en DEBUG des en-têtes de parties (dont les noms de fichiers) : coupé.
for _name in ("python_multipart", "multipart", "python_multipart.multipart"):
    logging.getLogger(_name).setLevel(logging.ERROR)

MAX_FILES_PER_UPLOAD = 50
MAX_FIELD_BYTES = 1024

ModelKey = Literal["rapide", "precis"]


def db_path() -> Path:
    return Path(os.environ.get("COPILOT_DB") or DB_PATH)


# --- Cycle de vie -----------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    path = db_path()
    conn = db.connect(path)
    try:
        db.init(conn)
        job = db.get_job(conn)
        if not job["text"].strip():
            try:
                title, text = criteria_mod.load_job_text()
                db.set_job(conn, title, text)
            except FileNotFoundError:
                pass
        if not job["criteria"]:
            db.set_criteria(conn, criteria_mod.DEFAULT_CRITERIA)
    finally:
        conn.close()
    worker = Worker(path)
    worker.start()
    worker.recover()
    app.state.db_path = path
    app.state.worker = worker
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(title="Recruiter Copilot (local)", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None)


@app.middleware("http")
async def no_browser_cache(request: Request, call_next):
    """Aucune réponse de l'API n'est gardée dans le cache disque du navigateur :
    sinon une fiche candidat (texte masqué, analyse) survivrait à l'effacement, hors de la base."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


def get_conn(request: Request) -> Iterator:
    conn = db.connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


# --- Modèles de requête --------------------------------------------------------------
class ModelBody(BaseModel):
    model: ModelKey = DEFAULT_MODEL  # type: ignore[assignment]


class CriteriaBody(BaseModel):
    criteria: list[Criterion] = Field(min_length=1, max_length=12)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    model: ModelKey = DEFAULT_MODEL  # type: ignore[assignment]


def _criteria(conn) -> list[Criterion]:
    return [Criterion(**c) for c in db.get_job(conn)["criteria"]]


def _candidate_or_404(conn, cid: str) -> dict:
    cand = db.get_candidate(conn, cid)
    if cand is None:
        raise HTTPException(404, "Candidat introuvable.")
    return cand


# --- Santé / poste ---------------------------------------------------------------------
@app.get("/api/health")
def health():
    h = llm.health()
    return {**h, "model_keys": dict(MODELS)}


@app.get("/api/job")
def get_job(conn=Depends(get_conn)):
    return db.get_job(conn)


@app.put("/api/job/criteria")
def put_criteria(body: CriteriaBody, conn=Depends(get_conn)):
    ids = [c.id for c in body.criteria]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Identifiants de critères en double.")
    # Même contrôle que pour les critères proposés par le modèle : un critère discriminatoire
    # (âge, origine, santé, « culture fit »…) est refusé ; un critère ambigu passe avec un avertissement.
    rejected = [f"{c.label} : {criteria_mod.criterion_warning(c)}"
                for c in body.criteria if criteria_mod.is_discriminatory(c)]
    if rejected:
        raise HTTPException(422, "Critère refusé. " + " | ".join(rejected))
    warnings = {c.id: w for c in body.criteria if (w := criteria_mod.criterion_warning(c))}
    db.set_criteria(conn, body.criteria)
    return {"criteria": db.get_job(conn)["criteria"], "warnings": warnings}


@app.post("/api/job/criteria/suggest")
def suggest_criteria(body: ModelBody | None = None, conn=Depends(get_conn)):
    model = body.model if body else DEFAULT_MODEL
    text = db.get_job(conn)["text"]
    if not text.strip():
        raise HTTPException(409, "Aucune fiche de poste chargée.")
    try:
        crits = criteria_mod.suggest_criteria(text, model)
    except llm.LLMError as e:
        raise HTTPException(503, f"Modèle local indisponible : {e}") from None
    return {"criteria": [c.model_dump() for c in crits]}


# --- Upload (multipart en mémoire) ----------------------------------------------------------
class _TooLarge(Exception):
    pass


class _BadForm(Exception):
    pass


async def read_multipart(request: Request) -> tuple[list[tuple[str, bytes]], dict[str, str]]:
    """Lit un corps multipart/form-data en flux, tout en mémoire.

    Retourne ([(nom_fichier, octets)] pour le champ `files`, {champ: valeur} pour les autres).
    Lève _TooLarge dès qu'un fichier dépasse MAX_UPLOAD_BYTES (le reste du corps n'est pas lu).
    """
    ctype, params = parse_options_header(request.headers.get("content-type", ""))
    if ctype != b"multipart/form-data" or b"boundary" not in params:
        raise _BadForm("Corps multipart/form-data attendu.")

    files: list[tuple[str, bytes]] = []
    fields: dict[str, str] = {}
    cur: dict = {}
    hdr = {"name": b"", "value": b""}

    def on_part_begin():
        cur.clear()
        cur.update(headers={}, data=bytearray())

    def on_header_field(data, start, end):
        hdr["name"] += data[start:end]

    def on_header_value(data, start, end):
        hdr["value"] += data[start:end]

    def on_header_end():
        cur["headers"][hdr["name"].lower()] = hdr["value"]
        hdr["name"] = b""
        hdr["value"] = b""

    def on_headers_finished():
        _, opts = parse_options_header(cur["headers"].get(b"content-disposition", b""))
        if b"name" not in opts:
            raise _BadForm("Partie sans nom.")
        cur["name"] = opts[b"name"].decode("utf-8", "replace")
        cur["filename"] = opts[b"filename"].decode("utf-8", "replace") if b"filename" in opts else None
        if cur["filename"] is not None and len(files) >= MAX_FILES_PER_UPLOAD:
            raise _BadForm(f"Trop de fichiers (maximum {MAX_FILES_PER_UPLOAD} par envoi).")

    def on_part_data(data, start, end):
        buf: bytearray = cur["data"]
        limit = MAX_UPLOAD_BYTES if cur.get("filename") is not None else MAX_FIELD_BYTES
        if len(buf) + (end - start) > limit:
            raise _TooLarge()
        buf.extend(data[start:end])

    def on_part_end():
        if cur.get("filename") is not None:
            if cur["name"] == "files":
                files.append((cur["filename"], bytes(cur["data"])))
        else:
            fields[cur["name"]] = cur["data"].decode("utf-8", "replace")
        cur["data"] = bytearray()

    parser = MultipartParser(params[b"boundary"], {
        "on_part_begin": on_part_begin, "on_part_data": on_part_data, "on_part_end": on_part_end,
        "on_header_field": on_header_field, "on_header_value": on_header_value,
        "on_header_end": on_header_end, "on_headers_finished": on_headers_finished,
    })
    try:
        async for chunk in request.stream():
            parser.write(chunk)
        parser.finalize()
    except FormParserError:
        raise _BadForm("Corps multipart invalide.") from None
    return files, fields


def _display_name_from(filename: str) -> str:
    stem = PurePath(filename.replace("\\", "/")).stem.replace("_", " ").strip()
    return (" ".join(stem.split()) or "Candidat")[:80]


@app.post("/api/candidates")
async def upload_candidates(request: Request):
    try:
        files, fields = await read_multipart(request)
    except _TooLarge:
        raise HTTPException(413, f"Fichier trop volumineux (maximum {MAX_UPLOAD_BYTES // (1024 * 1024)} Mo "
                                 "par fichier). Aucun fichier de cet envoi n'a été importé.") from None
    except _BadForm as e:
        raise HTTPException(400, str(e)) from None
    if not files:
        raise HTTPException(400, "Aucun fichier reçu (champ « files »).")
    model = fields.get("model") or DEFAULT_MODEL
    if model not in MODELS:
        raise HTTPException(422, "Modèle inconnu (attendu : rapide ou precis).")

    worker: Worker = request.app.state.worker
    conn = db.connect(request.app.state.db_path)
    out = []
    try:
        for filename, data in files:
            name = _display_name_from(filename)
            cid = db.create_candidate(conn, name)
            worker.submit_file(cid, filename, data, model)
            out.append({"id": cid, "display_name": name, "status": "pending"})
    finally:
        conn.close()
    files.clear()
    return out


# --- Candidats -------------------------------------------------------------------------------
@app.get("/api/candidates")
def list_candidates(conn=Depends(get_conn)):
    return db.list_candidates(conn)   # ordre d'import (created_at), jamais par score


@app.get("/api/candidates/{cid}")
def get_candidate(cid: str, conn=Depends(get_conn)):
    return _candidate_or_404(conn, cid)


@app.post("/api/candidates/{cid}/reanalyze")
def reanalyze(cid: str, request: Request, body: ModelBody | None = None, conn=Depends(get_conn)):
    cand = _candidate_or_404(conn, cid)
    if cand["status"] in ("pending", "analyzing"):
        raise HTTPException(409, "Analyse déjà en cours.")
    if not cand["redacted_text"]:
        raise HTTPException(409, "Aucun texte enregistré pour ce candidat : réimporter le fichier.")
    reason = cand["reason"] if cand["reason"] and "scannée" in cand["reason"] else None
    try:
        db.set_status(conn, cid, "pending", reason)
    except db.CandidateNotFound:
        raise HTTPException(404, "Candidat introuvable.") from None
    request.app.state.worker.submit_reanalysis(cid, body.model if body else DEFAULT_MODEL)
    return {"status": "pending"}


def _ready_candidate(conn, cid: str) -> tuple[dict, Analysis]:
    cand = _candidate_or_404(conn, cid)
    if not cand["redacted_text"] or not cand["analysis"]:
        raise HTTPException(409, "Analyse pas encore disponible pour ce candidat.")
    return cand, Analysis(**cand["analysis"])


@app.post("/api/candidates/{cid}/questions")
def questions(cid: str, body: ModelBody | None = None, conn=Depends(get_conn)):
    cand, an = _ready_candidate(conn, cid)
    model = body.model if body else DEFAULT_MODEL
    try:
        qs = assist.interview_questions(cand["redacted_text"], an, _criteria(conn), model)
    except llm.LLMError as e:
        raise HTTPException(503, f"Modèle local indisponible : {e}") from None
    try:
        db.save_questions(conn, cid, qs)
    except db.CandidateNotFound:
        raise HTTPException(404, "Candidat effacé entre-temps.") from None
    return {"questions": [q.model_dump() for q in qs]}


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.post("/api/candidates/{cid}/ask")
def ask(cid: str, body: AskBody, conn=Depends(get_conn)):
    cand = _candidate_or_404(conn, cid)
    text = cand["redacted_text"]
    if not text:
        raise HTTPException(409, "Aucun texte disponible pour ce candidat.")

    def stream() -> Iterator[str]:
        # Rien n'est stocké : ni la question, ni la réponse.
        try:
            for tok in assist.answer_stream(text, body.question, body.model):
                yield _sse({"token": tok})
            yield _sse({"done": True})
        except llm.LLMError as e:
            yield _sse({"error": f"Modèle local indisponible : {e}"})
        except Exception as e:  # noqa: BLE001
            yield _sse({"error": f"Erreur interne ({type(e).__name__})."})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/compare")
def compare(conn=Depends(get_conn)):
    crits = db.get_job(conn)["criteria"]
    rows = []
    for c in db.list_candidates(conn):      # ordre d'import ; aucun score, aucun tri
        cand = db.get_candidate(conn, c["id"])
        if cand is None:
            continue
        cells = {}
        if cand["analysis"]:
            for ev in cand["analysis"]["evidence"]:
                cells[ev["criterion_id"]] = {"assessment": ev["assessment"], "quote": ev["quote"]}
        rows.append({"id": c["id"], "display_name": c["display_name"], "status": c["status"], "cells": cells})
    return {"criteria": crits, "candidates": rows}


@app.delete("/api/candidates/{cid}", response_model=ErasureProof)
def delete_candidate(cid: str, request: Request, conn=Depends(get_conn)):
    try:
        return erase.erase_candidate(conn, cid, request.app.state.db_path)
    except KeyError:
        raise HTTPException(404, "Candidat introuvable.") from None


@app.get("/api/erasures")
def erasures(conn=Depends(get_conn)):
    return db.list_erasures(conn)
