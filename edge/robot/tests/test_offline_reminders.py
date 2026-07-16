from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import httpx
from sqlalchemy import func, select

from rafeeq_robot.application.emergency_manager import EmergencyManager
from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.application.reminder_service import ReminderService
from rafeeq_robot.persistence.database import RobotDatabase
from rafeeq_robot.persistence.models import (
    LocalEvent,
    LocalOccurrence,
    LocalRoutine,
    OutboxRecord,
)

DEVICE_ID = "00000000-0000-0000-0000-000000000001"
PATIENT_ID = "00000000-0000-0000-0000-000000000002"


class FakeSpeaker:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def speak(self, text: str, locale: str = "ar") -> None:
        self.messages.append(text)


def create_database(tmp_path: Path) -> RobotDatabase:
    return RobotDatabase(str(tmp_path / "robot.db"))


def seed_due_reminder(database: RobotDatabase) -> str:
    occurrence_id = "00000000-0000-0000-0000-000000000004"
    with database.session() as session, session.begin():
        session.add(
            LocalRoutine(
                id="00000000-0000-0000-0000-000000000003",
                patient_id=PATIENT_ID,
                type="medication",
                title="دواء الصباح",
                payload_json={"medication": {"dosage_text": "حبة واحدة"}},
                configuration_version="v1",
            )
        )
        session.add(
            LocalOccurrence(
                id=occurrence_id,
                routine_id="00000000-0000-0000-0000-000000000003",
                scheduled_at_utc=datetime.now(timezone.utc) - timedelta(minutes=1),
                status="pending",
            )
        )
    return occurrence_id


def test_due_reminder_runs_offline_once_after_restart(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    occurrence_id = seed_due_reminder(database)
    speaker = FakeSpeaker()
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID)
    service = ReminderService(database, outbox, speaker)
    assert service.run_due() == [occurrence_id]
    assert len(speaker.messages) == 1

    restarted = ReminderService(create_database(tmp_path), outbox, speaker)
    assert restarted.run_due() == []
    assert len(speaker.messages) == 1


def test_completion_and_sos_are_transactionally_queued(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    occurrence_id = seed_due_reminder(database)
    speaker = FakeSpeaker()
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID)
    reminders = ReminderService(database, outbox, speaker)
    reminders.complete(occurrence_id, "patient_voice")
    EmergencyManager(outbox, speaker).trigger_sos()
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(LocalEvent)) == 2
        assert session.scalar(select(func.count()).select_from(OutboxRecord)) == 2
        occurrence = session.get(LocalOccurrence, occurrence_id)
        assert occurrence.status == "completed"
    assert any("المساعدة" in message for message in speaker.messages)


def test_outbox_acknowledgement_marks_event_synced_once(tmp_path: Path) -> None:
    database = create_database(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        event_id = json.loads(request.read().decode("utf-8"))["events"][0]["event_id"]
        return httpx.Response(200, json={"items": [{"event_id": event_id, "status": "processed"}]})

    client = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID, client)
    outbox.record("sos_pressed", {})
    assert outbox.publish_pending() == 1
    assert outbox.publish_pending() == 0
    with database.session() as session:
        assert session.scalar(select(OutboxRecord.status)) == "synced"


def test_fall_detector_only_creates_verification_events_not_notifications(
    tmp_path: Path,
) -> None:
    database = create_database(tmp_path)
    speaker = FakeSpeaker()
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID)
    manager = EmergencyManager(outbox, speaker)
    possible_event_id = manager.trigger_possible_fall(0.82, ["mock_trigger"])
    manager.finish_fall_verification("safe")
    with database.session() as session:
        events = list(session.scalars(select(LocalEvent).order_by(LocalEvent.sequence)).all())
    assert [event.event_type for event in events] == [
        "possible_fall_detected",
        "fall_verification_result",
    ]
    assert events[1].payload_json == {
        "related_event_id": possible_event_id,
        "outcome": "safe",
    }
