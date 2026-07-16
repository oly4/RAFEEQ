from __future__ import annotations

import base64
import io
import json
import msvcrt
from pathlib import Path
import queue
import random
import re
import sys
import tempfile
import time
import wave
import winsound
from typing import Any

import httpx
import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model

ROOT = Path(__file__).resolve().parents[1]
ROBOT_SRC = ROOT / "edge" / "robot" / "src"
sys.path.insert(0, str(ROBOT_SRC))

from rafeeq_robot.config import RobotSettings  # noqa: E402


DEFAULT_EMAIL = "rafeeq.family.test@example.com"
DEFAULT_PASSWORD = "Rafeeq-Test-2026!"
COMMAND_MAX_SECONDS = 15.0
COMMAND_RECORD_SECONDS = 5.0
COMMAND_FIXED_RECORDING = True
COMMAND_START_TIMEOUT_SECONDS = 5.0
COMMAND_END_SILENCE_SECONDS = 2.0
COMMAND_MIN_SECONDS = 0.8
COMMAND_RMS_FLOOR = 650.0
COMMAND_EXTENSION_RMS_FLOOR = 380.0
COMMAND_MIN_VOICE_SECONDS = 0.45
COMMAND_MIN_PEAK = 1200

WAKE_PATTERNS = (
    "يا رفيق",
    "يارفيق",
    "يا رفيج",
    "رفيق",
    "رفيج",
    "rafeeq",
    "rafiq",
)


