"""SQLite : schéma + toutes les requêtes.

- journal_mode=MEMORY + temp_store=MEMORY : aucun -journal / -wal / fichier temporaire sur
  disque, donc aucune copie du CV hors du .db (contrepartie : un crash pendant une écriture
  peut corrompre la base). foreign_keys=ON (CASCADE), secure_delete=ON (pages libérées à zéro).
- Une connexion par requête côté API + un worker : les écritures sont sérialisées
  par un verrou module-level, en plus du verrou de fichier SQLite (busy timeout).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import DB_PATH
from .types import Analysis, Criterion, InterviewQuestion, RedactResult, Status

WRITE_LOCK = threading.RLock()


class CandidateNotFound(KeyError):
    """Le candidat n'existe pas (ou a été effacé entre-temps)."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS job (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    title TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS criteria (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    candidate_id TEXT PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
    redacted_text TEXT NOT NULL,
    removed_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses (
    candidate_id TEXT PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
    json TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    criterion_id TEXT NOT NULL,
    assessment TEXT NOT NULL,
    quote TEXT,
    start INTEGER,
    "end" INTEGER
);
CREATE INDEX IF NOT EXISTS idx_evidence_candidate ON evidence(candidate_id);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    rationale TEXT NOT NULL,
    criterion_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_questions_candidate ON questions(candidate_id);
CREATE TABLE IF NOT EXISTS erasure_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id_hash TEXT NOT NULL,
    erased_at TEXT NOT NULL,
    proof_json TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None : autocommit, transactions explicites via tx()
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=MEMORY")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA secure_delete=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Transaction d'écriture sérialisée (verrou module + BEGIN IMMEDIATE)."""
    with WRITE_LOCK:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")


def init(conn: sqlite3.Connection) -> None:
    with WRITE_LOCK:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO job(id, title, text) VALUES (1, '', '')")


def _require(conn: sqlite3.Connection, cid: str) -> None:
    if not candidate_exists(conn, cid):
        raise CandidateNotFound(f"candidat inconnu ou effacé : {cid}")


# --- Candidats ----------------------------------------------------------------
def create_candidate(conn: sqlite3.Connection, display_name: str) -> str:
    cid = uuid.uuid4().hex
    with tx(conn):
        conn.execute(
            "INSERT INTO candidates(id, display_name, status, reason, created_at) VALUES (?,?,?,?,?)",
            (cid, display_name, "pending", None, now_iso()),
        )
    return cid


def set_status(conn: sqlite3.Connection, cid: str, status: Status, reason: str | None = None) -> None:
    with tx(conn):
        _require(conn, cid)
        conn.execute("UPDATE candidates SET status=?, reason=? WHERE id=?", (status, reason, cid))


def set_display_name(conn: sqlite3.Connection, cid: str, name: str) -> None:
    with tx(conn):
        _require(conn, cid)
        conn.execute("UPDATE candidates SET display_name=? WHERE id=?", (name, cid))


def save_document(conn: sqlite3.Connection, cid: str, redacted: RedactResult) -> None:
    with tx(conn):
        _require(conn, cid)
        conn.execute(
            "INSERT OR REPLACE INTO documents(candidate_id, redacted_text, removed_json) VALUES (?,?,?)",
            (cid, redacted.text, json.dumps(redacted.removed, ensure_ascii=False)),
        )


def save_analysis(conn: sqlite3.Connection, cid: str, analysis: Analysis) -> None:
    with tx(conn):
        _require(conn, cid)
        conn.execute("DELETE FROM evidence WHERE candidate_id=?", (cid,))
        conn.execute("DELETE FROM analyses WHERE candidate_id=?", (cid,))
        conn.execute(
            "INSERT INTO analyses(candidate_id, json, model, prompt_version, created_at) VALUES (?,?,?,?,?)",
            (cid, analysis.model_dump_json(), analysis.model, analysis.prompt_version, now_iso()),
        )
        conn.executemany(
            'INSERT INTO evidence(candidate_id, criterion_id, assessment, quote, start, "end") VALUES (?,?,?,?,?,?)',
            [(cid, e.criterion_id, e.assessment, e.quote, e.start, e.end) for e in analysis.evidence],
        )


def save_questions(conn: sqlite3.Connection, cid: str, qs: list[InterviewQuestion]) -> None:
    with tx(conn):
        _require(conn, cid)
        conn.execute("DELETE FROM questions WHERE candidate_id=?", (cid,))
        conn.executemany(
            "INSERT INTO questions(candidate_id, question, rationale, criterion_id) VALUES (?,?,?,?)",
            [(cid, q.question, q.rationale, q.criterion_id) for q in qs],
        )


def candidate_exists(conn: sqlite3.Connection, cid: str) -> bool:
    return conn.execute("SELECT 1 FROM candidates WHERE id=?", (cid,)).fetchone() is not None


_CAND_COLS = "id, display_name, status, reason, created_at"


def list_candidates(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(f"SELECT {_CAND_COLS} FROM candidates ORDER BY created_at, rowid").fetchall()
    return [dict(r) for r in rows]


def get_candidate(conn: sqlite3.Connection, cid: str) -> dict | None:
    row = conn.execute(f"SELECT {_CAND_COLS} FROM candidates WHERE id=?", (cid,)).fetchone()
    if row is None:
        return None
    out = dict(row)
    doc = conn.execute(
        "SELECT redacted_text, removed_json FROM documents WHERE candidate_id=?", (cid,)
    ).fetchone()
    out["redacted_text"] = doc["redacted_text"] if doc else None
    out["removed"] = json.loads(doc["removed_json"]) if doc else {}
    an = conn.execute("SELECT json FROM analyses WHERE candidate_id=?", (cid,)).fetchone()
    out["analysis"] = Analysis.model_validate_json(an["json"]).model_dump() if an else None
    qs = conn.execute(
        "SELECT question, rationale, criterion_id FROM questions WHERE candidate_id=? ORDER BY id", (cid,)
    ).fetchall()
    out["questions"] = [InterviewQuestion(**dict(q)).model_dump() for q in qs]
    return out


# --- Poste / critères ---------------------------------------------------------
def get_job(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT title, text FROM job WHERE id=1").fetchone()
    crits = conn.execute("SELECT id, label, description FROM criteria ORDER BY position, id").fetchall()
    return {
        "title": row["title"] if row else "",
        "text": row["text"] if row else "",
        "criteria": [Criterion(**dict(c)).model_dump() for c in crits],
    }


def set_job(conn: sqlite3.Connection, title: str, text: str) -> None:
    with tx(conn):
        conn.execute(
            "INSERT INTO job(id, title, text) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, text=excluded.text",
            (title, text),
        )


def set_criteria(conn: sqlite3.Connection, criteria: list[Criterion]) -> None:
    with tx(conn):
        conn.execute("DELETE FROM criteria")
        conn.executemany(
            "INSERT INTO criteria(id, label, description, position) VALUES (?,?,?,?)",
            [(c.id, c.label, c.description, i) for i, c in enumerate(criteria)],
        )


# --- Journal d'effacement -----------------------------------------------------
def list_erasures(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT proof_json FROM erasure_log ORDER BY id DESC").fetchall()
    return [json.loads(r["proof_json"]) for r in rows]
