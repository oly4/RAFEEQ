from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LocalRoutine(Base):
    __tablename__ = "local_routines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(36), index=True)
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    configuration_version: Mapped[str] = mapped_column(String(200))


class LocalOccurrence(Base):
    __tablename__ = "local_occurrences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    routine_id: Mapped[str] = mapped_column(
        ForeignKey("local_routines.id", ondelete="CASCADE"), index=True
    )
    scheduled_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    snooze_count: Mapped[int] = mapped_column(Integer, default=0)
    prompted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocalEvent(Base):
    __tablename__ = "local_events"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    device_id: Mapped[str] = mapped_column(String(36))
    patient_id: Mapped[str] = mapped_column(String(36))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sequence: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class OutboxRecord(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(
        ForeignKey("local_events.event_id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SyncState(Base):
    __tablename__ = "sync_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