def _verbose_logging() -> bool:
    return "--verbose" in sys.argv or "--debug" in sys.argv


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    lock_handle = _acquire_single_instance_lock()
    if lock_handle is None:
        print("RAFEEQ wake-word assistant is already running.")
        return

    settings = RobotSettings()
    if "--devices" in sys.argv:
        print("Default devices:", sd.default.device)
        print(sd.query_devices())
        return
    if "--test-mic" in sys.argv:
        _test_mic(settings)
        return
    if "--test-speaker" in sys.argv:
        _speak_text(settings, "مرحبا، أنا رفيق. إذا سمعتني فالصوت شغال.")
        return

    model_path = Path(settings.vosk_model_path)
    if not model_path.exists():
        raise SystemExit(f"Vosk model not found: {model_path}")

    backend_base_url = settings.backend_base_url.rstrip("/")
    email = settings.rafeeq_voice_caregiver_email or DEFAULT_EMAIL
    password = settings.rafeeq_voice_caregiver_password or DEFAULT_PASSWORD
    try:
        token, patient_id = _login_and_patient(backend_base_url, email, password)
    except httpx.ConnectError:
        raise SystemExit(
            "RAFEEQ backend is not running. Start it first:\n"
            "  powershell -ExecutionPolicy Bypass -File scripts\\run_app_windows.ps1\n"
            "Then run this wake-word script again."
        )
    except httpx.HTTPStatusError as exc:
        raise SystemExit(
            f"RAFEEQ login failed: {exc.response.status_code} {exc.response.text}"
        )

    print("RAFEEQ wake-word assistant is running.")
    print("Wake word: يا رفيق")
    print(f"Backend: {backend_base_url}")
    print(f"Patient: {patient_id}")
    print(f"Mic device: {settings.vosk_input_device}")
    print("Say 'يا رفيق', wait for the beep, then say your command.")
    print("Press Ctrl+C to stop.")

    model = Model(str(model_path))
    sample_rate = int(settings.vosk_sample_rate)
    recognizer = KaldiRecognizer(model, sample_rate)
    audio_queue: queue.Queue[bytes] = queue.Queue()
    last_wake_at = 0.0
    last_debug_text = ""
    last_debug_at = 0.0
    debug_local = "--debug" in sys.argv
    verbose = "--verbose" in sys.argv or debug_local
    no_wake_mode = "--no-wake" in sys.argv

    def callback(indata: bytes, frames: int, time_info: Any, status: Any) -> None:
        if status and verbose:
            print(f"Audio status: {status}")
        audio_queue.put(bytes(indata))

    try:
        try:
            input_stream = sd.RawInputStream(
                samplerate=sample_rate,
                blocksize=1600,
                dtype="int16",
                channels=1,
                callback=callback,
                device=settings.vosk_input_device,
            )
        except Exception as exc:
            print(
                f"Could not open mic device {settings.vosk_input_device}: {exc}. "
                "Trying default microphone..."
            )
            input_stream = sd.RawInputStream(
                samplerate=sample_rate,
                blocksize=1600,
                dtype="int16",
                channels=1,
                callback=callback,
                device=None,
            )
        with input_stream:
            if no_wake_mode:
                if verbose:
                    print("\nNo-wake mode: press Enter or speak after every beep.")
                _beep()
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key in ("\r", "\n"):
                        last_wake_at = time.monotonic()
                        _beep()
                        if verbose:
                            print("\nManual listen started.")
                        _drain_audio_queue(audio_queue)
                        _handle_command(
                            settings,
                            backend_base_url,
                            token,
                            patient_id,
                            audio_queue,
                            model,
                        )
                        recognizer.Reset()
                        if verbose:
                            print("\nListening for: يا رفيق")
                        if no_wake_mode:
                            if verbose:
                                print(
                                    "Press Enter for next command, or Ctrl+C to stop."
                                )
                        continue

                try:
                    data = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                heard = ""
                if recognizer.AcceptWaveform(data):
                    heard = _extract_text(recognizer.Result())
                else:
                    heard = _extract_text(recognizer.PartialResult(), key="partial")
                if (
                    debug_local
                    and heard
                    and heard != last_debug_text
                    and time.monotonic() - last_debug_at > 1.5
                ):
                    last_debug_text = heard
                    last_debug_at = time.monotonic()
                    print(f"Local heard: {heard}", flush=True)
                if not heard:
                    continue
                if no_wake_mode and time.monotonic() - last_wake_at > 7.0:
                    last_wake_at = time.monotonic()
                    _beep()
                    if verbose:
                        print(f"\nSpeech heard, starting command capture: {heard}")
                    _drain_audio_queue(audio_queue)
                    _handle_command(
                        settings,
                        backend_base_url,
                        token,
                        patient_id,
                        audio_queue,
                        model,
                    )
                    recognizer.Reset()
                    if verbose:
                        print(
                            "\nNo-wake mode: speak again after the beep, or Ctrl+C to stop."
                        )
                    continue
                if _has_wake_word(heard) and time.monotonic() - last_wake_at > 2.5:
                    last_wake_at = time.monotonic()
                    _beep()
                    if verbose:
                        print(f"\nWake heard: {heard}")
                    _drain_audio_queue(audio_queue)
                    _handle_command(
                        settings,
                        backend_base_url,
                        token,
                        patient_id,
                        audio_queue,
                        model,
                    )
                    recognizer.Reset()
                    if verbose:
                        print("\nListening for: يا رفيق")
    except KeyboardInterrupt:
        print("\nStopped RAFEEQ wake-word assistant.")
    finally:
        try:
            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            lock_handle.close()
        except OSError:
            pass


def _acquire_single_instance_lock():
    lock_path = ROOT / ".run" / "wake_word.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def _login_and_patient(base_url: str, email: str, password: str) -> tuple[str, str]:
    with httpx.Client(timeout=30) as client:
        login = client.post(
            f"{base_url}/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        patients = client.get(
            f"{base_url}/api/v1/patients",
            headers={"Authorization": f"Bearer {token}"},
        )
        patients.raise_for_status()
        payload = patients.json()
        items = payload["items"] if isinstance(payload, dict) else payload
        if not items:
            raise RuntimeError("No patient found for this caregiver account.")
        return token, items[0]["id"]


