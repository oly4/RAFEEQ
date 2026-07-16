from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import select

from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.hardware.interfaces import SpeakerAdapter
from rafeeq_robot.persistence.database import RobotDatabase
from rafeeq_robot.persistence.models import LocalEvent, LocalOccurrence, LocalRoutine


@dataclass(frozen=True)
class RoutineTaskStatus:
    title: str
    routine_type: str
    status: str
    scheduled_at_utc: datetime


class ReminderService:
    def __init__(
        self,
        database: RobotDatabase,
        outbox: OutboxService,
        speaker: SpeakerAdapter,
    ) -> None:
        self.database = database
        self.outbox = outbox
        self.speaker = speaker

    def run_due(self, now: datetime | None = None) -> list[str]:
        current = now or datetime.now(timezone.utc)
        spoken: list[tuple[str, str]] = []
        with self.database.session() as session, session.begin():
            occurrences = list(
                session.scalars(
                    select(LocalOccurrence)
                    .where(
                        LocalOccurrence.status.in_(("pending", "snoozed")),
                        LocalOccurrence.scheduled_at_utc <= current,
                    )
                    .order_by(LocalOccurrence.scheduled_at_utc)
                ).all()
            )
            for occurrence in occurrences:
                routine = session.get(LocalRoutine, occurrence.routine_id)
                if routine is None:
                    continue
                medication = routine.payload_json.get("medication") or {}
                dosage = medication.get("dosage_text")
                message = f"حان موعد {routine.title}"
                if dosage:
                    message += f"، {dosage}"
                occurrence.status = "reminded"
                occurrence.prompted_at = current
                self.outbox.record_in_session(
                    session,
                    "reminder_spoken",
                    {"occurrence_id": occurrence.id, "routine_id": routine.id},
                    current,
                )
                spoken.append((occurrence.id, message))
        for _, message in spoken:
            self.speaker.speak(message, "ar")
        return [occurrence_id for occurrence_id, _ in spoken]

    def complete(self, occurrence_id: str, source: str = "manual") -> None:
        with self.database.session() as session, session.begin():
            occurrence = session.get(LocalOccurrence, occurrence_id)
            if occurrence is None:
                raise KeyError("Occurrence not found")
            if occurrence.status == "completed":
                return
            now = datetime.now(timezone.utc)
            occurrence.status = "completed"
            self.outbox.record_in_session(
                session,
                "reminder_completed",
                {"occurrence_id": occurrence.id, "confirmation_source": source},
                now,
            )

    def snooze(
        self,
        occurrence_id: str,
        minutes: int = 10,
        source: str = "patient_voice",
    ) -> None:
        with self.database.session() as session, session.begin():
            occurrence = session.get(LocalOccurrence, occurrence_id)
            if occurrence is None:
                raise KeyError("Occurrence not found")
            now = datetime.now(timezone.utc)
            occurrence.status = "snoozed"
            occurrence.snooze_count += 1
            occurrence.scheduled_at_utc = now + timedelta(minutes=minutes)
            self.outbox.record_in_session(
                session,
                "reminder_snoozed",
                {
                    "occurrence_id": occurrence.id,
                    "confirmation_source": source,
                    "snooze_minutes": minutes,
                },
                now,
            )

    def mark_missed(self, occurrence_id: str, source: str = "patient_voice") -> None:
        with self.database.session() as session, session.begin():
            occurrence = session.get(LocalOccurrence, occurrence_id)
            if occurrence is None:
                raise KeyError("Occurrence not found")
            now = datetime.now(timezone.utc)
            occurrence.status = "missed"
            self.outbox.record_in_session(
                session,
                "reminder_missed",
                {"occurrence_id": occurrence.id, "confirmation_source": source},
                now,
            )

    def latest_prompted_occurrence_id(self) -> str | None:
        with self.database.session() as session:
            occurrence = session.scalars(
                select(LocalOccurrence)
                .where(LocalOccurrence.status == "reminded")
                .order_by(LocalOccurrence.prompted_at.desc())
                .limit(1)
            ).first()
            return occurrence.id if occurrence else None

    def latest_completed_medication_at(self) -> datetime | None:
        with self.database.session() as session:
            events = session.scalars(
                select(LocalEvent)
                .where(LocalEvent.event_type == "reminder_completed")
                .order_by(LocalEvent.occurred_at.desc())
                .limit(20)
            ).all()
            for event in events:
                occurrence_id = event.payload_json.get("occurrence_id")
                if not isinstance(occurrence_id, str):
                    continue
                occurrence = session.get(LocalOccurrence, occurrence_id)
                if occurrence is None:
                    continue
                routine = session.get(LocalRoutine, occurrence.routine_id)
                if routine is not None and routine.type == "medication":
                    return event.occurred_at
            return None

    def find_task_status(self, query: str = "") -> RoutineTaskStatus | None:
        match = self._find_best_occurrence(query)
        if match is None:
            return None
        occurrence, routine = match
        return RoutineTaskStatus(
            title=routine.title,
            routine_type=routine.type,
            status=occurrence.status,
            scheduled_at_utc=occurrence.scheduled_at_utc,
        )

    def complete_best_match(self, query: str, source: str = "openai_voice") -> RoutineTaskStatus | None:
        return self._set_best_match_status(query, "completed", source)

    def snooze_best_match(
        self,
        query: str,
        minutes: int = 10,
        source: str = "openai_voice",
    ) -> RoutineTaskStatus | None:
        match = self._find_best_occurrence(query)
        if match is None:
            return None
        occurrence, routine = match
        self.snooze(occurrence.id, minutes, source)
        return RoutineTaskStatus(
            title=routine.title,
            routine_type=routine.type,
            status="snoozed",
            scheduled_at_utc=occurrence.scheduled_at_utc + timedelta(minutes=minutes),
        )

    def miss_best_match(self, query: str, source: str = "openai_voice") -> RoutineTaskStatus | None:
        return self._set_best_match_status(query, "missed", source)

    def undo_best_match_completion(
        self, query: str, source: str = "openai_voice"
    ) -> RoutineTaskStatus | None:
        match = self._find_best_occurrence(query, completed_only=True)
        if match is None:
            return None
        occurrence, routine = match
        now = datetime.now(timezone.utc)
        with self.database.session() as session, session.begin():
            stored = session.get(LocalOccurrence, occurrence.id)
            if stored is None:
                return None
            stored.status = "pending"
            self.outbox.record_in_session(
                session,
                "voice_task_completion_undone",
                {"occurrence_id": stored.id, "confirmation_source": source},
                now,
            )
        return RoutineTaskStatus(
            title=routine.title,
            routine_type=routine.type,
            status="pending",
            scheduled_at_utc=occurrence.scheduled_at_utc,
        )

    def _set_best_match_status(
        self, query: str, status: str, source: str
    ) -> RoutineTaskStatus | None:
        match = self._find_best_occurrence(query)
        if match is None:
            return None
        occurrence, routine = match
        if status == "completed":
            self.complete(occurrence.id, source)
        elif status == "missed":
            self.mark_missed(occurrence.id, source)
        else:
            raise ValueError(f"Unsupported status: {status}")
        return RoutineTaskStatus(
            title=routine.title,
            routine_type=routine.type,
            status=status,
            scheduled_at_utc=occurrence.scheduled_at_utc,
        )

    def _find_best_occurrence(
        self, query: str = "", completed_only: bool = False
    ) -> tuple[LocalOccurrence, LocalRoutine] | None:
        normalized_query = _normalize_text(query)
        with self.database.session() as session:
            statement = select(LocalOccurrence).order_by(LocalOccurrence.scheduled_at_utc.desc())
            if completed_only:
                statement = statement.where(LocalOccurrence.status == "completed")
            occurrences = list(session.scalars(statement).all())
            candidates: list[tuple[int, LocalOccurrence, LocalRoutine]] = []
            for occurrence in occurrences:
                routine = session.get(LocalRoutine, occurrence.routine_id)
                if routine is None:
                    continue
                score = _task_match_score(normalized_query, routine)
                candidates.append((score, occurrence, routine))
            if not candidates:
                return None
            candidates.sort(key=lambda item: (item[0], item[1].scheduled_at_utc), reverse=True)
            score, occurrence, routine = candidates[0]
            if normalized_query and score <= 0 and len(candidates) > 1:
                return None
            return occurrence, routine

    def list_task_statuses(self, limit: int = 20) -> list[RoutineTaskStatus]:
        with self.database.session() as session:
            occurrences = list(
                session.scalars(
                    select(LocalOccurrence)
                    .order_by(LocalOccurrence.scheduled_at_utc.desc())
                    .limit(limit)
                ).all()
            )
            statuses: list[RoutineTaskStatus] = []
            for occurrence in occurrences:
                routine = session.get(LocalRoutine, occurrence.routine_id)
                if routine is None:
                    continue
                statuses.append(
                    RoutineTaskStatus(
                        title=routine.title,
                        routine_type=routine.type,
                        status=occurrence.status,
                        scheduled_at_utc=occurrence.scheduled_at_utc,
                    )
                )
            return statuses


