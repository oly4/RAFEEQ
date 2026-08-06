import json
import re
import shlex
import subprocess
import sys
import time
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]

from rafeeq_robot.application.emergency_manager import EmergencyManager
from rafeeq_robot.application.language import choose_locale_text, detect_spoken_locale
from rafeeq_robot.application.memory_practice import MemoryPracticeService
from rafeeq_robot.application.openai_voice_agent import OpenAIRealtimeVoiceAgent
from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.application.poem_practice import PoemPracticeService
from rafeeq_robot.application.reminder_service import ReminderService, RoutineTaskStatus
from rafeeq_robot.application.sync_service import SyncService
from rafeeq_robot.application.voice_interactor import VoiceIntentRouter
from rafeeq_robot.config import RobotSettings
from rafeeq_robot.hardware.interfaces import SpeakerAdapter, VoiceInputAdapter
from rafeeq_robot.hardware.simulation.adapters import (
    ConsoleSpeaker,
    clean_speech_text,
    format_console_text,
)
from rafeeq_robot.hardware.voice.piper_speaker import PiperSpeaker
from rafeeq_robot.hardware.voice.openai_transcription_adapter import OpenAITranscriptionVoiceInput
from rafeeq_robot.hardware.voice.vosk_adapter import VoskVoiceInput
from rafeeq_robot.hardware.voice.windows_speaker import WindowsSpeechSpeaker
from rafeeq_robot.persistence.database import RobotDatabase
from rafeeq_robot.persistence.models import LocalOccurrence, LocalRoutine
from rafeeq_robot.transport.http_client import create_device_client


VOICE_PAUSE_FILE = Path("/tmp/rafeeq_voice_paused")
VOICE_MIC_RESERVED_FILE = Path("/tmp/rafeeq-runtime/voice_mic_reserved")
VOICE_COMMAND_DIR = Path("/tmp/rafeeq-runtime/voice-commands")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    daemon = "--daemon" in sys.argv[1:]
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
    reminders = ReminderService(
        database,
        outbox,
        speaker,
        spoken_reminders_enabled=settings.spoken_reminders_enabled,
    )
    emergencies = EmergencyManager(outbox, speaker)
    local_voice = VoiceIntentRouter(
        reminders,
        outbox,
        speaker,
        emergencies=emergencies,
        snooze_minutes=settings.voice_reminder_snooze_minutes,
    )
    sos_button = _start_sos_button_listener(settings, emergencies, outbox, speaker)
    voice = _create_voice_agent(settings, local_voice, reminders, speaker)
    voice_input = _create_voice_input(settings)
    poems = PoemPracticeService(settings, outbox, speaker)
    memories = MemoryPracticeService(settings, outbox, speaker)
    sync = SyncService(database, client) if client else None
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(reminders.run_due, "interval", seconds=5, max_instances=1)
    if client:
        scheduler.add_job(outbox.publish_pending, "interval", seconds=5, max_instances=1)
        if sync:
            scheduler.add_job(_synchronize_quietly, "interval", seconds=120, args=[sync], max_instances=1)
    scheduler.start()
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
    if daemon:
        if sync:
            try:
                version = sync.synchronize()
                print(f"Initial synchronization complete: {version}")
            except Exception as exc:
                print(f"Initial synchronization failed; local behavior remains active: {exc}")
        if voice_input is not None:
            _start_daemon_voice_loop(voice, voice_input, settings, speaker, outbox, poems, memories)
        _start_robot_speech_command_watcher(speaker)
        print("Daemon mode active.")
        _speak_startup_greeting(settings, speaker, voice_input is not None)
        try:
            while True:
                time.sleep(3600)
        finally:
            _close_sos_button(sos_button)
            scheduler.shutdown(wait=False)
            if client:
                client.close()
        return
    _speak_startup_greeting(settings, speaker, voice_input is not None)
    try:
        _command_loop(
            sync,
            reminders,
            voice,
            voice_input,
            settings,
            emergencies,
            outbox,
            poems,
            memories,
        )
    finally:
        _close_sos_button(sos_button)
        scheduler.shutdown(wait=False)
        if client:
            client.close()


def _start_sos_button_listener(
    settings: RobotSettings,
    emergencies: EmergencyManager,
    outbox: OutboxService,
    speaker: SpeakerAdapter,
) -> object | None:
    if not settings.sos_button_enabled or settings.hardware_mode != "raspberry_pi":
        return None
    try:
        from gpiozero import Button  # type: ignore[import-not-found]
        from gpiozero.pins.lgpio import LGPIOFactory  # type: ignore[import-not-found]
    except Exception as exc:
        print(f"SOS button disabled: GPIO library unavailable: {exc}")
        return None

    last_pressed_at = 0.0
    shutdown_requested = False
    lock = threading.Lock()

    def on_released() -> None:
        nonlocal last_pressed_at, shutdown_requested
        now = time.monotonic()
        with lock:
            if shutdown_requested:
                shutdown_requested = False
                print("SOS button release ignored after shutdown hold.")
                return
            if now - last_pressed_at < settings.sos_button_cooldown_seconds:
                print("SOS button press ignored during cooldown.")
                return
            last_pressed_at = now
        try:
            event_id = emergencies.trigger_sos()
            print(f"SOS button pressed; event queued: {event_id}")
            outbox.publish_pending()
        except Exception as exc:
            print(f"SOS button handling failed: {exc}")

    def on_held() -> None:
        nonlocal shutdown_requested
        if not settings.sos_button_shutdown_enabled:
            return
        with lock:
            if shutdown_requested:
                return
            shutdown_requested = True
        print("SOS button held; shutdown requested.")
        threading.Thread(
            target=_speak_goodbye_and_shutdown,
            args=(settings, speaker),
            daemon=True,
        ).start()

    try:
        factory = LGPIOFactory()
        button = Button(
            settings.sos_button_gpio,
            pull_up=settings.sos_button_pull_up,
            bounce_time=settings.sos_button_bounce_seconds,
            hold_time=settings.sos_button_shutdown_hold_seconds,
            hold_repeat=False,
            pin_factory=factory,
        )
        button.when_released = on_released
        button.when_held = on_held
        wiring = "GPIO to GND" if settings.sos_button_pull_up else "GPIO to 3.3V"
        print(
            f"SOS button active on BCM GPIO {settings.sos_button_gpio} ({wiring}); "
            f"hold {settings.sos_button_shutdown_hold_seconds:g}s to shutdown."
        )
        return button
    except Exception as exc:
        print(f"SOS button disabled: could not open GPIO {settings.sos_button_gpio}: {exc}")
    return None


