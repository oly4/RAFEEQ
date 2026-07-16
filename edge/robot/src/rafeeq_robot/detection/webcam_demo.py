from __future__ import annotations

import argparse
import hmac
import io
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import Any
import wave

from rafeeq_robot.application.emergency_manager import EmergencyManager
from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.config import RobotSettings
from rafeeq_robot.detection.pose_detector import MediaPipePoseFallDetector
from rafeeq_robot.detection.trained_detector import (
    FALL_MODEL_SHA256,
    FALL_MODEL_URL,
    MediaPipeTrainedFallDetector,
    file_sha256,
)
from rafeeq_robot.persistence.database import RobotDatabase
from rafeeq_robot.transport.http_client import create_device_client

POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)
POSE_MODEL_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"
Detector = MediaPipePoseFallDetector | MediaPipeTrainedFallDetector
CONNECTIONS = (
    (11, 12),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (24, 26),
    (25, 27),
    (26, 28),
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _safe_print(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(message.encode("utf-8", errors="replace").decode("utf-8"), flush=True)


class LaptopAlertSpeaker:
    """Console and non-blocking audible feedback for the laptop demo."""

    def speak(self, text: str, locale: str = "en") -> None:
        _safe_print(f"[{locale}] {text}")
        if sys.platform == "win32":
            threading.Thread(target=self._windows_alert, daemon=True).start()

    @staticmethod
    def _windows_alert() -> None:
        import winsound

        for frequency in (880, 1175, 880):
            winsound.Beep(frequency, 180)
            time.sleep(0.08)


class SilentSpeaker:
    def speak(self, text: str, locale: str = "ar") -> None:
        _safe_print(f"[{locale}] {text}")


class OpenAIFallSpeaker:
    """OpenAI TTS playback with a local beep fallback for fall verification."""

    def __init__(self, settings: RobotSettings, fallback: LaptopAlertSpeaker) -> None:
        self.settings = settings
        self.fallback = fallback

    def speak(self, text: str, locale: str = "ar") -> None:
        _safe_print(f"[{locale}] {text}")
        if not self.settings.openai_api_key:
            self.fallback.speak(text, locale)
            return
        self._speak_now(text)

    def _speak_now(self, text: str) -> None:
        try:
            import httpx

            response = httpx.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.settings.openai_tts_model,
                    "voice": self.settings.openai_tts_voice,
                    "input": text,
                    "response_format": "wav",
                },
                timeout=30,
            )
            response.raise_for_status()
            _play_wav(response.content, self.settings.audio_output_device)
        except Exception as exc:
            _safe_print(f"OpenAI fall voice failed; using beep fallback: {exc}")
            self.fallback._windows_alert()


def main() -> None:
    parser = argparse.ArgumentParser(description="RAFEEQ laptop-camera fall detector demo")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--detector", choices=("trained", "heuristic"), default="heuristic")
    parser.add_argument(
        "--pose-model",
        "--model",
        dest="pose_model",
        default=".run/models/pose_landmarker_lite.task",
        type=Path,
    )
    parser.add_argument(
        "--fall-model",
        default=".run/models/fall_detector_window.pkl",
        type=Path,
    )
    parser.add_argument("--database", default=".run/laptop-fall-demo.db")
    parser.add_argument("--verification-timeout", type=int, default=10)
    parser.add_argument("--cooldown", type=int, default=15)
    parser.add_argument("--heuristic-confirmation-frames", type=int, default=1)
    parser.add_argument(
        "--analysis-width",
        type=int,
        default=384,
        help="Resize frames to this width for pose inference. Lower is faster.",
    )
    parser.add_argument(
        "--speaker",
        choices=("openai", "beep"),
        default="openai",
        help="Use OpenAI TTS for fall prompts, or local beep/console fallback.",
    )
    parser.add_argument(
        "--voice-verification",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Listen once during fall verification and classify safe/help/timeout.",
    )
    parser.add_argument(
        "--voice-check-only",
        action="store_true",
        help="Test the fall voice prompt/listener once without opening the camera.",
    )
    args = parser.parse_args()
    if args.voice_check_only:
        settings = RobotSettings()
        speaker = (
            OpenAIFallSpeaker(settings, LaptopAlertSpeaker())
            if args.speaker == "openai"
            else LaptopAlertSpeaker()
        )
        speaker.speak(
            "انتبهت إنك ممكن طحت. طمني، أنت بخير؟ قل أنا بخير أو ساعدني.",
            "ar",
        )
        outcome = _listen_for_fall_response(settings, args.verification_timeout)
        _safe_print(f"Voice check outcome: {outcome}")
        return

    _ensure_artifact(
        args.pose_model,
        POSE_MODEL_URL,
        POSE_MODEL_SHA256,
        "MediaPipe pose model",
    )
    if args.detector == "trained":
        _ensure_artifact(
            args.fall_model,
            FALL_MODEL_URL,
            FALL_MODEL_SHA256,
            "trained fall classifier",
        )
    _run(args)


