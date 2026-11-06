"""File d'analyse en tâche de fond : UNE file, UN seul thread (l'inférence est CPU).

Pipeline par candidat importé :
  extract → (vision si scanné / pages scannées) → redact → db.save_document
  → analysis.analyze → db.save_analysis (+ display_name) → ready.

Confidentialité :
- les octets du fichier et le texte brut ne vivent qu'en mémoire (dans la tâche de la file)
  et sont libérés dès que le texte masqué est enregistré ;
- aucune journalisation de nom, de nom de fichier ni de texte : les raisons d'erreur
  enregistrées sont des phrases fixes en français, jamais un extrait du CV ;
- un candidat effacé pendant son analyse (db.CandidateNotFound) est abandonné en silence.
"""
from __future__ import annotations

import queue
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from . import analysis, db, llm, redact as redact_mod
from .extract import extract
from .types import Criterion

INTERRUPTED_REASON = "Import interrompu : réimporter le fichier."


@dataclass
class _FileJob:
    cid: str
    filename: str
    data: bytes | None          # octets du fichier, en mémoire seulement
    model: str


@dataclass
class _DocJob:
    """Ré-analyse à partir du texte masqué déjà enregistré."""
    cid: str
    model: str


_STOP = object()


def _short_reason(exc: BaseException) -> str:
    """Raison courte, en français, sans aucun contenu du CV."""
    if isinstance(exc, llm.LLMError):
        # Messages de llm/analysis : construits par le code (nom de type, clé de modèle), jamais le CV.
        return f"Analyse impossible (modèle local) : {str(exc)[:160]}"
    if isinstance(exc, ValueError) and str(exc) == "aucun critère":
        return "Analyse impossible : aucun critère défini pour le poste."
    return f"Erreur interne pendant l'analyse ({type(exc).__name__})."


class Worker:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._conn: sqlite3.Connection | None = None
        self.current: str | None = None          # id en cours (utile aux tests)

    # --- cycle de vie ----------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._conn = db.connect(self.db_path)
        self._thread = threading.Thread(target=self._run, name="copilot-analysis", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._q.put(_STOP)
        if self._thread:
            self._thread.join(timeout)
        self._thread = None

    def recover(self) -> int:
        """Au démarrage : relance les analyses interrompues. Retourne le nombre relancé."""
        conn = db.connect(self.db_path)
        n = 0
        try:
            for c in db.list_candidates(conn):
                if c["status"] not in ("pending", "analyzing"):
                    continue
                has_doc = conn.execute(
                    "SELECT 1 FROM documents WHERE candidate_id=?", (c["id"],)).fetchone() is not None
                try:
                    if has_doc:
                        db.set_status(conn, c["id"], "pending")
                        self.submit_reanalysis(c["id"], "rapide")
                        n += 1
                    else:
                        db.set_status(conn, c["id"], "error", INTERRUPTED_REASON)
                except db.CandidateNotFound:
                    pass
        finally:
            conn.close()
        return n

    # --- soumission ---------------------------------------------------------------
    def submit_file(self, cid: str, filename: str, data: bytes, model: str) -> None:
        self._q.put(_FileJob(cid, filename, data, model))

    def submit_reanalysis(self, cid: str, model: str) -> None:
        self._q.put(_DocJob(cid, model))

    def idle(self) -> bool:
        return self._q.unfinished_tasks == 0

    def join(self) -> None:
        """Attend que la file soit vide (tests)."""
        self._q.join()

    # --- boucle -------------------------------------------------------------------
    def _run(self) -> None:
        while True:
            job = self._q.get()
            try:
                if job is _STOP:
                    return
                self.current = job.cid
                self._process(job)
            except Exception:
                # Dernier filet : ne jamais tuer le thread. Rien n'est journalisé (pas de contenu).
                pass
            finally:
                self.current = None
                job = None  # libère les octets du fichier
                self._q.task_done()

    def _process(self, job) -> None:
        conn = self._conn
        assert conn is not None
        cid = job.cid
        try:
            db.set_status(conn, cid, "analyzing")
            note: str | None = None
            if isinstance(job, _FileJob):
                redacted_text, note, unsupported = self._ingest(conn, job)
                if unsupported is not None:
                    db.set_status(conn, cid, "unsupported", unsupported)
                    return
            else:
                cand = db.get_candidate(conn, cid)
                if cand is None:
                    return
                redacted_text = cand["redacted_text"]
                if not redacted_text:
                    db.set_status(conn, cid, "error", INTERRUPTED_REASON)
                    return
                note = cand["reason"] if cand["reason"] and "scannée" in cand["reason"] else None

            crits = [Criterion(**c) for c in db.get_job(conn)["criteria"]]
            result = analysis.analyze(redacted_text, crits, job.model)
            db.save_analysis(conn, cid, result)
            if result.display_name:
                db.set_display_name(conn, cid, result.display_name)
            db.set_status(conn, cid, "ready", note)
        except db.CandidateNotFound:
            return  # effacé pendant l'analyse : abandon silencieux
        except Exception as e:  # noqa: BLE001
            try:
                db.set_status(conn, cid, "error", _short_reason(e))
            except db.CandidateNotFound:
                pass

    def _ingest(self, conn: sqlite3.Connection, job: _FileJob) -> tuple[str, str | None, str | None]:
        """Fichier → texte masqué enregistré. Retourne (texte masqué, note, raison_unsupported)."""
        data, job.data = job.data, None
        res = extract(job.filename, data or b"")
        del data
        if res.status == "unsupported":
            return "", None, res.reason or "Fichier illisible."
        raw = res.text or ""
        note: str | None = None
        if res.page_images:
            vision = llm.vision_to_text(job.model, res.page_images)
            res.page_images = []
            if res.status == "needs_vision":
                raw = vision
            else:
                raw = (raw + "\n\n" + vision) if vision else raw
                note = res.reason  # « pages N,M scannées » : affiché sur la fiche
        elif res.status == "needs_vision":
            return "", None, res.reason or "Document scanné sans image exploitable."
        res.text = None
        if not raw.strip():
            return "", None, "Aucun texte lisible dans ce fichier."
        red = redact_mod.redact(raw)
        del raw
        db.save_document(conn, job.cid, red)
        return red.text, note, None
