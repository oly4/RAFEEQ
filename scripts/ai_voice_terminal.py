from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import io
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from uuid import uuid4
import wave
import winsound

import httpx
import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parents[1]
ROBOT_SRC = ROOT / "edge" / "robot" / "src"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROBOT_SRC))

from ai_terminal import _sync, _task_context, _text_model, ask_gpt  # noqa: E402
from rafeeq_robot.config import RobotSettings  # noqa: E402
from rafeeq_robot.persistence.database import RobotDatabase  # noqa: E402


def main() -> None:
    settings = RobotSettings()
    if not settings.openai_api_key:
        raise SystemExit(
            "OPENAI_API_KEY is missing in .env.robot. Add it first, then run again."
        )

    database = RobotDatabase(settings.local_database_path)
    text_model = _text_model(settings)
    listen_seconds = max(1, int(settings.voice_listen_seconds))
    debug = False
    pending_routine: dict[str, Any] | None = None

    print("RAFEEQ clean OpenAI voice test.")
    print(f"Reasoning model: {text_model}")
    print(f"Transcription model: {settings.openai_transcription_model}")
    print(f"TTS model: {settings.openai_tts_model}; voice={settings.openai_tts_voice}")
    print(f"Microphone device: {settings.vosk_input_device}")
    print(f"Speaker device: {settings.audio_output_device}")
    print(
        "Commands: enter=record, record <seconds>, test voice, test mic, "
        "test speakers, say <text>, text <request>, sync, tasks, debug on, debug off, quit"
    )
    print("Tip: speak clearly after you see 'Listening...'.")

    while True:
        try:
            command = input("rafeeq voice> ").strip()
        except EOFError:
            return

        if command in {"quit", "exit"}:
            return
        if command == "sync":
            _sync(settings, database)
            continue
        if command == "tasks":
            print(json.dumps(_task_context(database), ensure_ascii=False, indent=2))
            continue
        if command == "debug on":
            debug = True
            print("Debug text is ON. I will print transcript and answer.")
            continue
        if command == "debug off":
            debug = False
            print("Debug text is OFF. I will only speak the answer.")
            continue
        if command == "test voice":
            _speak_or_report(settings, "هلا، أنا رفيق. الصوت شغّال الحين.")
            continue
        if command == "test mic":
            _test_mic(settings)
            continue
        if command == "test speakers":
            _test_speakers()
            continue
        if command.startswith("say "):
            _speak_or_report(settings, command[4:].strip())
            continue
        if command.startswith("text "):
            transcript = command[5:].strip()
            if not transcript:
                print("Use: text add a meeting at 9")
                continue
            handled = _maybe_handle_task_completion(
                settings, database, transcript, debug
            )
            if handled:
                continue
            handled, pending_routine = _maybe_handle_routine_creation(
                settings,
                database,
                text_model,
                transcript,
                pending_routine,
                debug,
            )
            if handled:
                continue
            answer = ask_gpt(
                settings.openai_api_key,
                text_model,
                transcript,
                _task_context(database),
            )
            print(f"rafeeq> {answer}" if debug else "Speaking...")
            _speak_or_report(settings, answer)
            continue

        seconds = listen_seconds
        if command.startswith("record"):
            parts = command.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    seconds = max(1, int(float(parts[1])))
                except ValueError:
                    print("Use: record 10")
                    continue
        elif command:
            print("Unknown command. Press Enter to record, or use: record 10")
            continue

        try:
            wav_bytes = _record_wav(
                seconds=seconds,
                sample_rate=settings.vosk_sample_rate,
                input_device=settings.vosk_input_device,
            )
            transcript = _transcribe(settings, wav_bytes)
        except Exception as exc:
            print(f"Voice input failed: {exc}")
            _speak_or_report(
                settings,
                "فيه مشكلة بالمايك. تأكد من اختيار المايك وحاول مرة ثانية.",
            )
            continue

        if not transcript:
            print("Transcript was empty. Try speaking louder or use: record 10")
            _speak_or_report(
                settings,
                "ما سمعتك زين. حاول مرة ثانية وتكلم قريب من المايك.",
            )
            continue

        if debug:
            print(f"you> {transcript}")
        else:
            print("Heard you. Thinking...")

        handled = _maybe_handle_task_completion(settings, database, transcript, debug)
        if handled:
            continue

        handled, pending_routine = _maybe_handle_routine_creation(
            settings,
            database,
            text_model,
            transcript,
            pending_routine,
            debug,
        )
        if handled:
            continue

        try:
            answer = ask_gpt(
                settings.openai_api_key,
                text_model,
                transcript,
                _task_context(database),
            )
        except Exception as exc:
            print(f"OpenAI reasoning failed: {exc}")
            continue

        if debug:
            print(f"rafeeq> {answer}")
        else:
            print("Speaking...")
        try:
            _speak(settings, answer)
        except Exception as exc:
            print(f"OpenAI voice playback failed: {exc}")


