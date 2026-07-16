import sys
import subprocess
import time
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
        if sync:
            scheduler.add_job(sync.synchronize, "interval", seconds=60, max_instances=1)
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
    if daemon:
        if sync:
            try:
                version = sync.synchronize()
                print(f"Initial synchronization complete: {version}")
            except Exception as exc:
                print(f"Initial synchronization failed; local behavior remains active: {exc}")
        if voice_input is not None:
            _start_daemon_voice_loop(voice, voice_input, settings, speaker)
        print("Daemon mode active.")
        try:
            while True:
                time.sleep(3600)
        finally:
            scheduler.shutdown(wait=False)
            if client:
                client.close()
        return
    try:
        _command_loop(sync, reminders, voice, voice_input, settings, emergencies, outbox)
    finally:
        scheduler.shutdown(wait=False)
        if client:
            client.close()


def _start_daemon_voice_loop(
    voice: VoiceIntentRouter | OpenAIRealtimeVoiceAgent,
    voice_input: VoiceInputAdapter,
    settings: RobotSettings,
    speaker: SpeakerAdapter,
) -> None:
    def worker() -> None:
        description = getattr(voice_input, "description", "configured microphone")
        print(f"Daemon voice loop active: {description}")
        awake_until = 0.0
        voice_paused = False
        external_pause_logged = False
        mic_reserved_logged = False
        pending_transcript: str | None = None
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
            now = time.monotonic()
            external_paused = _is_terminal_voice_paused()
            if external_paused and not external_pause_logged:
                print("Voice paused by terminal command.")
                external_pause_logged = True
            if not external_paused:
                external_pause_logged = False
            if voice_paused or external_paused:
                wake_command = _extract_wake_command(transcript, settings.voice_wake_words)
                if wake_command is not None and _is_start_hearing_command(wake_command or transcript):
                    voice_paused = False
                    _set_terminal_voice_paused(False)
                    external_pause_logged = False
                    pending_transcript = None
                    awake_until = now + max(10, min(settings.voice_max_session_seconds, 120))
                    speaker.speak("رجعت أسمعك.", "ar")
                    print("Voice listening resumed by wake command.")
                else:
                    print("Voice paused: waiting for 'RafeeQ start hearing'.")
                time.sleep(0.5)
                continue
            if settings.voice_wake_word_required:
                wake_command = _extract_wake_command(transcript, settings.voice_wake_words)
                if wake_command is None and now >= awake_until:
                    print("Voice transcript ignored: wake word was not heard.")
                    time.sleep(0.5)
                    continue
                if wake_command is not None:
                    awake_until = now + max(10, min(settings.voice_max_session_seconds, 120))
                    speaker.speak("سمعتك.", "ar")
                    if not wake_command:
                        time.sleep(0.5)
                        continue
                    transcript = wake_command
                    print(f"Wake command: {format_console_text(transcript)}")
                else:
                    awake_until = now + max(10, min(settings.voice_max_session_seconds, 120))
                    print("Voice transcript accepted during active wake session.")
            if _is_stop_hearing_command(transcript):
                voice_paused = True
                _set_terminal_voice_paused(True)
                external_pause_logged = True
                pending_transcript = None
                awake_until = 0.0
                speaker.speak("تم، وقفت سماع الأوامر. قل يا رفيق اسمعني عشان أرجع.", "ar")
                print("Voice listening paused by command.")
                time.sleep(0.5)
                continue
            if _is_start_hearing_command(transcript):
                speaker.speak("أنا أسمعك.", "ar")
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
                        speaker.speak("تم، ألغيت الأمر.", "ar")
                        time.sleep(0.5)
                        continue
                    else:
                        pending_transcript = transcript
                        print(f"Voice pending transcript updated: {format_console_text(transcript)}")
                        speaker.speak(
                            f"سمعت: {transcript}. قل تأكيد عشان أنفذ.",
                            "ar",
                        )
                        time.sleep(0.5)
                        continue
                elif not _is_voice_confirmation(transcript):
                    pending_transcript = transcript
                    print(f"Voice pending transcript: {format_console_text(transcript)}")
                    speaker.speak(
                        f"سمعت: {transcript}. قل تأكيد عشان أنفذ.",
                        "ar",
                    )
                    time.sleep(0.5)
                    continue
            try:
                result = voice.handle_text(
                    transcript,
                    source=settings.voice_interaction_provider,
                )
                print(f"Voice intent: {result.intent}; handled={result.handled}")
            except Exception as exc:
                print(f"Voice handling failed: {exc}")
            time.sleep(0.5)

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
    patterns.extend(["يا رفيق", "يارفيق", "رفيق", "رفيج", "rafeeq", "rafeeq"])
    for pattern in patterns:
        if not pattern:
            continue
        compact_pattern = pattern.replace(" ", "")
        if pattern in normalized:
            return normalized.split(pattern, 1)[1].strip()
        if compact_pattern and compact_pattern in compact:
            return normalized.replace(pattern, "", 1).strip()
    return None


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
    if settings.speaker_provider == "openai_tts":
        return OpenAITTSSpeaker(settings, EspeakSpeaker(settings.speaker_rate, settings.speaker_volume))
    if settings.speaker_provider == "espeak":
        return EspeakSpeaker(settings.speaker_rate, settings.speaker_volume)
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
    def __init__(self, rate: int = 0, volume: int = 100) -> None:
        self.rate = 150 + max(-10, min(10, rate)) * 10
        self.volume = max(0, min(200, volume * 2))
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
                    subprocess.run(["aplay", "-D", "plughw:0,0", wav_file.name], check=False)
            finally:
                with self._lock:
                    self._speaking_until = time.monotonic() + 1.0


class OpenAITTSSpeaker:
    def __init__(self, settings: RobotSettings, fallback: SpeakerAdapter) -> None:
        self.api_key = settings.openai_api_key
        self.model = settings.openai_tts_model
        self.voice = settings.openai_tts_voice
        self.output_device = "plughw:0,0"
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
                timeout=45,
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
