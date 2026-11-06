"""Single background worker: processes queued tasks one at a time.

One worker + the global inference lock = sequential model execution, which
keeps memory usage predictable on a 16 GB RAM / 8 GB VRAM laptop. Task state
is persisted in the DB, so pending work is re-queued at startup.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from sqlalchemy import select

from app.db import new_session
from app.models import Analysis, Candidate, CandidateStatus

log = logging.getLogger(__name__)

TaskKind = str  # "candidate" | "analysis" | "interview"


class Worker:
    def __init__(self) -> None:
        self.q: "queue.Queue[tuple[TaskKind, str]]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.current: tuple[TaskKind, str] | None = None
        self._queued: set[tuple[TaskKind, str]] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------ public
    def enqueue(self, kind: TaskKind, ref: str) -> None:
        with self._lock:
            if (kind, ref) in self._queued:
                return
            self._queued.add((kind, ref))
        self.q.put((kind, ref))

    def pending_count(self) -> int:
        return self.q.qsize() + (1 if self.current else 0)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._requeue_unfinished()
        self._thread = threading.Thread(target=self._loop, name="rcl-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.q.put(("stop", ""))

    def drain(self) -> None:
        """Process everything synchronously (tests / CLI)."""
        while not self.q.empty():
            kind, ref = self.q.get()
            self._run(kind, ref)

    # ------------------------------------------------------------ internals
    def _requeue_unfinished(self) -> None:
        with new_session() as db:
            for c in db.execute(
                select(Candidate).where(Candidate.status.in_([CandidateStatus.PENDING, CandidateStatus.PROCESSING]))
            ).scalars():
                c.status = CandidateStatus.PENDING
                self.enqueue("candidate", c.id)
            for a in db.execute(select(Analysis).where(Analysis.status.in_(["pending", "processing"]))).scalars():
                a.status = "pending"
                self.enqueue(a.kind, a.id)
            db.commit()

    def _loop(self) -> None:
        while not self._stop.is_set():
            kind, ref = self.q.get()
            if kind == "stop":
                break
            self._run(kind, ref)

    def _run(self, kind: TaskKind, ref: str) -> None:
        with self._lock:
            self._queued.discard((kind, ref))
        self.current = (kind, ref)
        handler = _handlers().get(kind)
        try:
            if handler:
                with new_session() as db:
                    handler(db, ref)
        except Exception:  # noqa: BLE001 - the worker must never die
            log.exception("task failed kind=%s ref=%s", kind, ref)
        finally:
            self.current = None


def _handlers() -> dict[str, Callable]:
    from app.services.analysis import run_analysis
    from app.services.candidates import process_candidate
    from app.services.interview import run_interview

    return {"candidate": process_candidate, "analysis": run_analysis, "interview": run_interview}


worker = Worker()