def _record_wav(seconds: int, sample_rate: int, input_device: int | None) -> bytes:
    print(f"Listening for {seconds} seconds...")
    audio = sd.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=input_device,
    )
    sd.wait()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())
    return buffer.getvalue()


def _transcribe(settings: RobotSettings, wav_bytes: bytes) -> str:
    response = httpx.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        data={
            "model": settings.openai_transcription_model,
            "response_format": "json",
        },
        files={"file": ("speech.wav", wav_bytes, "audio/wav")},
        timeout=90,
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    text = data.get("text")
    return text.strip() if isinstance(text, str) else ""


def _speak(settings: RobotSettings, text: str) -> None:
    response = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_tts_model,
            "voice": settings.openai_tts_voice,
            "input": text,
            "response_format": "wav",
        },
        timeout=90,
    )
    response.raise_for_status()
    try:
        _play_wav_with_sounddevice(response.content, settings.audio_output_device)
        return
    except Exception as sounddevice_error:
        print(
            f"Sounddevice playback failed, trying Windows fallback: {sounddevice_error}"
        )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
        audio_path = audio_file.name
        audio_file.write(response.content)
    try:
        winsound.PlaySound(audio_path, winsound.SND_FILENAME)
    finally:
        Path(audio_path).unlink(missing_ok=True)


def _play_wav_with_sounddevice(wav_bytes: bytes, output_device: int | None) -> None:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    audio = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels)
    sd.play(audio, samplerate=sample_rate, device=output_device)
    sd.wait()


def _test_mic(settings: RobotSettings) -> None:
    try:
        print("Recording microphone level for 3 seconds...")
        audio = sd.rec(
            int(3 * settings.vosk_sample_rate),
            samplerate=settings.vosk_sample_rate,
            channels=1,
            dtype="float32",
            device=settings.vosk_input_device,
        )
        sd.wait()
        peak = float(np.max(np.abs(audio)))
        print(f"Microphone peak level: {peak:.4f}")
        if peak < 0.005:
            print("Mic is very quiet. Check Windows microphone permission/volume.")
        else:
            print("Mic is receiving sound.")
    except Exception as exc:
        print(f"Microphone test failed: {exc}")


def _test_speakers() -> None:
    devices = sd.query_devices()
    output_ids = [
        index
        for index, device in enumerate(devices)
        if int(device.get("max_output_channels", 0)) > 0
    ]
    print("Testing output devices. Tell me which number you hear.")
    for index in output_ids:
        device = devices[index]
        sample_rate = int(device.get("default_samplerate") or 44100)
        print(f"Playing beep on {index}: {device['name']}")
        seconds = 0.45
        t = np.linspace(0, seconds, int(sample_rate * seconds), False)
        tone = (0.18 * np.sin(2 * np.pi * 660 * t)).astype("float32")
        try:
            sd.play(tone, samplerate=sample_rate, device=index)
            sd.wait()
        except Exception as exc:
            print(f"  failed: {exc}")


def _speak_or_report(settings: RobotSettings, text: str) -> None:
    try:
        _speak(settings, text)
    except Exception as exc:
        print(f"OpenAI voice playback failed: {exc}")


def _maybe_handle_task_completion(
    settings: RobotSettings,
    database: RobotDatabase,
    user_text: str,
    debug: bool,
) -> bool:
    if not _looks_like_completion(user_text):
        return False

    match = _find_completion_target(database, user_text)
    if match is None:
        _speak_or_report(
            settings,
            _arabic("ما عرفت أي مهمة تقصد. قل مثلا: خلصت الغداء، أو أخذت الدواء."),
        )
        return True

    if match["status"] == "completed":
        _speak_or_report(
            settings,
            _arabic(f"{match['title']} مسجلة من قبل كمكتملة."),
        )
        return True

    try:
        _publish_reminder_completed(settings, str(match["occurrence_id"]))
        _sync(settings, database)
    except Exception as exc:
        print(f"Task completion failed: {exc}")
        _speak_or_report(
            settings,
            _arabic("فهمت عليك، بس ما قدرت أحدث المهمة في التطبيق."),
        )
        return True

    if debug:
        print(f"completed_task> {json.dumps(match, ensure_ascii=False, default=str)}")
    _speak_or_report(
        settings,
        _arabic(f"تم، سجلت {match['title']} كمكتملة."),
    )
    return True