def _ensure_artifact(path: Path, url: str, expected_sha256: str, label: str) -> None:
    if path.is_file():
        actual = file_sha256(path)
        if not hmac.compare_digest(actual.lower(), expected_sha256.lower()):
            raise RuntimeError(
                f"Refusing to load {label}: checksum mismatch for {path}. "
                "Delete the file and restart to download the pinned artifact."
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.download")
    print(f"Downloading {label} (one time)...")
    try:
        urllib.request.urlretrieve(url, temporary)  # noqa: S310 - pinned HTTPS + SHA-256
        actual = file_sha256(temporary)
        if not hmac.compare_digest(actual.lower(), expected_sha256.lower()):
            raise RuntimeError(
                f"Downloaded {label} failed checksum verification: expected "
                f"{expected_sha256}, got {actual}"
            )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _run(args: argparse.Namespace) -> None:
    import cv2  # type: ignore[import-not-found]

    capture = _open_camera(cv2, args.camera_index)
    if not capture.isOpened():
        raise RuntimeError(
            f"Camera {args.camera_index} could not be opened. Close other camera apps or try "
            "--camera-index 1."
        )
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    capture.set(cv2.CAP_PROP_FPS, 30)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    detector: Detector
    if args.detector == "trained":
        detector = MediaPipeTrainedFallDetector(args.pose_model, args.fall_model)
    else:
        detector = MediaPipePoseFallDetector(
            args.pose_model,
            confirmation_frames=max(1, args.heuristic_confirmation_frames),
        )
    settings = RobotSettings()
    speaker = (
        OpenAIFallSpeaker(settings, LaptopAlertSpeaker())
        if args.speaker == "openai"
        else LaptopAlertSpeaker()
    )
    client = (
        create_device_client(
            settings.backend_base_url,
            settings.rafeeq_device_id,
            settings.rafeeq_device_secret,
        )
        if settings.rafeeq_device_secret
        else None
    )
    database = RobotDatabase(args.database)
    outbox = OutboxService(
        database,
        settings.rafeeq_device_id,
        settings.rafeeq_patient_id,
        client,
    )
    emergencies = EmergencyManager(
        outbox,
        SilentSpeaker() if args.voice_verification else speaker,
        locale="ar",
    )
    verification_deadline = 0.0
    voice_verification = {"active": False, "deadline": 0.0, "listening": False}
    cooldown_until = 0.0
    next_publish_at = 0.0
    outcome_message = ""
    print(
        f"Camera preview started with the {args.detector} detector. "
        "Voice verification is hands-free; keys are backup only."
    )
    print(
        "Backend synchronization enabled."
        if client is not None
        else "Offline mode: set RAFEEQ device credentials to synchronize verified alerts."
    )

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("The camera stopped returning frames.")
            now = datetime.now(timezone.utc)
            analysis_frame = _resize_for_analysis(cv2, frame, args.analysis_width)
            detection = detector.analyze(analysis_frame, now)
            monotonic_now = time.monotonic()
            if (
                detection.is_possible_fall
                and emergencies.active_fall_event_id is None
                and monotonic_now >= cooldown_until
            ):
                event_id = emergencies.trigger_possible_fall(
                    detection.confidence, detection.reason_codes
                )
                verification_deadline = (
                    0.0 if args.voice_verification else monotonic_now + args.verification_timeout
                )
                cooldown_until = monotonic_now + args.cooldown
                outcome_message = f"Possible fall {event_id[:8]}: verification required"
                print(outcome_message)
                outbox.publish_pending()
                if args.voice_verification:
                    _start_fall_voice_listener(
                        settings,
                        args.verification_timeout,
                        emergencies,
                        outbox,
                        speaker,
                        voice_verification,
                    )

            if (
                emergencies.active_fall_event_id is not None
                and not voice_verification["active"]
                and not args.voice_verification
                and monotonic_now >= verification_deadline
            ):
                emergencies.finish_fall_verification("timeout")
                outcome_message = "NO RESPONSE: escalation event stored locally"
                print(outcome_message)
                outbox.publish_pending()

            active_deadline = float(voice_verification.get("deadline") or verification_deadline)
            _draw_preview(
                cv2,
                frame,
                detector,
                emergencies,
                active_deadline,
                outcome_message,
                bool(voice_verification.get("listening")),
            )
            cv2.imshow("RAFEEQ Laptop Fall Detection", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key in (ord("s"), ord("h"), ord("t")):
                outcome = {ord("s"): "safe", ord("h"): "help", ord("t"): "timeout"}[key]
                if emergencies.active_fall_event_id is not None:
                    voice_verification["active"] = False
                    emergencies.finish_fall_verification(outcome)
                    outcome_message = f"Verification recorded: {outcome.upper()}"
                    print(outcome_message)
                    outbox.publish_pending()
            if key == ord("f") and emergencies.active_fall_event_id is None:
                emergencies.trigger_possible_fall(0.82, ["manual_demo_trigger"])
                verification_deadline = (
                    0.0 if args.voice_verification else monotonic_now + args.verification_timeout
                )
                cooldown_until = monotonic_now + args.cooldown
                outcome_message = "Manual verification-path test started"
                outbox.publish_pending()
                if args.voice_verification:
                    _start_fall_voice_listener(
                        settings,
                        args.verification_timeout,
                        emergencies,
                        outbox,
                        speaker,
                        voice_verification,
                    )
            if client is not None and monotonic_now >= next_publish_at:
                outbox.publish_pending()
                next_publish_at = monotonic_now + 5
    finally:
        detector.close()
        capture.release()
        cv2.destroyAllWindows()
        if client is not None:
            client.close()


def _open_camera(cv2: Any, index: int) -> Any:
    if sys.platform == "win32":
        capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if capture.isOpened():
            return capture
        capture.release()
    return cv2.VideoCapture(index)


def _resize_for_analysis(cv2: Any, frame: Any, target_width: int) -> Any:
    if target_width <= 0:
        return frame
    height, width = frame.shape[:2]
    if width <= target_width:
        return frame
    target_height = max(1, int(height * (target_width / width)))
    return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)


def _listen_for_fall_response(settings: RobotSettings, seconds: int) -> str | None:
    if not settings.openai_api_key:
        print("OpenAI key missing; use S=safe, H=help, or wait for timeout.")
        return None
    try:
        wav_bytes = _record_wav(
            seconds=seconds,
            sample_rate=settings.vosk_sample_rate,
            input_device=settings.vosk_input_device,
        )
        transcript = _transcribe_fall_response(settings, wav_bytes)
    except Exception as exc:
        print(f"Fall voice verification failed; keyboard/timeout remains active: {exc}")
        return None

    print(f"Fall verification transcript: {transcript or '<empty>'}")
    if not transcript:
        return "timeout"
    return _classify_fall_response(transcript)


def _start_fall_voice_listener(
    settings: RobotSettings,
    seconds: int,
    emergencies: EmergencyManager,
    outbox: OutboxService,
    speaker: OpenAIFallSpeaker | LaptopAlertSpeaker,
    state: dict[str, bool | float],
) -> None:
    if state["active"]:
        return
    state["active"] = True
    state["deadline"] = 0.0
    state["listening"] = False

    def worker() -> None:
        try:
            speaker.speak(
                "انتبهت إنك ممكن طحت. طمني، أنت بخير؟ قل أنا بخير أو ساعدني.",
                "ar",
            )
            state["deadline"] = time.monotonic() + seconds
            state["listening"] = True
            outcome = _listen_for_fall_response(settings, seconds)
            state["listening"] = False
            if outcome is None:
                outcome = "timeout"
            if emergencies.active_fall_event_id is not None and outcome is not None:
                emergencies.finish_fall_verification(outcome)
                print(f"Voice verification recorded: {outcome.upper()}")
                if outcome == "safe":
                    speaker.speak("الحمد لله. ما راح أرسل تنبيه طارئ.", "ar")
                else:
                    speaker.speak("ما وصلني رد واضح، أرسلت تنبيه طارئ لأهلك.", "ar")
                outbox.publish_pending()
        finally:
            state["active"] = False
            state["deadline"] = 0.0
            state["listening"] = False

    threading.Thread(target=worker, daemon=True).start()


def _record_wav(seconds: int, sample_rate: int, input_device: int | None) -> bytes:
    import numpy as np
    import sounddevice as sd

    print(f"Listening for fall response for {seconds} seconds...")
    audio = sd.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=input_device,
    )
    sd.wait()
    if float(np.max(np.abs(audio))) < 8:
        return b""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())
    return buffer.getvalue()