def _speak_goodbye_and_shutdown(settings: RobotSettings, speaker: SpeakerAdapter) -> None:
    locale = (
        settings.voice_default_locale
        if settings.voice_default_locale in {"ar", "en"}
        else "en"
    )
    message = _sos_shutdown_goodbye_message(locale)
    try:
        speaker.speak(message, locale)
        _wait_until_speaker_idle(speaker, timeout_seconds=12)
    except Exception as exc:
        print(f"SOS shutdown goodbye failed: {exc}")
    command = shlex.split(settings.sos_button_shutdown_command)
    if not command:
        print("SOS shutdown skipped: shutdown command is empty.")
        return
    try:
        print(f"SOS shutdown command: {command[0]} ...")
        subprocess.run(command, check=False, timeout=15)
    except Exception as exc:
        print(f"SOS shutdown command failed: {exc}")


def _sos_shutdown_goodbye_message(locale: str) -> str:
    return choose_locale_text(
        locale,
        "مع السلامة. سأغلق الجهاز الآن.",
        "Goodbye. I will shut down now.",
    )


def _wait_until_speaker_idle(speaker: SpeakerAdapter, timeout_seconds: float) -> None:
    is_speaking = getattr(speaker, "is_speaking", None)
    deadline = time.monotonic() + timeout_seconds
    while callable(is_speaking) and is_speaking() and time.monotonic() < deadline:
        time.sleep(0.1)


def _synchronize_quietly(sync: SyncService) -> None:
    try:
        version = sync.synchronize()
        print(f"Configuration sync complete: {version}")
    except Exception as exc:
        print(f"Configuration sync skipped; local voice remains active: {exc}")


def _speak_startup_greeting(
    settings: RobotSettings,
    speaker: SpeakerAdapter,
    voice_ready: bool,
) -> None:
    if not settings.startup_greeting_enabled:
        return
    locale = (
        settings.voice_default_locale
        if settings.voice_default_locale in {"ar", "en"}
        else "en"
    )
    message = choose_locale_text(
        locale,
        "مرحبا، أنا رفيق. أنا جاهز أساعدك.",
        "Hello, I'm RAFEEQ. I'm ready to help.",
    )
    if not voice_ready:
        message = choose_locale_text(
            locale,
            "مرحبا، أنا رفيق. النظام جاهز، لكن الميكروفون غير مفعل الآن.",
            "Hello, I'm RAFEEQ. The system is ready, but the microphone is not "
            "active right now.",
        )
    try:
        speaker.speak(message, locale)
        print("Startup greeting spoken.")
    except Exception as exc:
        print(f"Startup greeting skipped: {exc}")


def _close_sos_button(button: object | None) -> None:
    close = getattr(button, "close", None)
    if callable(close):
        close()