def _looks_like_completion(text: str) -> bool:
    normalized = text.lower().strip()
    if any(marker in normalized for marker in ("did i", "have i", "هل", "؟", "?")):
        return False
    positive_markers = (
        "i did",
        "i have done",
        "i finished",
        "i completed",
        "done",
        "finished",
        "completed",
        "i took",
        "i ate",
        "i drank",
        "خلصت",
        "انهيت",
        "أنهيت",
        "سويت",
        "عملت",
        "اخذت",
        "أخذت",
        "اكلت",
        "أكلت",
        "شربت",
    )
    return any(marker in normalized for marker in positive_markers)


def _find_completion_target(
    database: RobotDatabase,
    user_text: str,
) -> dict[str, Any] | None:
    tasks = _completion_candidates(database)
    if not tasks:
        return None

    normalized = _normalize_match_text(user_text)
    scored: list[tuple[int, dict[str, Any]]] = [
        (_completion_score(normalized, task), task) for task in tasks
    ]
    scored.sort(key=lambda item: (item[0], item[1]["scheduled_at_utc"]), reverse=True)
    best_score, best_task = scored[0]

    if best_score > 0:
        return best_task

    incomplete = [task for task in tasks if task["status"] != "completed"]
    if len(incomplete) == 1:
        return incomplete[0]
    return None


def _completion_candidates(database: RobotDatabase) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from rafeeq_robot.persistence.models import LocalOccurrence, LocalRoutine

    with database.session() as session:
        occurrences = list(
            session.scalars(
                select(LocalOccurrence).order_by(
                    LocalOccurrence.scheduled_at_utc.desc()
                )
            ).all()
        )
        tasks: list[dict[str, Any]] = []
        for occurrence in occurrences:
            routine = session.get(LocalRoutine, occurrence.routine_id)
            if routine is None:
                continue
            tasks.append(
                {
                    "occurrence_id": occurrence.id,
                    "routine_id": routine.id,
                    "title": routine.title,
                    "type": routine.type,
                    "status": occurrence.status,
                    "scheduled_at_utc": occurrence.scheduled_at_utc,
                    "medication": routine.payload_json.get("medication"),
                    "description": routine.payload_json.get("description"),
                }
            )
        return tasks


def _completion_score(normalized_user_text: str, task: dict[str, Any]) -> int:
    score = 0
    title = _normalize_match_text(str(task["title"]))
    title_words = [word for word in title.split() if len(word) > 2]
    score += sum(4 for word in title_words if word in normalized_user_text)
    routine_type = str(task["type"])
    type_words = {
        "medication": (
            "دواء",
            "دوا",
            "medicine",
            "medication",
            "pill",
            "medcin",
            "medcine",
        ),
        "meal": (
            "اكل",
            "أكل",
            "غداء",
            "فطور",
            "عشاء",
            "meal",
            "food",
            "eat",
            "lunch",
            "dinner",
        ),
        "water": ("ماء", "اشرب", "شرب", "water", "drink"),
        "appointment": ("موعد", "اجتماع", "meeting", "appointment"),
        "memory_exercise": ("ذاكره", "ذاكرة", "memory", "exercise"),
        "conversation": ("محادثه", "محادثة", "conversation", "talk"),
        "custom": ("مهمه", "مهمة", "نشاط", "task", "activity"),
    }
    score += sum(
        3 for word in type_words.get(routine_type, ()) if word in normalized_user_text
    )
    medication = task.get("medication") or {}
    if isinstance(medication, dict):
        for value in (medication.get("medication_name"), medication.get("dosage_text")):
            if isinstance(value, str):
                words = [
                    word
                    for word in _normalize_match_text(value).split()
                    if len(word) > 2
                ]
                score += sum(3 for word in words if word in normalized_user_text)
    return score


