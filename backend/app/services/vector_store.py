"""Chunking + embedding storage + candidate-isolated semantic search.

Vectors live in the ``chunks`` table (float32 BLOB) next to the text they
represent. Every search *requires* an explicit set of candidate ids and the
SQL query filters on it before any similarity is computed, so a question
about candidate A can never retrieve text from candidate B. Deleting the
candidate's rows deletes the vectors in the same transaction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Chunk
from app.services.documents import section_at

log = logging.getLogger(__name__)

CHUNK_SIZE = 700
CHUNK_OVERLAP = 120


def split_chunks(text: str, sections: list[dict]) -> list[dict]:
    """Split by section, then into ~CHUNK_SIZE windows on line boundaries."""
    chunks: list[dict] = []
    spans = sections or [{"name": "header", "start": 0, "end": len(text)}]
    for sec in spans:
        s, e = sec["start"], sec["end"]
        pos = s
        while pos < e:
            end = min(e, pos + CHUNK_SIZE)
            if end < e:
                nl = text.rfind("\n", pos + CHUNK_SIZE // 2, end)
                if nl != -1:
                    end = nl
            piece = text[pos:end].strip()
            if len(piece) > 15:
                chunks.append({"section": sec["name"], "text": piece, "start": pos, "end": end})
            if end >= e:
                break
            pos = max(end - CHUNK_OVERLAP, pos + 1)
            # realign to a line start to keep chunks readable
            nl = text.find("\n", pos, end)
            if nl != -1:
                pos = nl + 1
    return chunks


def store_chunks(db: Session, candidate_id: str, text: str, sections: list[dict]) -> list[Chunk]:
    db.execute(delete(Chunk).where(Chunk.candidate_id == candidate_id))
    rows = []
    for i, c in enumerate(split_chunks(text, sections)):
        row = Chunk(
            candidate_id=candidate_id,
            ordinal=i,
            section=c["section"] or section_at(sections, c["start"]),
            text=c["text"],
            start_char=c["start"],
            end_char=c["end"],
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def attach_embeddings(rows: list[Chunk], vectors: list[list[float]], model: str) -> None:
    for row, vec in zip(rows, vectors):
        arr = np.asarray(vec, dtype=np.float32)
        n = np.linalg.norm(arr)
        if n > 0:
            arr = arr / n
        row.embedding = arr.tobytes()
        row.embedding_model = model


@dataclass
class Hit:
    chunk_id: int
    candidate_id: str
    ordinal: int
    section: str
    text: str
    start: int
    end: int
    score: float


def _keyword_score(query_terms: set[str], text: str) -> float:
    low = text.lower()
    return sum(1 for t in query_terms if t in low) / max(1, len(query_terms))


def search(
    db: Session,
    candidate_ids: list[str],
    query: str,
    query_vec: list[float] | None,
    *,
    top_k: int = 6,
    per_candidate: int | None = None,
) -> list[Hit]:
    if not candidate_ids:
        raise ValueError("candidate scope is required")
    rows = db.execute(select(Chunk).where(Chunk.candidate_id.in_(candidate_ids))).scalars().all()
    if not rows:
        return []
    terms = {t for t in query.lower().replace(",", " ").split() if len(t) > 2}
    scores: list[float] = []
    qv = None
    if query_vec is not None:
        qv = np.asarray(query_vec, dtype=np.float32)
        qv = qv / (np.linalg.norm(qv) or 1.0)
    for r in rows:
        kw = _keyword_score(terms, r.text) if terms else 0.0
        if qv is not None and r.embedding:
            v = np.frombuffer(r.embedding, dtype=np.float32)
            sem = float(v @ qv) if v.shape == qv.shape else 0.0
            scores.append(0.8 * sem + 0.2 * kw)
        else:
            scores.append(kw)
    order = np.argsort(scores)[::-1]
    hits: list[Hit] = []
    taken: dict[str, int] = {}
    for i in order:
        r = rows[int(i)]
        if per_candidate is not None and taken.get(r.candidate_id, 0) >= per_candidate:
            continue
        taken[r.candidate_id] = taken.get(r.candidate_id, 0) + 1
        hits.append(Hit(r.id, r.candidate_id, r.ordinal, r.section, r.text, r.start_char, r.end_char, round(float(scores[int(i)]), 4)))
        if per_candidate is None and len(hits) >= top_k:
            break
        if per_candidate is not None and len(hits) >= per_candidate * len(candidate_ids):
            break
    return hits
