from __future__ import annotations

import shutil
import sys
from pathlib import Path


REQUIRED_PATHS = (
    "AGENTS.md",
    "docker-compose.yml",
    "services/backend/pyproject.toml",
    "edge/robot/pyproject.toml",
    "apps/mobile/pubspec.yaml",
    "packages/contracts/schemas/device-event-v1.schema.json",
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing = [path for path in REQUIRED_PATHS if not (root / path).exists()]
    print(f"Python: {sys.version.split()[0]}")
    for command in ("docker", "flutter", "make"):
        print(
            f"{command}: {shutil.which(command) or 'not installed (optional for static verification)'}"
        )
    if missing:
        print("Missing required paths:", *missing, sep="\n- ")
        return 1
    print("RAFEEQ repository structure: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