def _publish_reminder_completed(settings: RobotSettings, occurrence_id: str) -> None:
    event_id = str(uuid4())
    occurred_at = datetime.now(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
    payload = {
        "events": [
            {
                "schema_version": 1,
                "event_id": event_id,
                "event_type": "reminder_completed",
                "device_id": settings.rafeeq_device_id,
                "patient_id": settings.rafeeq_patient_id,
                "occurred_at": occurred_at,
                "sequence": 0,
                "payload": {
                    "occurrence_id": occurrence_id,
                    "confirmation_source": "patient_voice",
                },
            }
        ]
    }
    with httpx.Client(base_url=settings.backend_base_url, timeout=15) as client:
        response = client.post(
            "/device-api/v1/events/batch",
            headers={
                "X-Device-Id": settings.rafeeq_device_id,
                "X-Device-Secret": settings.rafeeq_device_secret,
            },
            json=payload,
        )
        response.raise_for_status()


def _normalize_match_text(text: str) -> str:
    normalized = text.strip().casefold()
    normalized = normalized.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
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


def _maybe_handle_routine_creation(
    settings: RobotSettings,
    database: RobotDatabase,
    model: str,
    user_text: str,
    pending: dict[str, Any] | None,
    debug: bool,
) -> tuple[bool, dict[str, Any] | None]:
    if pending is not None:
        return _handle_pending_routine(settings, database, user_text, pending, debug)

    plan = _extract_routine_plan(settings, model, user_text)
    if debug:
        print(f"routine_plan> {json.dumps(plan, ensure_ascii=False)}")
    if plan.get("action") != "create_routine":
        return False, None

    if plan.get("type") == "medication" and not _medication_is_complete(plan):
        _speak_or_report(
            settings,
            _arabic(
                "ما أقدر أضيف دواء بالصوت بدون اسم الدواء والجرعة. "
                "الأفضل تضيفه من تطبيق العائلة، أو قل الاسم والجرعة والوقت بوضوح."
            ),
        )
        return True, None

    missing = _missing_routine_fields(plan)
    if missing:
        _speak_or_report(
            settings,
            _arabic(f"فهمت إنك تبي تضيف موعد، بس أحتاج {missing}."),
        )
        return True, None

    if plan.get("needs_meridiem"):
        pending = dict(plan)
        _speak_or_report(
            settings,
            _arabic(f"تقصد {plan['display_time']} الصبح ولا بالليل؟"),
        )
        return True, pending

    try:
        created = _create_backend_routine(settings, plan)
        _sync(settings, database)
    except Exception as exc:
        print(f"Routine creation failed: {exc}")
        _speak_or_report(
            settings,
            _arabic("فهمت الطلب، بس ما قدرت أحفظه في التطبيق."),
        )
        return True, None

    if debug:
        print(f"created_routine> {json.dumps(created, ensure_ascii=False)}")
    _speak_or_report(
        settings,
        _arabic(f"تم، أضفت {plan['title']} الساعة {plan['display_time']}."),
    )
    return True, None


def _handle_pending_routine(
    settings: RobotSettings,
    database: RobotDatabase,
    user_text: str,
    pending: dict[str, Any],
    debug: bool,
) -> tuple[bool, dict[str, Any] | None]:
    if pending.get("needs_meridiem"):
        meridiem = _detect_meridiem(user_text)
        if meridiem is None:
            _speak_or_report(
                settings,
                _arabic("تقصد الصبح ولا بالليل؟"),
            )
            return True, pending
        pending["time_24h"] = _apply_meridiem(int(pending["hour_12"]), meridiem)
        pending["display_time"] = _display_time(pending["time_24h"])
        pending["needs_meridiem"] = False
        try:
            created = _create_backend_routine(settings, pending)
            _sync(settings, database)
        except Exception as exc:
            print(f"Routine creation failed: {exc}")
            _speak_or_report(
                settings,
                _arabic("فهمت الطلب، بس ما قدرت أحفظه في التطبيق."),
            )
            return True, None

        if debug:
            print(f"created_routine> {json.dumps(created, ensure_ascii=False)}")
        _speak_or_report(
            settings,
            _arabic(f"تم، أضفت {pending['title']} الساعة {pending['display_time']}."),
        )
        return True, None

    if _is_yes(user_text):
        try:
            created = _create_backend_routine(settings, pending)
            _sync(settings, database)
        except Exception as exc:
            print(f"Routine creation failed: {exc}")
            _speak_or_report(
                settings,
                _arabic(
                    "فهمت الطلب، بس ما قدرت أحفظه في التطبيق. "
                    "تأكد من إعداد تسجيل دخول العائلة في ملف البيئة."
                ),
            )
            return True, None

        if debug:
            print(f"created_routine> {json.dumps(created, ensure_ascii=False)}")
        _speak_or_report(
            settings,
            _arabic(
                f"تم الحفظ، أضفت {pending['title']} الساعة {pending['display_time']}."
            ),
        )
        return True, None

    if _is_no(user_text):
        _speak_or_report(settings, _arabic("تمام، ما حفظت الموعد."))
        return True, None

    _speak_or_report(
        settings,
        _arabic("تبيني أحفظ الموعد؟ قل نعم للحفظ أو لا للإلغاء."),
    )
    return True, pending


def _extract_routine_plan(
    settings: RobotSettings,
    model: str,
    user_text: str,
) -> dict[str, Any]:
    quick = _quick_extract_routine_plan(user_text)
    if quick is not None:
        return quick

    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "instructions": (
                "Extract whether the user is asking RAFEEQ to create a routine item. "
                "Return only compact JSON. No markdown. Schema: "
                "{action:'create_routine'|'none', type:'medication'|'meal'|'water'|"
                "'appointment'|'spiritual'|'memory_exercise'|'conversation'|'custom'|null, "
                "title:string|null, time_24h:'HH:MM'|null, hour_12:number|null, "
                "needs_meridiem:boolean, display_time:string|null, "
                "medication:{medication_name:string|null,dosage_text:string|null,"
                "instructions:string|null}|null}. "
                "If the user says a bare hour like 9 without AM/PM, set hour_12 and "
                "needs_meridiem=true. Do not infer medication dosage."
            ),
            "input": user_text,
        },
        timeout=60,
    )
    response.raise_for_status()
    text = _response_text(response.json())
    try:
        plan = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {"action": "none"}
        plan = json.loads(match.group(0))
    return _normalize_plan(plan)


