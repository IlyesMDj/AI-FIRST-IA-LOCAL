"""Effacement vérifiable d'un candidat → ErasureProof.

Étapes : chemin réel du .db (PRAGMA database_list) → extraits lus AVANT suppression
→ DELETE (CASCADE) dans une transaction → VACUUM (avec nouvelles tentatives ; secure_delete
a déjà mis à zéro les pages libérées) → vérification : lignes restantes par table + recherche
des extraits dans les octets bruts du .db (et d'un éventuel -journal / -wal)
→ journal (hash, date, preuve ; jamais de texte ni de nom), y compris en cas d'échec du VACUUM.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from . import db as dbm
from .config import DB_PATH
from .types import ErasureProof

EXTRACT_LEN = 24
MAX_EXTRACTS = 8
VACUUM_RETRIES = 4
VACUUM_RETRY_DELAY_S = 0.5


def _line_windows(text: str) -> list[str]:
    """Toutes les fenêtres candidates de EXTRACT_LEN caractères (début / milieu / fin de
    chaque ligne assez longue). Pas de saut de ligne : retrouvables aussi dans le JSON."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < EXTRACT_LEN:
            continue
        mid = (len(line) - EXTRACT_LEN) // 2
        for start in sorted({0, mid, len(line) - EXTRACT_LEN}):
            chunk = line[start:start + EXTRACT_LEN]
            if any(c in chunk for c in '[]"\\'):
                continue  # marqueurs de masquage communs / caractères échappés en JSON
            if sum(ch.isalnum() for ch in chunk) < EXTRACT_LEN // 2:
                continue
            out.append(chunk)
    return list(dict.fromkeys(out))


def _spread(items: list[str], n: int) -> list[str]:
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def _shared_elsewhere(conn: sqlite3.Connection, cid: str, s: str) -> bool:
    """Vrai si l'extrait existe aussi chez un autre candidat ou dans la fiche de poste :
    sa présence dans le fichier ne prouverait alors rien sur ce candidat."""
    q = [
        ("SELECT 1 FROM documents WHERE candidate_id<>? AND instr(redacted_text, ?) > 0", (cid, s)),
        ("SELECT 1 FROM analyses WHERE candidate_id<>? AND instr(json, ?) > 0", (cid, s)),
        ("SELECT 1 FROM evidence WHERE candidate_id<>? AND instr(quote, ?) > 0", (cid, s)),
        ("SELECT 1 FROM questions WHERE candidate_id<>? AND (instr(question, ?) > 0 OR instr(rationale, ?) > 0)",
         (cid, s, s)),
        ("SELECT 1 FROM candidates WHERE id<>? AND instr(display_name, ?) > 0", (cid, s)),
        ("SELECT 1 FROM job WHERE instr(title, ?) > 0 OR instr(text, ?) > 0", (s, s)),
        ("SELECT 1 FROM criteria WHERE instr(label, ?) > 0 OR instr(description, ?) > 0", (s, s)),
        ("SELECT 1 FROM erasure_log WHERE instr(proof_json, ?) > 0", (s,)),
    ]
    return any(conn.execute(sql, args).fetchone() for sql, args in q)


def _collect_extracts(conn: sqlite3.Connection, cid: str, display_name: str) -> list[str]:
    return _collect(conn, cid, display_name)[0]


def _collect(conn: sqlite3.Connection, cid: str, display_name: str) -> tuple[list[str], int]:
    """Extraits propres à ce candidat (ceux présents ailleurs sont écartés un par un,
    pas en bloc : un doublon partiel garde ses extraits uniques)."""
    def unique(items: list[str]) -> list[str]:
        return [e for e in items if not _shared_elsewhere(conn, cid, e)]

    extracts: list[str] = []
    doc = conn.execute("SELECT redacted_text FROM documents WHERE candidate_id=?", (cid,)).fetchone()
    if doc:
        extracts += _spread(unique(_line_windows(doc["redacted_text"])), MAX_EXTRACTS)
    n_doc = len(extracts)   # extraits issus du CV lui-même (le nom seul ne prouve rien)
    an = conn.execute("SELECT json FROM analyses WHERE candidate_id=?", (cid,)).fetchone()
    if an:
        summary = json.loads(an["json"]).get("summary") or ""
        extracts += _spread(unique(_line_windows(summary)), 2)
    for q in conn.execute("SELECT question FROM questions WHERE candidate_id=? LIMIT 2", (cid,)).fetchall():
        extracts += _spread(unique(_line_windows(q["question"])), 1)
    name = (display_name or "").strip()
    if len(name) >= 6:
        extracts += unique([name])
    return list(dict.fromkeys(extracts)), n_doc