def _start_daemon_voice_loop(
    voice: VoiceIntentRouter | OpenAIRealtimeVoiceAgent,
    voice_input: VoiceInputAdapter,
    settings: RobotSettings,
    speaker: SpeakerAdapter,
    outbox: OutboxService,
    poems: PoemPracticeService,
    memories: MemoryPracticeService,
) -> None:
    def worker() -> None:
        description = getattr(voice_input, "description", "configured microphone")
        print(f"Daemon voice loop active: {description}")
        voice_paused = False
        external_pause_logged = False
        mic_reserved_logged = False
        pending_transcript: str | None = None
        awaiting_wake_followup = False
        current_locale = settings.voice_default_locale if settings.voice_default_locale in {"ar", "en"} else "en"
        _set_voice_response_locale(voice, current_locale)
        while True:
            if _is_voice_mic_reserved():
                if not mic_reserved_logged:
                    print("Voice microphone paused: fall verification is using the mic.")
                    mic_reserved_logged = True
                time.sleep(0.5)
                continue
            mic_reserved_logged = False
            is_speaking = getattr(speaker, "is_speaking", None)
            while callable(is_speaking) and is_speaking():
                time.sleep(0.25)
            started_at = time.monotonic()
            try:
                transcript = voice_input.listen_text(settings.voice_listen_seconds)
            except Exception as exc:
                print(f"Voice listening failed: {exc}")
                time.sleep(5)
                continue
            spoke_since = getattr(speaker, "spoke_since", None)
            if callable(spoke_since) and spoke_since(started_at):
                print("Voice transcript skipped because RAFEEQ spoke during recording.")
                time.sleep(0.5)
                continue
            if not transcript:
                time.sleep(0.5)
                continue
            print(f"Voice transcript: {format_console_text(transcript)}")
            external_paused = _is_terminal_voice_paused()
            if external_paused and not external_pause_logged:
                print("Voice paused by terminal command.")
                external_pause_logged = True
            if not external_paused:
                external_pause_logged = False
            if voice_paused or external_paused:
                wake_command = _extract_wake_command(transcript, settings.voice_wake_words)
                if wake_command is not None:
                    if wake_command and _is_quiet_command(wake_command):
                        voice_paused = True
                        _set_terminal_voice_paused(True)
                        external_pause_logged = True
                        pending_transcript = None
                        awaiting_wake_followup = False
                        print("Voice remains in quiet mode after repeated quiet command.")
                        time.sleep(0.5)
                        continue
                    requested_locale = _language_switch_locale(wake_command or transcript)
                    voice_paused = False
                    _set_terminal_voice_paused(False)
                    external_pause_logged = False
                    pending_transcript = None
                    awaiting_wake_followup = False
                    if requested_locale is not None:
                        current_locale = requested_locale
                        _set_voice_response_locale(voice, current_locale)
                        speaker.speak(
                            choose_locale_text(
                                current_locale,
                                "تمام، بتكلم عربي.",
                                "Okay. I will speak English.",
                            ),
                            current_locale,
                        )
                        print(f"Voice response language changed to {current_locale}.")
                        time.sleep(0.5)
                        continue
                    if wake_command and not _is_start_hearing_command(wake_command):
                        transcript = wake_command
                        print(f"Wake command after quiet mode: {format_console_text(transcript)}")
                    else:
                        speaker.speak(
                            choose_locale_text(current_locale, "سمعتك.", "I heard you."),
                            current_locale,
                        )
                        awaiting_wake_followup = True
                        print("Voice listening resumed by wake command.")
                        time.sleep(0.5)
                        continue
                else:
                    print("Voice paused: waiting for wake word.")
                    time.sleep(0.5)
                    continue
            if settings.voice_wake_word_required:
                wake_command = _extract_wake_command(transcript, settings.voice_wake_words)
                if wake_command is None:
                    if _is_explicit_activity_test_request(transcript):
                        awaiting_wake_followup = False
                        print(
                            "Voice activity request accepted without wake word: "
                            f"{format_console_text(transcript)}"
                        )
                    elif awaiting_wake_followup and _is_followup_candidate(transcript):
                        awaiting_wake_followup = False
                        print(
                            "Voice follow-up accepted after wake word: "
                            f"{format_console_text(transcript)}"
                        )
                    else:
                        awaiting_wake_followup = False
                        print("Voice transcript ignored: wake word was not heard.")
                        time.sleep(0.5)
                        continue
                if wake_command is not None:
                    requested_locale = _language_switch_locale(wake_command or transcript)
                    if not wake_command:
                        speaker.speak(
                            choose_locale_text(current_locale, "سمعتك.", "I heard you."),
                            current_locale,
                        )
                        awaiting_wake_followup = True
                        time.sleep(0.5)
                        continue
                    awaiting_wake_followup = False
                    transcript = wake_command
                    print(f"Wake command: {format_console_text(transcript)}")
            requested_locale = _language_switch_locale(transcript)
            if requested_locale is not None:
                current_locale = requested_locale
                _set_voice_response_locale(voice, current_locale)
                speaker.speak(
                    choose_locale_text(
                        current_locale,
                        "تمام، بتكلم عربي.",
                        "Okay. I will speak English.",
                    ),
                    current_locale,
                )
                print(f"Voice response language changed to {current_locale}.")
                time.sleep(0.5)
                continue
            if _is_quiet_command(transcript):
                speaker.speak(choose_locale_text(current_locale, "تمام.", "Okay."), current_locale)
                voice_paused = True
                _set_terminal_voice_paused(True)
                external_pause_logged = True
                pending_transcript = None
                awaiting_wake_followup = False
                print("Voice quiet mode enabled by command; waiting for wake word.")
                time.sleep(0.5)
                continue
            if _is_stop_hearing_command(transcript):
                voice_paused = True
                _set_terminal_voice_paused(True)
                external_pause_logged = True
                pending_transcript = None
                awaiting_wake_followup = False
                speaker.speak(
                    choose_locale_text(
                        current_locale,
                        "تم، وقفت سماع الأوامر. قل يا رفيق اسمعني عشان أرجع.",
                        "Done. I stopped listening for commands. Say Rafeeq start hearing to bring me back.",
                    ),
                    current_locale,
                )
                print("Voice listening paused by command.")
                time.sleep(0.5)
                continue
            if _is_start_hearing_command(transcript):
                speaker.speak(
                    choose_locale_text(current_locale, "أنا أسمعك.", "I am listening."),
                    current_locale,
                )
                print("Voice start-hearing command received while already active.")
                time.sleep(0.5)
                continue
            if settings.voice_confirm_before_response:
                if pending_transcript is not None:
                    if _is_voice_confirmation(transcript):
                        transcript = pending_transcript
                        pending_transcript = None
                        print(f"Voice confirmed transcript: {format_console_text(transcript)}")
                    elif _is_voice_cancel(transcript):
                        print(f"Voice cancelled transcript: {format_console_text(pending_transcript)}")
                        pending_transcript = None
                        speaker.speak(
                            choose_locale_text(
                                current_locale,
                                "تم، ألغيت الأمر.",
                                "Done. I cancelled it.",
                            ),
                            current_locale,
                        )
                        time.sleep(0.5)
                        continue
                    else:
                        pending_transcript = transcript
                        print(f"Voice pending transcript updated: {format_console_text(transcript)}")
                        speaker.speak(
                            choose_locale_text(
                                current_locale,
                                f"سمعت: {transcript}. قل تأكيد عشان أنفذ.",
                                f"I heard: {transcript}. Say confirm so I can do it.",
                            ),
                            current_locale,
                        )
                        time.sleep(0.5)
                        continue
                elif not _is_voice_confirmation(transcript):
                    pending_transcript = transcript
                    print(f"Voice pending transcript: {format_console_text(transcript)}")
                    speaker.speak(
                        choose_locale_text(
                            current_locale,
                            f"سمعت: {transcript}. قل تأكيد عشان أنفذ.",
                            f"I heard: {transcript}. Say confirm so I can do it.",
                        ),
                        current_locale,
                    )
                    time.sleep(0.5)
                    continue
            try:
                if _is_vague_test_request(transcript):
                    speaker.speak(
                        choose_locale_text(
                            current_locale,
                            "أي نشاط تريد؟ قل جولة الذكريات أو تمرين القصيدة.",
                            "Which activity do you want? Say memory tour or poem exercise.",
                        ),
                        current_locale,
                    )
                    awaiting_wake_followup = True
                    print("Voice intent: clarify_activity_test; handled=True")
                    time.sleep(0.5)
                    continue
                activity_request = _looks_like_activity_test(transcript)
                if activity_request:
                    if poems.can_handle(transcript) and poems.handle_text(transcript, voice_input):
                        print("Voice intent: start_poem_test; handled=True")
                        time.sleep(0.5)
                        continue
                    if memories.can_handle(transcript) and memories.handle_text(transcript, voice_input):
                        print("Voice intent: start_photo_test; handled=True")
                        time.sleep(0.5)
                        continue
                if _handle_read_routine_request(transcript, reminders, speaker, current_locale):
                    time.sleep(0.5)
                    continue
                if _handle_local_app_command(transcript, outbox, speaker, current_locale):
                    time.sleep(0.5)
                    continue
                result = voice.handle_text(
                    transcript,
                    source=settings.voice_interaction_provider,
                )
                print(f"Voice intent: {result.intent}; handled={result.handled}")
            except Exception as exc:
                print(f"Voice handling failed: {exc}")
            time.sleep(0.5)

    threading.Thread(target=worker, daemon=True).start()