def _quick_extract_routine_plan(user_text: str) -> dict[str, Any] | None:
    normalized = user_text.strip().lower()
    if not re.search(r"\b(add|create|schedule|remind)\b", normalized):
        return None
    match = re.search(r"\b(?:at|@)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", normalized)
    if not match:
        return None
    title = re.sub(r"\b(add|create|schedule|remind|me|a|an|the)\b", "", normalized)
    title = re.sub(r"\b(?:at|@)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", "", title)
    title = " ".join(title.split()) or "meeting"
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem is None and 1 <= hour <= 11:
        return _normalize_plan(
            {
                "action": "create_routine",
                "type": "appointment" if "meeting" in title else "custom",
                "title": title,
                "time_24h": None,
                "hour_12": hour,
                "minute": minute,
                "needs_meridiem": True,
                "display_time": f"{hour}:{minute:02d}",
                "medication": None,
            }
        )
    if meridiem is not None:
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    return _normalize_plan(
        {
            "action": "create_routine",
            "type": "appointment" if "meeting" in title else "custom",
            "title": title,
            "time_24h": f"{hour:02d}:{minute:02d}",
            "needs_meridiem": False,
            "display_time": f"{hour:02d}:{minute:02d}",
            "medication": None,
        }
    )


def _normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    allowed_types = {
        "medication",
        "meal",
        "water",
        "appointment",
        "spiritual",
        "memory_exercise",
        "conversation",
        "custom",
    }
    if plan.get("action") != "create_routine":
        return {"action": "none"}
    routine_type = str(plan.get("type") or "custom")
    if routine_type not in allowed_types:
        routine_type = "custom"
    title = str(plan.get("title") or "").strip()
    if not title:
        title = "موعد" if routine_type == "appointment" else "نشاط"
    time_24h = plan.get("time_24h")
    if isinstance(time_24h, str) and re.match(r"^\d{1,2}:\d{2}$", time_24h):
        hour, minute = [int(part) for part in time_24h.split(":")]
        time_24h = f"{hour:02d}:{minute:02d}"
    else:
        time_24h = None
    hour_12 = plan.get("hour_12")
    try:
        hour_12 = int(hour_12) if hour_12 is not None else None
    except (TypeError, ValueError):
        hour_12 = None
    minute = plan.get("minute")
    try:
        minute = int(minute) if minute is not None else 0
    except (TypeError, ValueError):
        minute = 0
    return {
        "action": "create_routine",
        "type": routine_type,
        "title": title,
        "time_24h": time_24h,
        "hour_12": hour_12,
        "minute": minute,
        "needs_meridiem": bool(plan.get("needs_meridiem")),
        "display_time": str(plan.get("display_time") or time_24h or hour_12 or ""),
        "medication": plan.get("medication")
        if isinstance(plan.get("medication"), dict)
        else None,
    }


