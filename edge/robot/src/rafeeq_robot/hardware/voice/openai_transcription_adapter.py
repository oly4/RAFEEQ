from __future__ import annotations

import io
from typing import Any
import wave

from rafeeq_robot.hardware.interfaces import VoiceInputAdapter


class OpenAITranscriptionVoiceInput(VoiceInputAdapter):
    """Microphone adapter that records locally and transcribes only non-silent audio."""

    def __init__(
        self,
        api_key: str,
        model: str,
        sample_rate: int = 16000,
        input_device: int | str | None = None,
        silence_threshold: int = 24,
    ) -> None:
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI transcription.")
        try:
            import httpx
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - depends on Pi audio setup
            raise RuntimeError("Install voice dependencies: httpx numpy sounddevice") from exc

        self._httpx = httpx
        self._np = np
        self._sd = sd
        self._api_key = api_key
        self._model = model
        self._sample_rate = sample_rate
        self._input_device = input_device
        self._silence_threshold = silence_threshold

    @property
    def description(self) -> str:
        if self._input_device is None:
            device = "default"
        else:
            try:
                device_info: dict[str, Any] = self._sd.query_devices(self._input_device)
                device = f"{self._input_device}: {device_info['name']}"
            except Exception:
                device = str(self._input_device)
        return (
            "OpenAITranscriptionVoiceInput"
            f"(device={device}, sample_rate={self._sample_rate}, model={self._model})"
        )

    def listen_text(self, timeout_seconds: int = 15) -> str | None:
        wav_bytes = self._record_wav(timeout_seconds)
        if not wav_bytes:
            return None
        response = self._httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            data={"model": self._model, "response_format": "json"},
            files={"file": ("rafeeq-microphone.wav", wav_bytes, "audio/wav")},
            timeout=max(30, timeout_seconds + 30),
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("text")
        return text.strip() if isinstance(text, str) and text.strip() else None

    def _record_wav(self, seconds: int) -> bytes:
        try:
            audio = self._sd.rec(
                int(seconds * self._sample_rate),
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                device=self._input_device,
            )
            self._sd.wait()
        finally:
            self._sd.stop()
        if float(self._np.max(self._np.abs(audio))) < self._silence_threshold:
            return b""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._sample_rate)
            wav_file.writeframes(audio.tobytes())
        return buffer.getvalue()
