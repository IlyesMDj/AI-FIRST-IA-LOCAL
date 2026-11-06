"""Lifecycle / audit events. Details must never contain personal data."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import LifecycleEvent

log = logging.getLogger("lifecycle")

_FORBIDDEN_KEYS = {"name", "email", "phone", "text", "filename", "content", "quote"}


def record(db: Session, event_type: str, *, candidate_id: str | None = None, job_id: str | None = None, **details) -> None:
    safe = {k: v for k, v in details.items() if k not in _FORBIDDEN_KEYS}
    db.add(LifecycleEvent(event_type=event_type, candidate_id=candidate_id, job_id=job_id, details=safe))
    log.info("event=%s candidate=%s job=%s %s", event_type, candidate_id, job_id, safe)