def _missing_routine_fields(plan: dict[str, Any]) -> str:
    if not plan.get("title"):
        return _arabic("اسم النشاط")
    if not plan.get("time_24h") and not plan.get("needs_meridiem"):
        return _arabic("الوقت")
    return ""


def _medication_is_complete(plan: dict[str, Any]) -> bool:
    medication = plan.get("medication")
    if not isinstance(medication, dict):
        return False
    return bool(medication.get("medication_name") and medication.get("dosage_text"))


def _confirmation_text(plan: dict[str, Any]) -> str:
    return _arabic(f"بضيف {plan['title']} الساعة {plan['display_time']}. أحفظه؟")


def _create_backend_routine(
    settings: RobotSettings,
    plan: dict[str, Any],
) -> dict[str, Any]:
    timezone_name = "Europe/London"
    try:
        today = datetime.now(ZoneInfo(timezone_name)).date()
    except ZoneInfoNotFoundError:
        today = datetime.now().date()

    payload: dict[str, Any] = {
        "type": plan["type"],
        "title": plan["title"],
        "description": "Created by RAFEEQ voice assistant.",
        "timezone": timezone_name,
        "start_date": today.isoformat(),
        "end_date": today.isoformat(),
        "recurrence_rule": "FREQ=DAILY;COUNT=1",
        "scheduled_local_time": f"{plan['time_24h']}:00",
        "requires_confirmation": True,
        "snooze_minutes": 10,
        "max_snoozes": 2,
    }
    if plan["type"] == "medication":
        payload["medication"] = plan["medication"]
        token = _backend_access_token(settings)
        with httpx.Client(base_url=settings.backend_base_url, timeout=15) as client:
            response = client.post(
                f"/api/v1/patients/{settings.rafeeq_patient_id}/routines",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    with httpx.Client(base_url=settings.backend_base_url, timeout=15) as client:
        response = client.post(
            "/device-api/v1/voice-routines",
            headers={
                "X-Device-Id": settings.rafeeq_device_id,
                "X-Device-Secret": settings.rafeeq_device_secret,
            },
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def _backend_access_token(settings: RobotSettings) -> str:
    if settings.rafeeq_voice_access_token:
        return settings.rafeeq_voice_access_token
    if (
        not settings.rafeeq_voice_caregiver_email
        or not settings.rafeeq_voice_caregiver_password
    ):
        raise RuntimeError(
            "Set RAFEEQ_VOICE_ACCESS_TOKEN or RAFEEQ_VOICE_CAREGIVER_EMAIL/"
            "RAFEEQ_VOICE_CAREGIVER_PASSWORD in .env.robot."
        )
    with httpx.Client(base_url=settings.backend_base_url, timeout=15) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": settings.rafeeq_voice_caregiver_email,
                "password": settings.rafeeq_voice_caregiver_password,
            },
        )
        response.raise_for_status()
        return str(response.json()["access_token"])


def _response_text(data: dict[str, Any]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts).strip()


def _detect_meridiem(text: str) -> str | None:
    normalized = text.lower()
    if any(word in normalized for word in ("am", "morning", "صباح", "الصباح", "الصبح")):
        return "am"
    if any(
        word in normalized
        for word in ("pm", "evening", "night", "مساء", "المساء", "ليل", "بالليل")
    ):
        return "pm"
    return None


def _apply_meridiem(hour_12: int, meridiem: str) -> str:
    hour = hour_12
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:00"


def _display_time(time_24h: str) -> str:
    hour, minute = [int(part) for part in time_24h.split(":")]
    meridiem = "الصبح" if hour < 12 else "بالليل"
    hour_12 = hour % 12 or 12
    return f"{hour_12}:{minute:02d} {meridiem}"


def _is_yes(text: str) -> bool:
    normalized = text.lower().strip()
    return any(
        word in normalized
        for word in (
            "yes",
            "yeah",
            "ok",
            "okay",
            "save",
            "نعم",
            "ايه",
            "اي",
            "أبشر",
            "احفظ",
            "تمام",
        )
    )


def _is_no(text: str) -> bool:
    normalized = text.lower().strip()
    return any(
        word in normalized
        for word in ("no", "cancel", "don't", "dont", "لا", "الغ", "إلغاء")
    )


def _arabic(text: str) -> str:
    return text


if __name__ == "__main__":
    main()