def _normalize_text(text: str) -> str:
    normalized = text.strip().casefold()
    normalized = normalized.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ٱ": "ا",
                "ى": "ي",
                "ؤ": "و",
                "ئ": "ي",
                "ة": "ه",
                "ـ": "",
            }
        )
    )
    normalized = re.sub(r"[\u064b-\u065f\u0670]", "", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _task_match_score(normalized_query: str, routine: LocalRoutine) -> int:
    if not normalized_query:
        return 0
    score = 0
    title = _normalize_text(routine.title)
    routine_type = _normalize_text(routine.type)
    title_words = [word for word in title.split() if len(word) > 2]
    score += sum(3 for word in title_words if word in normalized_query)
    if routine_type and routine_type in normalized_query:
        score += 2
    type_words = {
        "medication": ("دواء", "دوا", "medicine", "medication", "pill", "medcin", "medcine"),
        "meal": ("اكل", "غداء", "فطور", "عشاء", "meal", "food", "eat"),
        "water": ("ماء", "اشرب", "water", "drink"),
        "memory_exercise": ("ذاكره", "memory", "exercise"),
        "conversation": ("محادثه", "conversation", "talk"),
        "custom": ("مهمه", "نشاط", "task", "activity"),
        "custom_activity": ("مهمه", "نشاط", "task", "activity"),
    }
    score += sum(2 for word in type_words.get(routine.type, ()) if word in normalized_query)
    medication = routine.payload_json.get("medication") or {}
    for value in (
        medication.get("medication_name"),
        medication.get("dosage_text"),
        routine.payload_json.get("description"),
    ):
        if isinstance(value, str):
            value_words = [word for word in _normalize_text(value).split() if len(word) > 2]
            score += sum(2 for word in value_words if word in normalized_query)
    return score
