import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]

from rafeeq_robot.application.emergency_manager import EmergencyManager
from rafeeq_robot.application.openai_voice_agent import OpenAIRealtimeVoiceAgent
from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.application.reminder_service import ReminderService
from rafeeq_robot.application.sync_service import SyncService
from rafeeq_robot.application.voice_interactor import VoiceIntentRouter
from rafeeq_robot.config import RobotSettings
from rafeeq_robot.hardware.interfaces import SpeakerAdapter, VoiceInputAdapter
from rafeeq_robot.hardware.simulation.adapters import ConsoleSpeaker, format_console_text
from rafeeq_robot.hardware.voice.piper_speaker import PiperSpeaker
from rafeeq_robot.hardware.voice.vosk_adapter import VoskVoiceInput
from rafeeq_robot.hardware.voice.windows_speaker import WindowsSpeechSpeaker
from rafeeq_robot.persistence.database import RobotDatabase
from rafeeq_robot.persistence.models import LocalOccurrence, LocalRoutine
from rafeeq_robot.transport.http_client import create_device_client


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    settings = RobotSettings()
    database = RobotDatabase(settings.local_database_path)
    speaker = _create_speaker(settings)
    client = None
    if settings.rafeeq_device_secret:
        client = create_device_client(
            settings.backend_base_url,
            settings.rafeeq_device_id,
            settings.rafeeq_device_secret,
        )
    outbox = OutboxService(
        database,
        settings.rafeeq_device_id,
        settings.rafeeq_patient_id,
        client,
    )
    reminders = ReminderService(database, outbox, speaker)
    emergencies = EmergencyManager(outbox, speaker)
    local_voice = VoiceIntentRouter(
        reminders,
        outbox,
        speaker,
        emergencies=emergencies,
        snooze_minutes=settings.voice_reminder_snooze_minutes,
    )
    voice = _create_voice_agent(settings, local_voice, reminders, speaker)
    voice_input = _create_voice_input(settings)
    sync = SyncService(database, client) if client else None
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(reminders.run_due, "interval", seconds=5, max_instances=1)
    if client:
        scheduler.add_job(outbox.publish_pending, "interval", seconds=5, max_instances=1)
    scheduler.start()
    speaker.speak("مرحبا انا رفيق")
    print(f"RAFEEQ robot started (hardware_mode={settings.hardware_mode})")
    print(
        "Commands: sync, due, complete <id>, demo-med-taken, listen, voice <text>, "
        "ask-med, sos, fall, safe, help, timeout, publish, quit"
    )
    print(
        "Voice provider="
        f"{settings.voice_interaction_provider}; reasoning={settings.voice_reasoning_provider}; "
        f"model={settings.openai_realtime_model}"
    )
    print(f"Speaker provider={settings.speaker_provider}")
    if not client:
        print("Offline mode: set RAFEEQ_DEVICE_ID and RAFEEQ_DEVICE_SECRET to synchronize.")
    try:
        _command_loop(sync, reminders, voice, voice_input, settings, emergencies, outbox)
    finally:
        scheduler.shutdown(wait=False)
        if client:
            client.close()


