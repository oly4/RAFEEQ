from __future__ import annotations

import json
import queue
from pathlib import Path

from rafeeq_robot.hardware.interfaces import VoiceInputAdapter


class VoskVoiceInput(VoiceInputAdapter):
    def __init__(
        self,
        model_path: str,
        sample_rate: int = 16000,
        input_device: int | None = None,
    ) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model
        except ImportError as exc:  # pragma: no cover - depends on optional local setup
            raise RuntimeError(
                "Install voice dependencies with: "
                "edge\\robot\\.venv\\Scripts\\python.exe -m pip install vosk sounddevice"
            ) from exc

        if not Path(model_path).exists():
            raise FileNotFoundError(f"Vosk model path not found: {model_path}")
        self._sd = sd
        self._recognizer = KaldiRecognizer(Model(model_path), sample_rate)
        self._sample_rate = sample_rate
        self._input_device = input_device

    @property
    def description(self) -> str:
        if self._input_device is None:
            device = "default"
        else:
            device_info = self._sd.query_devices(self._input_device)
            device = f"{self._input_device}: {device_info['name']}"
        return f"VoskVoiceInput(device={device}, sample_rate={self._sample_rate})"

    def listen_text(self, timeout_seconds: int = 8) -> str | None:
        audio_queue: queue.Queue[bytes] = queue.Queue()

        def callback(indata: object, frames: int, time: object, status: object) -> None:
            del frames, time
            if status:
                print(status)
            audio_queue.put(bytes(indata))

        chunks = max(1, int(timeout_seconds * self._sample_rate / 4000))
        with self._sd.RawInputStream(
            samplerate=self._sample_rate,
            blocksize=4000,
            dtype="int16",
            channels=1,
            device=self._input_device,
            callback=callback,
        ):
            for _ in range(chunks):
                data = audio_queue.get(timeout=timeout_seconds + 1)
                if self._recognizer.AcceptWaveform(data):
                    result = json.loads(self._recognizer.Result())
                    text = result.get("text", "").strip()
                    if text:
                        return text
        final = json.loads(self._recognizer.FinalResult())
        text = final.get("text", "").strip()
        return text or None
