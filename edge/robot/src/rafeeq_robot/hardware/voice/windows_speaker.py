from __future__ import annotations

import base64
import os
import subprocess

from rafeeq_robot.hardware.interfaces import SpeakerAdapter
from rafeeq_robot.hardware.simulation.adapters import clean_speech_text, format_console_text


class WindowsSpeechSpeaker(SpeakerAdapter):
    def __init__(self, rate: int = 0, volume: int = 100) -> None:
        self.rate = max(-10, min(10, rate))
        self.volume = max(0, min(100, volume))

    def speak(self, text: str, locale: str = "ar") -> None:
        print(f"[{locale}] {format_console_text(text)}")
        encoded = base64.b64encode(clean_speech_text(text).encode("utf-8")).decode("ascii")
        env = os.environ.copy()
        env["RAFEEQ_SPEAK_B64"] = encoded
        env["RAFEEQ_SPEAK_RATE"] = str(self.rate)
        env["RAFEEQ_SPEAK_VOLUME"] = str(self.volume)
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Rate = [int]$env:RAFEEQ_SPEAK_RATE; "
            "$s.Volume = [int]$env:RAFEEQ_SPEAK_VOLUME; "
            "$text = [Text.Encoding]::UTF8.GetString("
            "[Convert]::FromBase64String($env:RAFEEQ_SPEAK_B64)); "
            "$s.Speak($text);"
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            env=env,
            check=False,
        )