def _transcribe_fall_response(settings: RobotSettings, wav_bytes: bytes) -> str:
    if not wav_bytes:
        return ""
    import httpx

    response = httpx.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        data={
            "model": settings.openai_transcription_model,
            "response_format": "json",
        },
        files={"file": ("fall-response.wav", wav_bytes, "audio/wav")},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    text = data.get("text")
    return text.strip() if isinstance(text, str) else ""


def _classify_fall_response(transcript: str) -> str:
    normalized = transcript.casefold()
    negated_help_safe_words = (
        "ما احتاج",
        "ما أحتاج",
        "لا احتاج",
        "لا أحتاج",
        "ما ابي مساعدة",
        "ما أبي مساعدة",
        "لا ترسل",
        "لا تتصل",
    )
    if any(word in normalized for word in negated_help_safe_words):
        return "safe"
    help_words = (
        "help",
        "emergency",
        "not okay",
        "hurt",
        "pain",
        "مساعدة",
        "ساعد",
        "الحق",
        "مو بخير",
        "ماني بخير",
        "تعبان",
        "تعبانه",
        "اتصل",
    )
    safe_words = (
        "safe",
        "okay",
        "ok",
        "fine",
        "i am good",
        "i'm good",
        "بخير",
        "تمام",
        "كويس",
        "كويسة",
        "ما احتاج",
        "لا ترسل",
    )
    if any(word in normalized for word in help_words):
        return "help"
    if any(word in normalized for word in safe_words):
        return "safe"
    return "timeout"