def _start_robot_speech_command_watcher(speaker: SpeakerAdapter) -> None:
    def worker() -> None:
        VOICE_COMMAND_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Robot speech command watcher active: {VOICE_COMMAND_DIR}")
        while True:
            try:
                commands = sorted(VOICE_COMMAND_DIR.glob("*.json"))
            except Exception as exc:
                print(f"Robot speech command scan failed: {exc}")
                time.sleep(2)
                continue
            if not commands:
                time.sleep(0.5)
                continue
            for command_path in commands[:5]:
                try:
                    payload = json.loads(command_path.read_text(encoding="utf-8"))
                    text = str(payload.get("text") or "").strip()
                    locale = str(payload.get("locale") or "en").strip().lower()
                    locale = "ar" if locale.startswith("ar") else "en"
                    command_path.unlink(missing_ok=True)
                    if not text:
                        continue
                    print(f"Robot speech command: {format_console_text(text)}")
                    speaker.speak(text, locale)
                except Exception as exc:
                    print(f"Robot speech command failed: {exc}")
                    command_path.unlink(missing_ok=True)
            time.sleep(0.2)

    threading.Thread(target=worker, daemon=True).start()


def _is_voice_confirmation(transcript: str) -> bool:
    normalized = _normalize_wake_text(transcript)
    compact = normalized.replace(" ", "")
    phrases = (
        "confirm",
        "confirmed",
        "confirmation",
        "confirme",
        "تأكيد",
        "تاكيد",
        "اكد",
        "أكد",
        "نعم اكد",
        "اي اكد",
        "نفذ",
        "تمام نفذ",
    )
    return any(_normalize_wake_text(phrase).replace(" ", "") in compact for phrase in phrases)


def _is_voice_cancel(transcript: str) -> bool:
    normalized = _normalize_wake_text(transcript)
    compact = normalized.replace(" ", "")
    phrases = (
        "cancel",
        "stop",
        "الغاء",
        "الغي",
        "لا تنفذ",
        "خلاص",
    )
    return any(_normalize_wake_text(phrase).replace(" ", "") in compact for phrase in phrases)


def _is_followup_candidate(transcript: str) -> bool:
    normalized = _normalize_wake_text(transcript)
    return bool(re.search(r"[0-9a-z\u0600-\u06ff]", normalized))


def _is_actionable_followup(transcript: str) -> bool:
    if _language_switch_locale(transcript) is not None:
        return True
    if (
        _is_quiet_command(transcript)
        or _is_stop_hearing_command(transcript)
        or _is_start_hearing_command(transcript)
    ):
        return True
    return _contains_control_phrase(
        transcript,
        (
            "add task",
            "add a task",
            "create task",
            "new task",
            "task at",
            "add appointment",
            "create appointment",
            "new appointment",
            "appointment at",
            "meeting at",
            "add reminder",
            "create reminder",
            "new reminder",
            "remind me",
            "medicine",
            "medication",
            "water",
            "meal",
            "complete task",
            "mark done",
            "done task",
            "start poem",
            "poem test",
            "poetry test",
            "start album",
            "memory tour",
            "album tour",
            "album test",
            "photo test",
            "memory test",
            "start activity",
            "help",
            "emergency",
            "موعد",
            "اجتماع",
            "مهمه",
            "مهمة",
            "تذكير",
            "ذكرني",
            "دواء",
            "علاج",
            "مويه",
            "ماء",
            "وجبه",
            "وجبة",
            "غداء",
            "عشاء",
            "فطور",
            "خلصت",
            "سويت",
            "ابدأ",
            "ابدا",
            "شغل",
            "قصيده",
            "قصيدة",
            "البوم",
            "ألبوم",
            "صور",
            "ذاكره",
            "ذاكرة",
            "مساعده",
            "مساعدة",
            "طوارئ",
        ),
    )


