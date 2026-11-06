"""ORM models.

Every table holding candidate-derived data has a ``candidate_id`` foreign key
with ``ON DELETE CASCADE`` so deletion is consistent at the database level.
The deletion service additionally deletes explicitly and verifies counts.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.db import Base


class UTCDateTime(TypeDecorator):
    """SQLite drops tzinfo: store UTC, and re-attach UTC when loading."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class CandidateStatus:
    IMPORTED = "imported"
    PENDING = "pending"  # waiting for extraction
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ALL = (IMPORTED, PENDING, PROCESSING, COMPLETED, FAILED)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default=CandidateStatus.IMPORTED, index=True)
    processing_step: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str | None] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(10))
    file_size: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int | None] = mapped_column(Integer)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    injection_flags: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    possible_duplicates: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    text_row: Mapped["CandidateText | None"] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )
    profile_row: Mapped["CandidateProfile | None"] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )


class CandidateText(Base):
    __tablename__ = "candidate_texts"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), primary_key=True
    )
    text: Mapped[str] = mapped_column(Text)  # redacted text
    char_count: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(20))  # pdf_text | ocr | docx | txt
    redactions: Mapped[dict] = mapped_column(JSON, default=dict)  # category -> count
    sections: Mapped[list] = mapped_column(JSON, default=list)  # [{name,start,end}]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="text_row")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[dict] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="profile_row")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(60))
    text: Mapped[str] = mapped_column(Text)
    start_char: Mapped[int] = mapped_column(Integer)
    end_char: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(100))


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    optional_skills: Mapped[list] = mapped_column(JSON, default=list)
    experience_requirements: Mapped[str] = mapped_column(Text, default="")
    education_requirements: Mapped[str] = mapped_column(Text, default="")
    languages: Mapped[list] = mapped_column(JSON, default=list)
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("job_descriptions.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="analysis")  # analysis | interview
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|processing|completed|failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON)
    model: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), default="Conversation")
    job_id: Mapped[str | None] = mapped_column(ForeignKey("job_descriptions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    candidates: Mapped[list["ConversationCandidate"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="ChatMessage.id"
    )


class ConversationCandidate(Base):
    """Scope of a conversation. Deleting a candidate deletes every conversation
    that involved it (messages may contain the candidate's data)."""

    __tablename__ = "conversation_candidates"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class LifecycleEvent(Base):
    """Data-lifecycle / audit trail. Never contains personal data: only ids,
    event type and non-personal details (counts, durations, model names)."""

    __tablename__ = "lifecycle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class DeletionReport(Base):
    __tablename__ = "deletion_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_ref: Mapped[str] = mapped_column(String(36), index=True)  # former UUID only
    deleted_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    success: Mapped[bool] = mapped_column(Boolean)
    report: Mapped[dict] = mapped_column(JSON)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
