from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.application.openai_voice_agent import OpenAIRealtimeVoiceAgent
from rafeeq_robot.application.reminder_service import ReminderService
from rafeeq_robot.application.voice_interactor import VoiceIntentRouter
from rafeeq_robot.main import (
    _extract_wake_command,
    _is_followup_candidate,
    _is_actionable_followup,
    _is_quiet_command,
    _language_switch_locale,
    _local_app_action,
)
from rafeeq_robot.persistence.database import RobotDatabase
from rafeeq_robot.persistence.models import LocalEvent, LocalOccurrence, LocalRoutine

DEVICE_ID = "00000000-0000-0000-0000-000000000001"
PATIENT_ID = "00000000-0000-0000-0000-000000000002"
ROUTINE_ID = "00000000-0000-0000-0000-000000000003"
OCCURRENCE_ID = "00000000-0000-0000-0000-000000000004"


class FakeSpeaker:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def speak(self, text: str, locale: str = "ar") -> None:
        self.messages.append(text)


def create_database(tmp_path: Path) -> RobotDatabase:
    return RobotDatabase(str(tmp_path / "robot.db"))


def seed_prompted_medication(database: RobotDatabase) -> None:
    with database.session() as session, session.begin():
        session.add(
            LocalRoutine(
                id=ROUTINE_ID,
                patient_id=PATIENT_ID,
                type="medication",
                title="Morning medicine",
                payload_json={"medication": {"dosage_text": "one tablet"}},
                configuration_version="v1",
            )
        )
        session.add(
            LocalOccurrence(
                id=OCCURRENCE_ID,
                routine_id=ROUTINE_ID,
                scheduled_at_utc=datetime.now(timezone.utc) - timedelta(minutes=1),
                status="reminded",
                prompted_at=datetime.now(timezone.utc),
            )
        )


def seed_completed_medication(database: RobotDatabase, outbox: OutboxService) -> None:
    completed_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    with database.session() as session, session.begin():
        session.add(
            LocalRoutine(
                id=ROUTINE_ID,
                patient_id=PATIENT_ID,
                type="medication",
                title="Morning medicine",
                payload_json={"medication": {"dosage_text": "one tablet"}},
                configuration_version="v1",
            )
        )
        session.add(
            LocalOccurrence(
                id=OCCURRENCE_ID,
                routine_id=ROUTINE_ID,
                scheduled_at_utc=completed_at,
                status="completed",
                prompted_at=completed_at,
            )
        )
        outbox.record_in_session(
            session,
            "reminder_completed",
            {"occurrence_id": OCCURRENCE_ID, "confirmation_source": "patient_voice"},
            completed_at,
        )


def seed_task(database: RobotDatabase, title: str, status: str) -> None:
    with database.session() as session, session.begin():
        session.add(
            LocalRoutine(
                id=ROUTINE_ID,
                patient_id=PATIENT_ID,
                type="custom_activity",
                title=title,
                payload_json={"description": title},
                configuration_version="v1",
            )
        )
        session.add(
            LocalOccurrence(
                id=OCCURRENCE_ID,
                routine_id=ROUTINE_ID,
                scheduled_at_utc=datetime.now(timezone.utc) - timedelta(minutes=10),
                status=status,
                prompted_at=None,
            )
        )


def create_router(
    database: RobotDatabase,
    speaker: FakeSpeaker,
    snooze_minutes: int = 10,
) -> VoiceIntentRouter:
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID)
    reminders = ReminderService(database, outbox, speaker)
    return VoiceIntentRouter(reminders, outbox, speaker, snooze_minutes=snooze_minutes)