def _handle_local_app_command(
    transcript: str,
    outbox: OutboxService,
    speaker: SpeakerAdapter,
    locale: str,
) -> bool:
    action = _local_app_action(transcript)
    if action is None:
        return False
    message = _local_app_action_message(action, locale)
    outbox.record(
        "voice_app_action",
        {
            "action": action,
            "transcript": transcript,
            "assistant_text": message,
            "used_openai": False,
        },
    )
    speaker.speak(message, locale)
    print(f"Voice intent: {action}; handled=True")
    return True


def _handle_read_routine_request(
    transcript: str,
    reminders: ReminderService,
    speaker: SpeakerAdapter,
    locale: str,
) -> bool:
    if not _looks_like_read_routine_request(transcript):
        return False
    statuses = reminders.list_today_task_statuses()
    message = _routine_summary_message(statuses, locale)
    speaker.speak(message, locale)
    print("Voice intent: read_routine; handled=True")
    return True


def _looks_like_read_routine_request(transcript: str) -> bool:
    return _contains_control_phrase(
        transcript,
        (
            "what in my routine",
            "what in my routen",
            "what in my routin",
            "what in my routun",
            "what in my rotun",
            "what's in my routine",
            "what's in my routen",
            "what is in my routine",
            "what is in my routen",
            "what is in my routin",
            "what is in my routun",
            "what is in my rotun",
            "what is my routine",
            "what is my routen",
            "what is my routin",
            "what is my routun",
            "what is my rotun",
            "what do i have in my routine",
            "what do i have in my routen",
            "tell me my routine",
            "tell me my routen",
            "read my routine",
            "read my routen",
            "say my routine",
            "say my routen",
            "list my routine",
            "list my routen",
            "what is my schedule",
            "what's my schedule",
            "what do i have today",
            "today routine",
            "today's routine",
            "routin today",
            "rotun today",
            "وش روتيني",
            "وش في روتيني",
            "ايش روتيني",
            "ايش في روتيني",
            "ما هو روتيني",
            "ماذا في روتيني",
            "اقرا الروتين",
            "اقرأ الروتين",
            "قل الروتين",
            "وش جدولي",
            "ايش جدولي",
            "اقرا الجدول",
            "اقرأ الجدول",
            "مهامي اليوم",
            "روتيني اليوم",
            "جدولي اليوم",
        ),
    )


def _routine_summary_message(statuses: list[RoutineTaskStatus], locale: str) -> str:
    if not statuses:
        return choose_locale_text(
            locale,
            "ما عندك مهام في روتين اليوم.",
            "You do not have any tasks in today's routine.",
        )
    intro = choose_locale_text(locale, "روتين اليوم:", "Today's routine:")
    parts = [intro]
    for index, status in enumerate(statuses, start=1):
        local_time = status.scheduled_at_utc.astimezone().strftime("%H:%M")
        state = _spoken_status(status.status, locale)
        parts.append(
            choose_locale_text(
                locale,
                f"{index}. الساعة {local_time}: {status.title}. الحالة: {state}.",
                f"{index}. At {local_time}: {status.title}. Status: {state}.",
            )
        )
    return " ".join(parts)


def _spoken_status(status: str, locale: str) -> str:
    normalized = status.strip().casefold()
    arabic = {
        "pending": "لم تنجز بعد",
        "reminded": "تم التذكير",
        "snoozed": "مؤجلة",
        "completed": "منجزة",
        "missed": "فائتة",
    }
    english = {
        "pending": "not done yet",
        "reminded": "reminded",
        "snoozed": "snoozed",
        "completed": "done",
        "missed": "missed",
    }
    table = english if locale == "en" else arabic
    return table.get(normalized, normalized or ("unknown" if locale == "en" else "غير معروفة"))


def _local_app_action(transcript: str) -> str | None:
    if _looks_like_activity_test(transcript) or _looks_like_create_or_edit(transcript):
        return None
    if _contains_control_phrase(
        transcript,
        (
            "open album",
            "show album",
            "open photo",
            "open photos",
            "show photos",
            "open pictures",
            "show pictures",
            "open memories",
            "show memories",
            "album",
            "photo album",
            "افتح الالبوم",
            "افتح الألبوم",
            "افتح الصور",
            "وريني الصور",
            "اعرض الصور",
            "افتح الذكريات",
            "الالبوم",
            "الألبوم",
        ),
    ):
        return "open_album"
    if _contains_control_phrase(
        transcript,
        (
            "open routine",
            "show routine",
            "open schedule",
            "show schedule",
            "open tasks",
            "show tasks",
            "routine",
            "routin",
            "routun",
            "rotun",
            "routune",
            "schedule",
            "افتح الروتين",
            "افتح الجدول",
            "افتح المهام",
            "اعرض الروتين",
            "اعرض الجدول",
            "الروتين",
            "الجدول",
            "المهام",
        ),
    ):
        return "open_routine"
    if _contains_control_phrase(
        transcript,
        (
            "open activities",
            "show activities",
            "activities",
            "activity",
            "افتح الانشطه",
            "افتح الأنشطة",
            "اعرض الانشطه",
            "اعرض الأنشطة",
            "الانشطه",
            "الأنشطة",
        ),
    ):
        return "open_activities"
    if _contains_control_phrase(
        transcript,
        (
            "open dashboard",
            "show dashboard",
            "dashboard",
            "home page",
            "افتح الرئيسيه",
            "افتح الرئيسية",
            "افتح لوحه التحكم",
            "افتح لوحة التحكم",
        ),
    ):
        return "open_dashboard"
    if _contains_control_phrase(
        transcript,
        (
            "open settings",
            "settings",
            "افتح الاعدادات",
            "افتح الإعدادات",
            "الاعدادات",
            "الإعدادات",
        ),
    ):
        return "open_settings"
    return None