def _handle_command(
    settings: RobotSettings,
    base_url: str,
    token: str,
    patient_id: str,
    audio_queue: queue.Queue[bytes],
    model: Model,
) -> None:
    try:
        if _verbose_logging():
            print("قل أمرك الآن...")
        wav_bytes = _record_command_wav(
            audio_queue=audio_queue,
            sample_rate=int(settings.vosk_sample_rate),
            model=model,
        )
        if wav_bytes is None:
            if _verbose_logging():
                print(
                    "ما سمعت أمر واضح بعد كلمة التنبيه. حاول تقول الأمر بعد الصفارة مباشرة."
                )
            _beep(frequency=360, duration_ms=180)
            return
        data_url = "data:audio/wav;base64," + base64.b64encode(wav_bytes).decode(
            "ascii"
        )
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{base_url}/api/v1/patients/{patient_id}/voice-command",
                headers={"Authorization": f"Bearer {token}"},
                json={"audio_data_url": data_url},
            )
            response.raise_for_status()
            result = response.json()
        action = result.get("action") or "unknown"
        assistant_text = result.get("assistant_text") or "تم."
        if "--verbose" in sys.argv:
            transcript = result.get("transcript") or ""
            print(f"You said: {transcript}")
            print(f"Action: {action}")
            print(f"RAFEEQ: {assistant_text}")
        audio_data_url = result.get("audio_data_url")
        if isinstance(audio_data_url, str) and audio_data_url:
            _play_audio_data_url(audio_data_url, settings.audio_output_device)
        else:
            _beep(frequency=520, duration_ms=140)
        if action == "start_poem_test":
            _run_poem_activity(
                settings=settings,
                base_url=base_url,
                token=token,
                patient_id=patient_id,
                audio_queue=audio_queue,
                model=model,
            )
    except Exception as exc:
        if _verbose_logging():
            print(f"Command failed: {exc}")
        _beep(frequency=280, duration_ms=220)


def _run_poem_activity(
    *,
    settings: RobotSettings,
    base_url: str,
    token: str,
    patient_id: str,
    audio_queue: queue.Queue[bytes],
    model: Model,
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=120) as client:
        poems_response = client.get(
            f"{base_url}/api/v1/patients/{patient_id}/activities/poems",
            headers=headers,
        )
        poems_response.raise_for_status()
        poems = poems_response.json()
        if not isinstance(poems, list) or not poems:
            _speak_text(
                settings,
                "ما عندي قصائد محفوظة للحين. أضف قصيدة من صفحة الأنشطة، وبعدها أقدر أختبرك فيها.",
            )
            return

        poem_options = [item for item in poems if isinstance(item, dict)]
        if not poem_options:
            _speak_text(settings, "قائمة القصائد ما وصلتني بشكل صحيح. جرب بعد شوي.")
            return
        poem = random.choice(poem_options)
        title = str(poem.get("title") or "قصيدة جميلة")
        poem_start = str(poem.get("poem_start") or "").strip()
        expected_completion = str(poem.get("expected_completion") or "").strip()
        if not poem_start or not expected_completion:
            _speak_text(
                settings, "لقيت قصيدة، لكن بياناتها ناقصة. افتح الأنشطة وعدّلها."
            )
            return

        _speak_text(
            settings,
            f"أبشر. اخترت لك {title}. بقرأ لك البداية، وخذ راحتك كمل اللي تتذكره.",
        )
        speech_response = client.post(
            f"{base_url}/api/v1/patients/{patient_id}/activities/poem-speech",
            headers=headers,
            json={"poem_start": poem_start},
        )
        speech_response.raise_for_status()
        speech_audio = speech_response.json().get("audio_data_url")
        if isinstance(speech_audio, str) and speech_audio:
            _play_audio_data_url(speech_audio, settings.audio_output_device)
        else:
            _speak_text(settings, poem_start)

        for attempt in range(1, 3):
            if attempt == 1:
                _speak_text(settings, "الحين كمل القصيدة بصوتك. أنا سامعك.")
            else:
                _speak_text(
                    settings, "خلنا نحاول مرة ثانية بهدوء. كمل من المكان اللي تذكره."
                )
            _drain_audio_queue(audio_queue)
            answer_wav = _record_command_wav(
                audio_queue=audio_queue,
                sample_rate=int(settings.vosk_sample_rate),
                model=model,
            )
            if answer_wav is None:
                _speak_text(
                    settings, "ما سمعت إجابة واضحة. ولا يهمك، نقدر نعيدها بعد شوي."
                )
                return
            answer_data_url = "data:audio/wav;base64," + base64.b64encode(
                answer_wav
            ).decode("ascii")
            evaluation_response = client.post(
                f"{base_url}/api/v1/patients/{patient_id}/activities/poem-voice-test",
                headers=headers,
                json={
                    "poem_start": poem_start,
                    "expected_completion": expected_completion,
                    "audio_data_url": answer_data_url,
                },
            )
            evaluation_response.raise_for_status()
            evaluation = evaluation_response.json()
            transcript = evaluation.get("transcript") or ""
            matched = bool(evaluation.get("matched"))
            assistant_text = str(evaluation.get("assistant_text") or "").strip()
            if "--verbose" in sys.argv:
                print(f"Poem attempt {attempt}: {transcript}")
                print(f"Poem matched: {matched}")
            audio_data_url = evaluation.get("audio_data_url")
            if isinstance(audio_data_url, str) and audio_data_url:
                _play_audio_data_url(audio_data_url, settings.audio_output_device)
            elif assistant_text:
                _speak_text(settings, assistant_text)
            if matched:
                return

        _speak_text(
            settings,
            f"ما قصّرت. خلني أساعدك. التكملة هي: {expected_completion}. نعيدها مرة ثانية وقت ما تحب.",
        )