def test_voice_confirmation_completes_latest_prompted_reminder(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    seed_prompted_medication(database)
    speaker = FakeSpeaker()
    router = create_router(database, speaker)

    result = router.handle_text("yes I took it")

    assert result.intent == "confirm_reminder"
    assert result.handled is True
    with database.session() as session:
        occurrence = session.get(LocalOccurrence, OCCURRENCE_ID)
        assert occurrence is not None
        assert occurrence.status == "completed"
        events = list(session.scalars(select(LocalEvent).order_by(LocalEvent.sequence)).all())
    assert [event.event_type for event in events] == [
        "voice_command_recognized",
        "reminder_completed",
    ]
    assert events[0].payload_json == {
        "intent": "confirm_reminder",
        "confidence": 0.95,
        "source": "simulated_text",
    }


def test_voice_snooze_reschedules_without_storing_transcript(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    seed_prompted_medication(database)
    speaker = FakeSpeaker()
    router = create_router(database, speaker, snooze_minutes=15)

    result = router.handle_text("remind me later after lunch")

    assert result.intent == "snooze_reminder"
    assert result.handled is True
    with database.session() as session:
        occurrence = session.get(LocalOccurrence, OCCURRENCE_ID)
        assert occurrence is not None
        assert occurrence.status == "snoozed"
        assert occurrence.snooze_count == 1
        events = list(session.scalars(select(LocalEvent).order_by(LocalEvent.sequence)).all())
    assert events[0].payload_json["intent"] == "snooze_reminder"
    assert "transcript" not in events[0].payload_json
    assert "audio" not in events[0].payload_json
    assert events[1].payload_json["snooze_minutes"] == 15


def test_voice_answers_medication_status_out_loud(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID)
    seed_completed_medication(database, outbox)
    speaker = FakeSpeaker()
    reminders = ReminderService(database, outbox, speaker)
    router = VoiceIntentRouter(reminders, outbox, speaker)

    result = router.handle_text("هل أخذت الدواء")

    assert result.intent == "medication_status_question"
    assert result.handled is True
    assert speaker.messages[-1] == "Yes, the medicine was taken about half an hour ago."
    with database.session() as session:
        events = list(session.scalars(select(LocalEvent).order_by(LocalEvent.sequence)).all())
    assert events[-1].payload_json["intent"] == "medication_status_question"


def test_voice_understands_natural_medicine_status_request(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID)
    seed_completed_medication(database, outbox)
    speaker = FakeSpeaker()
    reminders = ReminderService(database, outbox, speaker)
    router = VoiceIntentRouter(reminders, outbox, speaker)

    result = router.handle_text("I want you to let me know if I eat my medcin or not")

    assert result.intent == "medication_status_question"
    assert result.handled is True
    assert speaker.messages[-1] == "Yes, the medicine was taken about half an hour ago."


def test_voice_does_not_claim_medication_was_taken_without_record(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    speaker = FakeSpeaker()
    router = create_router(database, speaker)

    result = router.handle_text("هل اخذت الدواء")

    assert result.intent == "medication_status_question"
    assert result.handled is False
    assert speaker.messages[-1] == "I do not have a record that the medicine was taken yet."


def test_voice_answers_completed_app_task_status(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    seed_task(database, "Lunch", "completed")
    speaker = FakeSpeaker()
    router = create_router(database, speaker)

    result = router.handle_text("did I finish lunch or not")

    assert result.intent == "task_status_question"
    assert result.handled is True
    assert speaker.messages[-1] == "Yes, Lunch is recorded as completed."


def test_voice_answers_pending_app_task_status(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    seed_task(database, "Memory exercise", "pending")
    speaker = FakeSpeaker()
    router = create_router(database, speaker)

    result = router.handle_text("check memory exercise task status")

    assert result.intent == "task_status_question"
    assert result.handled is False
    assert speaker.messages[-1] == "No, Memory exercise is not recorded as completed yet."


def test_openai_voice_agent_without_key_uses_local_fallback(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    seed_task(database, "Lunch", "completed")
    speaker = FakeSpeaker()
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID)
    reminders = ReminderService(database, outbox, speaker)
    local_router = VoiceIntentRouter(reminders, outbox, speaker)
    agent = OpenAIRealtimeVoiceAgent(
        local_router,
        reminders,
        speaker,
        api_key="",
        model="gpt-realtime-2.1",
        text_model="gpt-5.4",
        reasoning_effort="low",
    )

    result = agent.handle_text("did I finish lunch or not")

    assert result.intent == "task_status_question"
    assert result.handled is True
    assert speaker.messages[-1] == "Yes, Lunch is recorded as completed."


def test_openai_add_routine_action_records_create_event(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    speaker = FakeSpeaker()
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID)
    reminders = ReminderService(database, outbox, speaker)
    local_router = VoiceIntentRouter(reminders, outbox, speaker)
    agent = OpenAIRealtimeVoiceAgent(
        local_router,
        reminders,
        speaker,
        api_key="test",
        model="gpt-realtime-2.1",
        text_model="gpt-5.4",
        reasoning_effort="low",
    )

    message = agent._execute_plan(
        {
            "action": "add_routine",
            "routine": {
                "title": "Dentist appointment",
                "type": "appointment",
                "time_24h": "20:00",
            },
        },
        "add appointment dentist at 8 pm",
        "test",
        "en",
    )

    assert message == "Done. I added the task."
    with database.session() as session:
        events = list(session.scalars(select(LocalEvent).order_by(LocalEvent.sequence)).all())
    assert [event.event_type for event in events] == ["voice_routine_create"]
    assert events[0].payload_json["routine"]["title"] == "Dentist appointment"


def test_voice_router_can_switch_preferred_locale_to_arabic(tmp_path: Path) -> None:
    database = create_database(tmp_path)
    outbox = OutboxService(database, DEVICE_ID, PATIENT_ID)
    seed_completed_medication(database, outbox)
    speaker = FakeSpeaker()
    reminders = ReminderService(database, outbox, speaker)
    router = VoiceIntentRouter(reminders, outbox, speaker)
    router.set_preferred_locale("ar")

    result = router.handle_text("did I take my medicine")

    assert result.intent == "medication_status_question"
    assert result.handled is True
    assert speaker.messages[-1] == "نعم، لقد أخذت الدواء قبل نصف ساعة."


def test_voice_quiet_command_understands_english_typos_and_arabic() -> None:
    assert _is_quiet_command("be quiet")
    assert _is_quiet_command("be quite")
    assert _is_quiet_command("silnte")
    assert _is_quiet_command("اسكت يا رفيق")


def test_paused_voice_can_resume_with_wake_word_only() -> None:
    assert _extract_wake_command("Rafeeq", "يا رفيق,rafeeq") == ""
    assert _extract_wake_command("يا رفيق", "يا رفيق,rafeeq") == ""
    assert _extract_wake_command("توفيق، ابدأ اختبار الذاكرة", "يا رفيق,rafeeq") == "ابدأ اختبار الذاكره"
    assert _extract_wake_command("حفيق؟", "يا رفيق,rafeeq") == ""
    assert _extract_wake_command("Rafiq?", "يا رفيق,rafeeq") == ""
    assert _extract_wake_command("Rafeeq add task", "يا رفيق,rafeeq") == "add task"
    assert _extract_wake_command("Rafeeq, start memory test", "يا رفيق,rafeeq") == "start memory test"
    assert _extract_wake_command("Trafikk", "يا رفيق,rafeeq") is None


def test_voice_accepts_one_actionable_followup_after_wake_word() -> None:
    assert _is_followup_candidate("at seven o'clock in the morning")
    assert _is_followup_candidate("رقم تسعة")
    assert _is_actionable_followup("appointment at eight o'clock in the evening")
    assert _is_actionable_followup("add a task at 8 pm")
    assert _is_actionable_followup("start poem test")
    assert _is_actionable_followup("ابدأ اختبار القصيدة")
    assert not _is_actionable_followup("they were alive")


def test_local_app_actions_handle_simple_navigation_commands() -> None:
    assert _local_app_action("open album") == "open_album"
    assert _local_app_action("show routine") == "open_routine"
    assert _local_app_action("rotun") == "open_routine"
    assert _local_app_action("افتح الألبوم") == "open_album"
    assert _local_app_action("افتح الروتين") == "open_routine"
    assert _local_app_action("start memory test") is None
    assert _local_app_action("add appointment at 7") is None


def test_voice_language_switch_commands() -> None:
    assert _language_switch_locale("speak Arabic") == "ar"
    assert _language_switch_locale("تكلم عربي") == "ar"
    assert _language_switch_locale("speak English") == "en"
    assert _language_switch_locale("تكلم انجليزي") == "en"