def _looks_like_activity_test(transcript: str) -> bool:
    return _contains_control_phrase(
        transcript,
        (
            "test",
            "practice",
            "quiz",
            "start memory",
            "start album",
            "start photo",
            "start picture",
            "start poem",
            "begin memory",
            "begin album",
            "begin photo",
            "اختبار",
            "تمرين",
            "اختبرني",
            "دربني",
            "ابدأ الالبوم",
            "ابدا الالبوم",
            "ابدأ الألبوم",
            "ابدا الألبوم",
            "ابدأ الصور",
            "ابدا الصور",
            "ابدأ الذاكره",
            "ابدا الذاكره",
            "ابدأ الذاكرة",
            "ابدا الذاكرة",
        ),
    )


def _is_explicit_activity_test_request(transcript: str) -> bool:
    if _is_vague_test_request(transcript):
        return False
    normalized = _normalize_wake_text(transcript)
    has_test_word = _contains_control_phrase(
        normalized,
        (
            "test",
            "practice",
            "quiz",
            "اختبار",
            "تمرين",
            "اختبرني",
            "دربني",
        ),
    )
    has_memory_word = _contains_control_phrase(
        normalized,
        (
            "memory",
            "album",
            "photo",
            "picture",
            "memories",
            "الذاكره",
            "الذاكرة",
            "الالبوم",
            "الألبوم",
            "البوم",
            "ألبوم",
            "الصور",
            "صوره",
            "صورة",
        ),
    )
    has_poem_word = _contains_control_phrase(
        normalized,
        (
            "poem",
            "poetry",
            "قصيده",
            "قصيدة",
        ),
    )
    has_start_word = _contains_control_phrase(
        normalized,
        (
            "start",
            "begin",
            "run",
            "open",
            "ابدأ",
            "ابدا",
            "افتح",
            "شغل",
        ),
    )
    return has_test_word and (has_memory_word or has_poem_word or has_start_word)


def _is_vague_test_request(transcript: str) -> bool:
    normalized = _normalize_wake_text(transcript)
    compact = normalized.replace(" ", "")
    vague = {
        "test",
        "tests",
        "testing",
        "تست",
        "اختبار",
        "الاختبار",
        "تمرين",
    }
    return compact in vague


def _looks_like_create_or_edit(transcript: str) -> bool:
    return _contains_control_phrase(
        transcript,
        (
            "add",
            "create",
            "new",
            "delete",
            "edit",
            "change",
            "remind me",
            "complete",
            "done",
            "اضف",
            "أضف",
            "ضيف",
            "سوي",
            "احذف",
            "عدل",
            "غير",
            "ذكرني",
            "خلصت",
        ),
    )


def _local_app_action_message(action: str, locale: str) -> str:
    messages = {
        "open_album": (
            "تمام، فتحت الألبوم.",
            "Okay. I opened the album.",
        ),
        "open_routine": (
            "تمام، فتحت الروتين.",
            "Okay. I opened the routine.",
        ),
        "open_activities": (
            "تمام، فتحت الأنشطة.",
            "Okay. I opened activities.",
        ),
        "open_dashboard": (
            "تمام، فتحت الصفحة الرئيسية.",
            "Okay. I opened the dashboard.",
        ),
        "open_settings": (
            "تمام، فتحت الإعدادات.",
            "Okay. I opened settings.",
        ),
    }
    arabic, english = messages[action]
    return choose_locale_text(locale, arabic, english)


def _set_voice_response_locale(
    voice: VoiceIntentRouter | OpenAIRealtimeVoiceAgent,
    locale: str,
) -> None:
    set_locale = getattr(voice, "set_preferred_locale", None)
    if callable(set_locale):
        set_locale(locale)


def _language_switch_locale(transcript: str) -> str | None:
    if _contains_control_phrase(
        transcript,
        (
            "speak arabic",
            "talk arabic",
            "talk in arabic",
            "speak in arabic",
            "answer arabic",
            "answer in arabic",
            "arabic language",
            "change to arabic",
            "switch to arabic",
            "تكلم عربي",
            "تكلم بالعربي",
            "تحدث عربي",
            "تحدث بالعربي",
            "جاوب عربي",
            "جاوب بالعربي",
            "حول عربي",
            "حول للعربي",
            "اللغة العربية",
            "اللغه العربيه",
        ),
    ):
        return "ar"
    if _contains_control_phrase(
        transcript,
        (
            "speak english",
            "talk english",
            "talk in english",
            "speak in english",
            "answer english",
            "answer in english",
            "english language",
            "change to english",
            "switch to english",
            "تكلم انجليزي",
            "تكلم بالانجليزي",
            "تكلم انقليزي",
            "تكلم بالانقليزي",
            "تحدث انجليزي",
            "تحدث بالانجليزي",
            "جاوب انجليزي",
            "جاوب بالانجليزي",
            "حول انجليزي",
            "حول للانجليزي",
            "اللغة الانجليزية",
            "اللغه الانجليزيه",
        ),
    ):
        return "en"
    return None