def _record_command_wav(
    *,
    audio_queue: queue.Queue[bytes],
    sample_rate: int,
    model: Model,
) -> bytes | None:
    if COMMAND_FIXED_RECORDING:
        return _record_fixed_command_wav(
            audio_queue=audio_queue, sample_rate=sample_rate
        )

    chunks: list[bytes] = []
    pre_speech_chunks: list[bytes] = []
    noise_samples: list[float] = []
    command_recognizer = KaldiRecognizer(model, sample_rate)
    speech_started = False
    first_voice_at = 0.0
    last_voice_at = 0.0
    voice_bytes = 0
    started_at = time.monotonic()
    stop_reason = "timeout"
    if _verbose_logging():
        print("أنتظر كلامك... بس اسكت ثانية بعد ما تخلص.")
    while True:
        now = time.monotonic()
        if now - started_at > COMMAND_MAX_SECONDS:
            stop_reason = "max time"
            break
        try:
            data = audio_queue.get(timeout=0.35)
        except queue.Empty:
            if (
                speech_started
                and time.monotonic() - last_voice_at >= COMMAND_END_SILENCE_SECONDS
            ):
                break
            if (
                not speech_started
                and time.monotonic() - started_at > COMMAND_START_TIMEOUT_SECONDS
            ):
                return None
            continue

        now = time.monotonic()
        endpoint_reached = command_recognizer.AcceptWaveform(data)
        rms = _rms_int16(data)
        if not speech_started and now - started_at <= 0.65:
            noise_samples.append(rms)
        threshold = max(COMMAND_RMS_FLOOR, _median(noise_samples) * 2.6)
        has_voice = rms >= threshold

        if not speech_started:
            pre_speech_chunks.append(data)
            del pre_speech_chunks[:-4]
            if has_voice and now - started_at > 0.25:
                speech_started = True
                first_voice_at = now
                last_voice_at = now
                chunks.extend(pre_speech_chunks)
                if _verbose_logging():
                    print("سمعتك، كمل...")
            elif now - started_at > COMMAND_START_TIMEOUT_SECONDS:
                return None
            continue

        chunks.append(data)
        if has_voice:
            last_voice_at = now
            voice_bytes += len(data)
        spoken_for = now - first_voice_at
        if endpoint_reached and spoken_for >= COMMAND_MIN_SECONDS:
            stop_reason = "speech end"
            break
        if (
            spoken_for >= COMMAND_MIN_SECONDS
            and now - last_voice_at >= COMMAND_END_SILENCE_SECONDS
        ):
            stop_reason = "silence"
            break

    if not chunks or not speech_started:
        return None
    total_seconds = sum(len(chunk) for chunk in chunks) / 2 / sample_rate
    if total_seconds < COMMAND_MIN_SECONDS:
        return None
    voice_seconds = voice_bytes / 2 / sample_rate
    peak = _peak_int16(b"".join(chunks))
    if voice_seconds < COMMAND_MIN_VOICE_SECONDS or peak < COMMAND_MIN_PEAK:
        if _verbose_logging():
            print(
                f"التسجيل ضعيف/صامت، ما راح أرسله. voice={voice_seconds:.2f}s peak={peak}"
            )
        return None
    if _verbose_logging():
        print(f"انتهى التسجيل ({stop_reason})، أرسل الأمر للذكاء...")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(chunks))
    return buffer.getvalue()


