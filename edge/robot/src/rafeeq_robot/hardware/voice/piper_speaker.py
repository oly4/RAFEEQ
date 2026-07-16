from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4
import winsound

from rafeeq_robot.hardware.interfaces import SpeakerAdapter
from rafeeq_robot.hardware.simulation.adapters import clean_speech_text, format_console_text
from rafeeq_robot.hardware.voice.windows_speaker import WindowsSpeechSpeaker


class PiperSpeaker(SpeakerAdapter):
    def __init__(self, model_path: str, config_path: str, volume: int = 100) -> None:
        self.model_path = Path(model_path)
        self.config_path = Path(config_path)
        self.volume = max(0, min(100, volume))
        self.fallback = WindowsSpeechSpeaker(volume=self.volume)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Piper voice model not found: {self.model_path}")
        if not self.config_path.exists():
            raise FileNotFoundError(f"Piper voice config not found: {self.config_path}")

    def speak(self, text: str, locale: str = "ar") -> None:
        print(f"[{locale}] {format_console_text(text)}")
        speech_text = clean_speech_text(text)
        wav_path = Path(tempfile.gettempdir()) / f"rafeeq-piper-{uuid4()}.wav"
        python_executable = Path(sys.executable)
        piper_command = [str(python_executable), "-m", "piper"]
        piper_executable = Path(sys.prefix) / "Scripts" / "piper.exe"
        if piper_executable.exists():
            piper_command = [str(piper_executable)]
        elif discovered_piper := shutil.which("piper"):
            piper_command = [discovered_piper]
        if not python_executable.name.casefold().startswith("python"):
            venv_python = python_executable.with_name("python.exe")
            if venv_python.exists():
                python_executable = venv_python
            piper_executable = python_executable.with_name("piper.exe")
            if piper_executable.exists():
                piper_command = [str(piper_executable)]
            elif not piper_command[0].endswith("piper.exe"):
                piper_command = [str(python_executable), "-m", "piper"]
        try:
            result = subprocess.run(
                [
                    *piper_command,
                    "-m",
                    str(self.model_path),
                    "-c",
                    str(self.config_path),
                    "-f",
                    str(wav_path),
                    "--volume",
                    str(self.volume / 100),
                ],
                input=speech_text.encode("utf-8"),
                check=False,
                stderr=subprocess.PIPE,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                reason = stderr.splitlines()[-1] if stderr else "unknown Piper error"
                print(f"Piper speech generation failed: {reason}")
                print("Using Windows speech fallback.")
                self.fallback.speak(text, locale)
                return
            if wav_path.exists() and wav_path.stat().st_size > 0:
                winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
        finally:
            wav_path.unlink(missing_ok=True)