def _is_terminal_voice_paused() -> bool:
    return VOICE_PAUSE_FILE.exists()


def _set_terminal_voice_paused(paused: bool) -> None:
    try:
        if paused:
            VOICE_PAUSE_FILE.write_text("paused\n", encoding="utf-8")
        else:
            VOICE_PAUSE_FILE.unlink(missing_ok=True)
    except OSError as exc:
        print(f"Voice pause state update failed: {exc}")


def _is_voice_mic_reserved() -> bool:
    return VOICE_MIC_RESERVED_FILE.exists()


def _is_stop_hearing_command(transcript: str) -> bool:
    return _contains_control_phrase(
        transcript,
        (
            "stop hearing",
            "stop listening",
            "dont hear",
            "don't hear",
            "do not hear",
            "mute yourself",
            "وقف السماع",
            "وقف الاستماع",
            "توقف عن السماع",
            "توقف عن الاستماع",
            "لا تسمع",
            "لا تسمعني",
            "اسكت عن السماع",
            "وقف سماع الاوامر",
            "وقف سماع الأوامر",
        ),
    )


def _is_quiet_command(transcript: str) -> bool:
    return _contains_control_phrase(
        transcript,
        (
            "be quiet",
            "be quite",
            "quiet",
            "silent",
            "silence",
            "silnte",
            "dont talk",
            "don't talk",
            "do not talk",
            "stop talking",
            "stop speaking",
            "mute",
            "shut up",
            "اسكت",
            "اسكت يا رفيق",
            "اصمت",
            "صامت",
            "هدوء",
            "لا تتكلم",
            "لا تحكي",
            "لا تتحدث",
            "وقف الكلام",
            "وقف التحدث",
        ),
    )


def _is_start_hearing_command(transcript: str) -> bool:
    return _contains_control_phrase(
        transcript,
        (
            "start hearing",
            "start listening",
            "hear me",
            "listen to me",
            "اسمع",
            "اسمعني",
            "ابدأ السماع",
            "ابدا السماع",
            "ابدأ الاستماع",
            "ابدا الاستماع",
            "ارجع اسمع",
            "ارجع اسمعني",
            "اسمع الاوامر",
            "اسمع الأوامر",
        ),
    )


def _contains_control_phrase(transcript: str, phrases: tuple[str, ...]) -> bool:
    normalized = _normalize_wake_text(transcript)
    compact = normalized.replace(" ", "")
    return any(_normalize_wake_text(phrase).replace(" ", "") in compact for phrase in phrases)


def _extract_wake_command(transcript: str, wake_words: str) -> str | None:
    normalized = _normalize_wake_text(transcript)
    compact = normalized.replace(" ", "")
    patterns = [
        _normalize_wake_text(pattern)
        for pattern in wake_words.split(",")
        if pattern.strip()
    ]
    patterns.extend(
        [
            "يا رفيق",
            "يارفيق",
            "رفيق",
            "رفيج",
            "رفيك",
            "رافيق",
            "رفيقو",
            "توفيق",
            "حفيق",
            "خفيق",
            "وفيق",
            "rafeeq",
            "rafeek",
            "rafeq",
            "rafiq",
            "rafik",
            "rafique",
            "rafig",
            "ofeig",
            "hafik",
            "hafeek",
            "dovek",
            "dovik",
            "dofek",
            "صاحبنا",
            "صاحبي",
        ]
    )
    for pattern in patterns:
        if not pattern:
            continue
        if _is_latin_wake_pattern(pattern):
            match = re.search(
                rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])",
                normalized,
            )
            if match:
                return _clean_wake_command(normalized[match.end() :])
            continue
        compact_pattern = pattern.replace(" ", "")
        if pattern in normalized:
            return _clean_wake_command(normalized.split(pattern, 1)[1])
        if compact_pattern and compact.startswith(compact_pattern):
            return ""
    return None


def _is_latin_wake_pattern(pattern: str) -> bool:
    return bool(re.search(r"[a-z]", pattern))


def _clean_wake_command(command: str) -> str:
    cleaned = command.strip(" \t\r\n.,!?؟،؛:;-_()[]{}\"'")
    if not re.search(r"[0-9a-z\u0600-\u06ff]", cleaned):
        return ""
    return cleaned


def _normalize_wake_text(text: str) -> str:
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
    for mark in ("\u064b", "\u064c", "\u064d", "\u064e", "\u064f", "\u0650", "\u0651", "\u0652"):
        normalized = normalized.replace(mark, "")
    return " ".join(normalized.split())


