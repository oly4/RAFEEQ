#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


PAUSE_FILE = Path("/tmp/rafeeq_voice_paused")


def main() -> int:
    command = _command_from_args()
    if command in {"stop", "pause", "off"}:
        PAUSE_FILE.write_text("paused\n", encoding="utf-8")
        print("RAFEEQ voice command handling stopped.")
        return 0
    if command in {"start", "resume", "on"}:
        PAUSE_FILE.unlink(missing_ok=True)
        print("RAFEEQ voice command handling started.")
        return 0
    if command == "status":
        state = "stopped" if PAUSE_FILE.exists() else "listening"
        print(f"RAFEEQ voice command handling is {state}.")
        return 0
    print("Usage: rafeeq-voice stop|start|status")
    return 2


def _command_from_args() -> str:
    executable = Path(sys.argv[0]).name
    if executable == "stop-hearing":
        return "stop"
    if executable == "start-hearing":
        return "start"
    if executable == "stop" and len(sys.argv) >= 2 and sys.argv[1].lower() == "hearing":
        return "stop"
    if executable == "start" and len(sys.argv) >= 2 and sys.argv[1].lower() == "hearing":
        return "start"
    if len(sys.argv) >= 2:
        return sys.argv[1].strip().lower()
    return "status"


if __name__ == "__main__":
    raise SystemExit(main())