def _record_fixed_command_wav(
    *,
    audio_queue: queue.Queue[bytes],
    sample_rate: int,
) -> bytes | None:
    if _verbose_logging():
        print(
            f"تكلم الآن. بسجل على الأقل {COMMAND_RECORD_SECONDS:.0f} ثواني، "
            "وبوقف بعد ما تسكت."
        )
    started_at = time.monotonic()
    chunks: list[bytes] = []
    last_voice_at = started_at
    voice_detected = False
    total_bytes = 0
    while True:
        now = time.monotonic()
        elapsed = now - started_at
        if elapsed >= COMMAND_MAX_SECONDS:
            break
        if (
            elapsed >= COMMAND_RECORD_SECONDS
            and voice_detected
            and now - last_voice_at >= COMMAND_END_SILENCE_SECONDS
        ):
            break
        if (
            elapsed >= COMMAND_RECORD_SECONDS + COMMAND_END_SILENCE_SECONDS
            and not voice_detected
        ):
            break
        try:
            data = audio_queue.get(timeout=0.25)
        except queue.Empty:
            continue
        chunks.append(data)
        total_bytes += len(data)
        rms = _rms_int16(data)
        peak = _peak_int16(data)
        if rms >= COMMAND_EXTENSION_RMS_FLOOR or peak >= COMMAND_MIN_PEAK:
            voice_detected = True
            last_voice_at = time.monotonic()

    raw_audio = b"".join(chunks)
    if len(raw_audio) < int(sample_rate * COMMAND_MIN_SECONDS * 2):
        if _verbose_logging():
            print("ما وصلني صوت كفاية.")
        return None
    peak = _peak_int16(raw_audio)
    rms = _rms_int16(raw_audio)
    if peak < COMMAND_MIN_PEAK:
        if _verbose_logging():
            print(f"التسجيل ضعيف/صامت، ما راح أرسله. rms={rms:.1f} peak={peak}")
        return None
    seconds = total_bytes / 2 / sample_rate
    if _verbose_logging():
        print(
            f"انتهى التسجيل بعد {seconds:.1f}s، أرسل الأمر للذكاء... "
            f"rms={rms:.1f} peak={peak}"
        )
    return _raw_pcm_to_wav(raw_audio, sample_rate)