def _candidate_tables(conn: sqlite3.Connection) -> list[str]:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    out = []
    for t in tables:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')}
        if "candidate_id" in cols:
            out.append(t)
    return out


def _real_db_path(conn: sqlite3.Connection) -> Path:
    """Chemin du fichier réellement ouvert (et non un paramètre qui pourrait mentir)."""
    for row in conn.execute("PRAGMA database_list"):
        if row[1] == "main":
            if not row[2]:
                raise RuntimeError("Base sans fichier (en mémoire) : effacement non vérifiable.")
            p = Path(row[2])
            if not p.is_file():
                raise FileNotFoundError(f"Fichier de base introuvable : {p}")
            return p
    raise RuntimeError("Base principale introuvable.")


def _raw_hits(db_path: Path, extracts: list[str]) -> int:
    """Occurrences des extraits dans les octets bruts. Le .db doit exister : jamais 0 silencieux."""
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(f"Fichier de base introuvable : {db_path}")
    hits = 0
    for p in (db_path, Path(str(db_path) + "-journal"), Path(str(db_path) + "-wal")):
        if not p.exists():
            continue
        raw = p.read_bytes()
        for e in extracts:
            hits += raw.count(e.encode("utf-8"))
    return hits


def _vacuum(conn: sqlite3.Connection) -> None:
    conn.execute("VACUUM")


def _vacuum_with_retry(conn: sqlite3.Connection) -> bool:
    for attempt in range(VACUUM_RETRIES):
        try:
            _vacuum(conn)
            return True
        except sqlite3.OperationalError:
            if attempt + 1 < VACUUM_RETRIES:
                time.sleep(VACUUM_RETRY_DELAY_S * (attempt + 1))
    return False


def erase_candidate(conn: sqlite3.Connection, cid: str, db_path: Path = DB_PATH) -> ErasureProof:
    """`db_path` est conservé pour compatibilité de signature ; le chemin vérifié est
    celui que SQLite a réellement ouvert (PRAGMA database_list)."""
    row = conn.execute("SELECT display_name FROM candidates WHERE id=?", (cid,)).fetchone()
    if row is None:
        raise KeyError(cid)
    real_path = _real_db_path(conn)          # échoue AVANT toute suppression

    # 1. Extraits lus AVANT suppression (restent en mémoire, jamais journalisés).
    had_document = conn.execute(
        "SELECT 1 FROM documents WHERE candidate_id=?", (cid,)).fetchone() is not None
    extracts, n_doc = _collect(conn, cid, row["display_name"])

    with dbm.WRITE_LOCK:
        # 2. Suppression en cascade, une transaction (si elle échoue : rien n'est effacé).
        with dbm.tx(conn):
            conn.execute("DELETE FROM candidates WHERE id=?", (cid,))
            for t in _candidate_tables(conn):   # filet si une table n'avait pas la cascade
                conn.execute(f'DELETE FROM "{t}" WHERE candidate_id=?', (cid,))

        # À partir d'ici, le candidat est effacé : la preuve est TOUJOURS journalisée.
        vacuum_ok = _vacuum_with_retry(conn)

        tables = {"candidates": conn.execute(
            "SELECT COUNT(*) FROM candidates WHERE id=?", (cid,)).fetchone()[0]}
        for t in _candidate_tables(conn):
            tables[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}" WHERE candidate_id=?', (cid,)).fetchone()[0]
        try:
            hits = _raw_hits(real_path, extracts)
            checked = len(extracts)
        except OSError:
            hits, checked, n_doc = 0, 0, 0            # vérification des octets impossible → non vérifié

        verified = (
            all(v == 0 for v in tables.values())
            and hits == 0
            and vacuum_ok
            and (n_doc > 0 or not had_document)
        )
        proof = ErasureProof(
            candidate_id_hash=hashlib.sha256(cid.encode("utf-8")).hexdigest(),
            erased_at=dbm.now_iso(),
            tables=tables,
            raw_file_hits=hits,
            extracts_checked=checked,
            vacuum_ok=vacuum_ok,
            verified=verified,
        )
        # 5. Journal : hash + date + preuve (aucun texte, aucun nom).
        with dbm.tx(conn):
            conn.execute(
                "INSERT INTO erasure_log(candidate_id_hash, erased_at, proof_json) VALUES (?,?,?)",
                (proof.candidate_id_hash, proof.erased_at, proof.model_dump_json()),
            )
    return proof
