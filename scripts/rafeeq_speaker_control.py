#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any


def main() -> int:
    action = sys.argv[1].strip().lower() if len(sys.argv) > 1 else "status"
    if action == "status":
        _print_status("Speaker volume loaded.")
        return 0
    if action == "set":
        payload = _read_payload()
        volume = _bounded_volume(payload.get("volume_percent"))
        _set_volume(volume)
        _print_status("Speaker volume updated.")
        return 0
    if action == "test":
        _speak_test()
        _print_status("Speaker test played.")
        return 0
    print("Usage: rafeeq_speaker_control.py status|set|test", file=sys.stderr)
    return 2


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON payload: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _bounded_volume(value: Any) -> int:
    try:
        volume = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise SystemExit("volume_percent must be a number") from exc
    return max(0, min(100, volume))


def _set_volume(volume: int) -> None:
    if _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{volume / 100:.2f}"]):
        return
    for mixer in _mixer_candidates():
        if _run(["amixer", "set", mixer, f"{volume}%"]):
            return
    raise SystemExit("Could not set speaker volume with wpctl or amixer")


def _current_volume() -> tuple[int | None, bool]:
    wpctl = _capture(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    if wpctl:
        match = re.search(r"Volume:\s*([0-9.]+)", wpctl)
        if match:
            muted = "[MUTED]" in wpctl.upper()
            return round(float(match.group(1)) * 100), muted
    amixer = _capture(["amixer", "get", "Master"])
    if not amixer:
        for mixer in _mixer_candidates():
            amixer = _capture(["amixer", "get", mixer])
            if amixer:
                break
    if amixer:
        percentages = [int(item) for item in re.findall(r"\[(\d{1,3})%\]", amixer)]
        muted = "[off]" in amixer.lower()
        if percentages:
            return max(0, min(100, percentages[-1])), muted
    return None, False


def _mixer_candidates() -> list[str]:
    controls = _capture(["amixer", "scontrols"])
    names = re.findall(r"Simple mixer control '([^']+)'", controls)
    preferred = ["Master", "Speaker", "PCM"]
    ordered = [name for name in preferred if name in names]
    ordered.extend(name for name in names if name not in ordered)
    return ordered or preferred


def _speak_test() -> None:
    text = "RAFEEQ speaker volume test."
    if _run(["espeak", "-v", "en", text]):
        return
    _run(["speaker-test", "-t", "sine", "-f", "880", "-l", "1"])


def _print_status(message: str) -> None:
    volume, muted = _current_volume()
    print(
        json.dumps(
            {
                "enabled": True,
                "volume_percent": volume,
                "muted": muted,
                "message": message,
            },
            ensure_ascii=False,
        )
    )


def _run(command: list[str]) -> bool:
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _capture(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