def _command_loop(
    sync: SyncService | None,
    reminders: ReminderService,
    voice: VoiceIntentRouter,
    voice_input: VoiceInputAdapter | None,
    settings: RobotSettings,
    emergencies: EmergencyManager,
    outbox: OutboxService,
) -> None:
    while True:
        try:
            command = input("rafeeq> ").strip()
        except EOFError:
            return
        if command in ("quit", "exit"):
            return
        if command == "sync":
            if sync is None:
                print("No device credentials configured; still operating offline.")
            else:
                version = sync.synchronize()
                print(f"Synchronized configuration {version}; routines={sync.routine_count()}")
        elif command == "due":
            print(f"Spoken occurrences: {reminders.run_due()}")
        elif command.startswith("complete "):
            reminders.complete(command.split(maxsplit=1)[1])
            print("Reminder completed locally and queued for synchronization.")
        elif command == "demo-med-taken":
            _seed_demo_completed_medication(reminders, outbox)
            print("Demo medication completion stored as 30 minutes ago.")
        elif command in ("ask-med", "medicine-status", "med-status"):
            result = voice.handle_text("did you take medicine")
            print(f"Voice intent: {result.intent}; handled={result.handled}")
        elif command.startswith("voice "):
            result = voice.handle_text(command.split(maxsplit=1)[1])
            print(f"Voice intent: {result.intent}; handled={result.handled}")
        elif command.startswith("listen"):
            if voice_input is None:
                print("Voice input is not configured. Use: voice yes I took it")
                continue
            seconds = settings.voice_listen_seconds
            parts = command.split(maxsplit=1)
            if len(parts) == 2 and parts[1].isdigit():
                seconds = int(parts[1])
            print(f"Listening for {seconds} seconds...")
            transcript = voice_input.listen_text(seconds)
            if not transcript:
                print("No speech recognized.")
                continue
            print(f"Transcript: {format_console_text(transcript)}")
            result = voice.handle_text(transcript, source=settings.voice_interaction_provider)
            print(f"Voice intent: {result.intent}; handled={result.handled}")
        elif command.startswith("mic-test"):
            if voice_input is None:
                print("Voice input is not configured.")
                continue
            seconds = settings.voice_listen_seconds
            parts = command.split(maxsplit=1)
            if len(parts) == 2 and parts[1].isdigit():
                seconds = int(parts[1])
            description = getattr(voice_input, "description", "configured microphone")
            print(description)
            print(f"Listening for {seconds} seconds without action...")
            transcript = voice_input.listen_text(seconds)
            print(f"Transcript: {format_console_text(transcript or '<none>')}")
        elif command == "sos":
            event_id = emergencies.trigger_sos()
            print(f"SOS stored locally: {event_id}")
            outbox.publish_pending()
        elif command == "fall":
            event_id = emergencies.trigger_possible_fall(0.82, ["mock_trigger"])
            print(f"Possible fall stored; verification active: {event_id}")
            outbox.publish_pending()
        elif command in ("safe", "help", "timeout"):
            try:
                emergencies.finish_fall_verification(command)
                outbox.publish_pending()
            except RuntimeError as error:
                print(error)
        elif command == "publish":
            print(f"Published events: {outbox.publish_pending()}")
        elif command == "help":
            print(
                "Commands: sync, due, complete <id>, demo-med-taken, listen, "
                "voice <text>, ask-med, sos, fall, safe, help, timeout, mic-test, "
                "publish, quit"
            )
        elif command:
            print("Unknown command. Type help.")


def _seed_demo_completed_medication(
    reminders: ReminderService,
    outbox: OutboxService,
) -> None:
    completed_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    routine_id = str(uuid4())
    occurrence_id = str(uuid4())
    with reminders.database.session() as session, session.begin():
        session.add(
            LocalRoutine(
                id=routine_id,
                patient_id=outbox.patient_id,
                type="medication",
                title="دواء تجريبي",
                payload_json={"medication": {"dosage_text": "جرعة تجريبية"}},
                configuration_version="demo",
            )
        )
        session.add(
            LocalOccurrence(
                id=occurrence_id,
                routine_id=routine_id,
                scheduled_at_utc=completed_at,
                status="completed",
                prompted_at=completed_at,
            )
        )
        outbox.record_in_session(
            session,
            "reminder_completed",
            {"occurrence_id": occurrence_id, "confirmation_source": "demo"},
            completed_at,
        )


def _create_voice_input(settings: RobotSettings) -> VoiceInputAdapter | None:
    if settings.voice_interaction_provider != "vosk":
        return None
    return VoskVoiceInput(
        settings.vosk_model_path,
        settings.vosk_sample_rate,
        settings.vosk_input_device,
    )


def _create_voice_agent(
    settings: RobotSettings,
    local_voice: VoiceIntentRouter,
    reminders: ReminderService,
    speaker: SpeakerAdapter,
) -> VoiceIntentRouter | OpenAIRealtimeVoiceAgent:
    if settings.voice_reasoning_provider == "openai":
        return OpenAIRealtimeVoiceAgent(
            local_voice,
            reminders,
            speaker,
            settings.openai_api_key,
            settings.openai_realtime_model,
            settings.voice_max_session_seconds,
        )
    return local_voice


def _create_speaker(settings: RobotSettings) -> SpeakerAdapter:
    if settings.speaker_provider == "piper":
        return PiperSpeaker(
            settings.piper_voice_model,
            settings.piper_voice_config,
            settings.speaker_volume,
        )
    if settings.speaker_provider == "windows":
        return WindowsSpeechSpeaker(settings.speaker_rate, settings.speaker_volume)
    return ConsoleSpeaker()


if __name__ == "__main__":
    main()