def _raw_pcm_to_wav(raw_audio: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(raw_audio)
    return buffer.getvalue()


def _drain_audio_queue(audio_queue: queue.Queue[bytes]) -> None:
    while True:
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            return


def _rms_int16(data: bytes) -> float:
    if len(data) < 2:
        return 0.0
    samples = memoryview(data[: len(data) - (len(data) % 2)]).cast("h")
    if len(samples) == 0:
        return 0.0
    total = 0
    for sample in samples:
        total += int(sample) * int(sample)
    return (total / len(samples)) ** 0.5


def _peak_int16(data: bytes) -> int:
    if len(data) < 2:
        return 0
    samples = memoryview(data[: len(data) - (len(data) % 2)]).cast("h")
    if len(samples) == 0:
        return 0
    peak = 0
    for sample in samples:
        value = abs(int(sample))
        if value > peak:
            peak = value
    return peak


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _play_audio_data_url(data_url: str, output_device: int | None = None) -> None:
    if ";base64," not in data_url:
        return
    header, encoded = data_url.split(";base64,", 1)
    suffix = ".wav" if "audio/wav" in header else ".audio"
    audio = base64.b64decode(encoded)
    if suffix == ".wav":
        try:
            _play_wav_bytes(audio, output_device)
            return
        except Exception as exc:
            if _verbose_logging():
                print(f"Sounddevice playback failed, trying Windows fallback: {exc}")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as file:
        path = file.name
        file.write(audio)
    if suffix == ".wav":
        winsound.PlaySound(path, winsound.SND_FILENAME)
    else:
        _beep()


def _speak_text(settings: RobotSettings, text: str) -> None:
    text = _sanitize_voice_text(text.strip())
    if not text:
        return
    if _verbose_logging():
        print(f"RAFEEQ says: {text}")
    api_key = getattr(settings, "openai_api_key", "") or ""
    if not api_key:
        _beep(frequency=520, duration_ms=140)
        return
    payload = {
        "model": settings.openai_tts_model,
        "voice": settings.openai_tts_voice,
        "input": text,
        "response_format": "wav",
        "instructions": (
            "Speak Arabic clearly in calm neutral Saudi Arabic. "
            "Use a respectful, patient tone for an older adult. "
            "Keep sentences short and natural. Do not sound childish or robotic. "
            "Do not use overly intimate phrases such as حبيبي, حبيبتي, يا قلبي, "
            "يا بعدي, يا الغالي, يا عم, or يا خالة."
        ),
    }
    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            _play_wav_bytes(response.content, settings.audio_output_device)
    except Exception as exc:
        if _verbose_logging():
            print(f"OpenAI speech failed: {exc}")
        _beep(frequency=520, duration_ms=140)


def _sanitize_voice_text(text: str) -> str:
    banned = (
        "حبيبي",
        "حبيبتي",
        "يا قلبي",
        "يا بعدي",
        "يا الغالي",
        "يا عم",
        "يا خالة",
        "طال عمرك",
        "وشلونك",
        "علومك",
    )
    cleaned = text
    for phrase in banned:
        cleaned = cleaned.replace(phrase, "")
    return " ".join(cleaned.split()).strip()


def _test_mic(settings: RobotSettings) -> None:
    try:
        print(f"Testing mic device: {settings.vosk_input_device}")
        print("تكلم الآن لمدة 3 ثواني...")
        audio = sd.rec(
            int(3 * settings.vosk_sample_rate),
            samplerate=settings.vosk_sample_rate,
            channels=1,
            dtype="int16",
            device=settings.vosk_input_device,
        )
        sd.wait()
        raw = audio.tobytes()
        rms = _rms_int16(raw)
        peak = _peak_int16(raw)
        print(f"Mic RMS: {rms:.1f}")
        print(f"Mic peak: {peak}")
        if peak < COMMAND_MIN_PEAK:
            print(
                "المايك ضعيف جداً أو الجهاز غلط. جرّب تغير VOSK_INPUT_DEVICE في .env.robot."
            )
        else:
            print("المايك يلقط صوتك.")
    except Exception as exc:
        print(f"Microphone test failed: {exc}")


def _play_wav_bytes(audio: bytes, output_device: int | None = None) -> None:
    with wave.open(io.BytesIO(audio), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())
    if sample_width != 2:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")
    samples = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels)
    sd.play(samples, samplerate=sample_rate, device=output_device)
    sd.wait()


def _extract_text(raw_json: str, *, key: str = "text") -> str:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return ""
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _has_wake_word(text: str) -> bool:
    normalized = _normalize(text)
    if any(_normalize(pattern) in normalized for pattern in WAKE_PATTERNS):
        return True
    compact = normalized.replace(" ", "")
    return any(
        pattern in compact
        for pattern in (
            "يارفيق",
            "يارفيج",
            "ياارفيق",
            "رفيق",
            "رفيج",
        )
    )


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[أإآ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[\u064B-\u065F]", "", text)
    return re.sub(r"\s+", " ", text)


def _beep(frequency: int = 740, duration_ms: int = 130) -> None:
    try:
        winsound.Beep(frequency, duration_ms)
    except RuntimeError:
        pass


if __name__ == "__main__":
    main()