def _command_loop(
    sync: SyncService | None,
    reminders: ReminderService,
    voice: VoiceIntentRouter | OpenAIRealtimeVoiceAgent,
    voice_input: VoiceInputAdapter | None,
    settings: RobotSettings,
    emergencies: EmergencyManager,
    outbox: OutboxService,
    poems: PoemPracticeService,
    memories: MemoryPracticeService,
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
            transcript = command.split(maxsplit=1)[1]
            if voice_input is not None and poems.can_handle(transcript):
                poems.handle_text(transcript, voice_input)
                print("Voice intent: start_poem_test; handled=True")
                continue
            if voice_input is not None and memories.can_handle(transcript):
                memories.handle_text(transcript, voice_input)
                print("Voice intent: start_photo_test; handled=True")
                continue
            result = voice.handle_text(transcript)
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
            if poems.can_handle(transcript):
                poems.handle_text(transcript, voice_input)
                print("Voice intent: start_poem_test; handled=True")
                continue
            if memories.can_handle(transcript):
                memories.handle_text(transcript, voice_input)
                print("Voice intent: start_photo_test; handled=True")
                continue
            if _handle_read_routine_request(transcript, reminders, speaker, settings.voice_response_locale):
                continue
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
    if settings.voice_interaction_provider == "openai_transcription":
        if not settings.voice_upload_audio:
            print("Voice input disabled: VOICE_UPLOAD_AUDIO must be true for OpenAI transcription.")
            return None
        try:
            return OpenAITranscriptionVoiceInput(
                settings.openai_api_key,
                settings.openai_transcription_model,
                settings.vosk_sample_rate,
                settings.vosk_input_device,
                settings.voice_silence_threshold,
            )
        except Exception as exc:
            print(f"Voice input disabled: {exc}")
            return None
    if settings.voice_interaction_provider != "vosk":
        return None
    try:
        return VoskVoiceInput(
            settings.vosk_model_path,
            settings.vosk_sample_rate,
            settings.vosk_input_device,
        )
    except Exception as exc:
        print(f"Voice input disabled: {exc}")
        return None


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
            settings.openai_text_model,
            settings.openai_reasoning_effort,
            settings.voice_max_session_seconds,
        )
    return local_voice


def _create_speaker(settings: RobotSettings) -> SpeakerAdapter:
    output_device = str(settings.audio_output_device or "plughw:0,0")
    if settings.speaker_provider == "openai_tts":
        return OpenAITTSSpeaker(
            settings,
            EspeakSpeaker(settings.speaker_rate, settings.speaker_volume, output_device),
        )
    if settings.speaker_provider == "espeak":
        return EspeakSpeaker(settings.speaker_rate, settings.speaker_volume, output_device)
    if settings.speaker_provider == "piper":
        return PiperSpeaker(
            settings.piper_voice_model,
            settings.piper_voice_config,
            settings.speaker_volume,
        )
    if settings.speaker_provider == "windows":
        return WindowsSpeechSpeaker(settings.speaker_rate, settings.speaker_volume)
    return ConsoleSpeaker()


class EspeakSpeaker:
    def __init__(self, rate: int = 0, volume: int = 100, output_device: str = "plughw:0,0") -> None:
        self.rate = 150 + max(-10, min(10, rate)) * 10
        self.volume = max(0, min(200, volume * 2))
        self.output_device = output_device
        self._lock = threading.Lock()
        self._speaking_until = 0.0
        self._last_speak_started = 0.0

    def is_speaking(self) -> bool:
        with self._lock:
            return time.monotonic() < self._speaking_until

    def spoke_since(self, started_at: float) -> bool:
        with self._lock:
            return self._last_speak_started >= started_at

    def speak(self, text: str, locale: str = "ar") -> None:
        print(f"[{locale}] {format_console_text(text)}")
        with self._lock:
            self._last_speak_started = time.monotonic()
            self._speaking_until = time.monotonic() + 3600
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as wav_file:
            try:
                result = subprocess.run(
                    [
                        "espeak-ng",
                        "-v",
                        "ar" if locale == "ar" else "en",
                        "-s",
                        str(self.rate),
                        "-a",
                        str(self.volume),
                        "-w",
                        wav_file.name,
                        clean_speech_text(text),
                    ],
                    check=False,
                    stderr=subprocess.PIPE,
                )
                if result.returncode == 0:
                    subprocess.run(["aplay", "-D", self.output_device, wav_file.name], check=False)
            finally:
                with self._lock:
                    self._speaking_until = time.monotonic() + 1.0


class OpenAITTSSpeaker:
    def __init__(self, settings: RobotSettings, fallback: SpeakerAdapter) -> None:
        self.api_key = settings.openai_api_key
        self.model = settings.openai_tts_model
        self.voice = settings.openai_tts_voice
        self.output_device = str(settings.audio_output_device or "plughw:0,0")
        self.fallback = fallback
        self._lock = threading.Lock()
        self._speaking_until = 0.0
        self._last_speak_started = 0.0

    def is_speaking(self) -> bool:
        with self._lock:
            return time.monotonic() < self._speaking_until

    def spoke_since(self, started_at: float) -> bool:
        with self._lock:
            return self._last_speak_started >= started_at

    def speak(self, text: str, locale: str = "ar") -> None:
        print(f"[{locale}] {format_console_text(text)}")
        if not self.api_key:
            self.fallback.speak(text, locale)
            return
        with self._lock:
            self._last_speak_started = time.monotonic()
            self._speaking_until = time.monotonic() + 3600
        try:
            import httpx

            response = httpx.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "voice": self.voice,
                    "input": clean_speech_text(text),
                    "response_format": "wav",
                },
                timeout=15,
            )
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as wav_file:
                wav_file.write(response.content)
                wav_file.flush()
                subprocess.run(["aplay", "-D", self.output_device, wav_file.name], check=False)
        except Exception as exc:
            print(f"OpenAI TTS unavailable; using espeak fallback: {exc}")
            self.fallback.speak(text, locale)
        finally:
            with self._lock:
                self._speaking_until = time.monotonic() + 1.0


if __name__ == "__main__":
    main()