def _play_wav(wav_bytes: bytes, output_device: int | None) -> None:
    try:
        import numpy as np
        import sounddevice as sd

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
        return
    except Exception:
        if sys.platform != "win32":
            raise
    import winsound

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
        audio_path = audio_file.name
        audio_file.write(wav_bytes)
    try:
        winsound.PlaySound(audio_path, winsound.SND_FILENAME)
    finally:
        Path(audio_path).unlink(missing_ok=True)


def _draw_preview(
    cv2: Any,
    frame: Any,
    detector: Detector,
    emergencies: EmergencyManager,
    verification_deadline: float,
    outcome_message: str,
    listening: bool = False,
) -> None:
    height, width = frame.shape[:2]
    if emergencies.active_fall_event_id is not None:
        alert_overlay = frame.copy()
        cv2.rectangle(alert_overlay, (0, 0), (width, height), (0, 0, 210), -1)
        cv2.addWeighted(alert_overlay, 0.25, frame, 0.75, 0, frame)
        cv2.rectangle(frame, (4, 4), (width - 5, height - 5), (0, 0, 255), 9)
    for start, end in CONNECTIONS:
        if len(detector.last_landmarks) <= end:
            continue
        first = detector.last_landmarks[start]
        second = detector.last_landmarks[end]
        if min(first.visibility or 0, second.visibility or 0) < 0.35:
            continue
        cv2.line(
            frame,
            (int(first.x * width), int(first.y * height)),
            (int(second.x * width), int(second.y * height)),
            (124, 79, 194),
            3,
        )
    for index in (11, 12, 23, 24, 25, 26, 27, 28):
        if len(detector.last_landmarks) <= index:
            continue
        point = detector.last_landmarks[index]
        if (point.visibility or 0) >= 0.35:
            cv2.circle(
                frame,
                (int(point.x * width), int(point.y * height)),
                5,
                (255, 255, 255),
                -1,
            )

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (width, 142), (24, 18, 34), -1)
    cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
    cv2.putText(
        frame,
        "RAFEEQ FALL-DETECTION PROTOTYPE - NOT A MEDICAL DEVICE",
        (18, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (255, 255, 255),
        2,
    )
    status = "NO POSE: move back until shoulders and hips are visible"
    detail = "Keep your full body visible while the detector warms up"
    color = (120, 230, 120)
    if isinstance(detector, MediaPipeTrainedFallDetector):
        trained_metrics = detector.last_metrics
        if trained_metrics is not None:
            status = (
                "ML READY - lower yourself SAFELY sideways onto a sofa/mat"
                if trained_metrics.window_ready
                else "ML WARMING UP - remain fully visible for about 2 seconds"
            )
            detail = (
                f"Model: fall probability={trained_metrics.fall_probability:.2f}  "
                f"angle={trained_metrics.torso_angle_from_vertical:.0f}deg  "
                f"height/width={trained_metrics.body_height_width_ratio:.2f}"
            )
    else:
        heuristic_metrics = detector.last_metrics
        if heuristic_metrics is not None:
            status = (
                "READY - lower yourself SAFELY sideways onto a sofa/mat"
                if heuristic_metrics.recently_upright
                else "NOT ARMED - stand upright and face the camera"
            )
            detail = (
                f"Pose: angle={heuristic_metrics.torso_angle_from_vertical:.0f}deg  "
                f"aspect={heuristic_metrics.body_aspect_ratio:.2f}  "
                f"descent={heuristic_metrics.descent:.2f}  "
                f"candidate={heuristic_metrics.candidate_frames}"
            )
    if emergencies.active_fall_event_id is not None:
        remaining = max(0, int(verification_deadline - time.monotonic()))
        status = (
            f"POSSIBLE FALL - LISTENING ({remaining}s): say ANA BIKHAIR or SAAEDNI"
            if listening and verification_deadline > 0
            else "POSSIBLE FALL - RAFEEQ IS ASKING, ANSWER AFTER THE PROMPT"
        )
        color = (40, 40, 255)
    cv2.putText(frame, status, (18, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.56, color, 2)
    cv2.putText(
        frame,
        detail,
        (18, 94),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        (230, 220, 255),
        2,
    )
    cv2.putText(
        frame,
        "Voice control is primary. Backup: S=safe H=help T=timeout Q=quit",
        (18, 124),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (230, 220, 255),
        2,
    )
    if outcome_message:
        cv2.putText(
            frame,
            outcome_message[:90],
            (18, height - 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            2,
        )


if __name__ == "__main__":
    main()
