from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import httpx
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
ROBOT_SRC = ROOT / "edge" / "robot" / "src"
sys.path.insert(0, str(ROBOT_SRC))

from rafeeq_robot.config import RobotSettings  # noqa: E402
from rafeeq_robot.persistence.database import RobotDatabase  # noqa: E402
from rafeeq_robot.persistence.models import LocalOccurrence, LocalRoutine  # noqa: E402
from rafeeq_robot.transport.http_client import create_device_client  # noqa: E402
from rafeeq_robot.application.sync_service import SyncService  # noqa: E402


SYSTEM_PROMPT = """
You are Rafeeq, a warm AI companion for an elderly-care prototype.
You are talking in a terminal test, not through the old robot voice pipeline.

Understand messy Arabic/English user wording. Be natural and helpful, not robotic.
Use the synced RAFEEQ task data below as truth. If a task is pending, say it has not
been recorded as done. If a task is completed, say it is done. If the user asks about
eating, infer meal/lunch/dinner when present. If the user asks about medicine, infer
medication tasks when present. Do not invent completion. Do not give diagnosis,
dosage advice, or medical recommendations.

Answer in the user's language when clear; otherwise answer in clear neutral Saudi
Arabic. Use a calm, respectful, patient tone suitable for older adults, with neutral
wording that works for any patient gender. Keep it short and natural. Prefer phrases
like "أبشر", "حاضر", "تم", "الله يعافيك", and "خذ راحتك". Do not overdo slang.
Avoid overly intimate or childish words such as حبيبي, حبيبتي, يا قلبي, يا بعدي,
يا الغالي, يا عم, or يا خالة. Avoid formal Standard Arabic unless the user uses it.
""".strip()


def main() -> None:
    settings = RobotSettings()
    if not settings.openai_api_key:
        raise SystemExit(
            "OPENAI_API_KEY is missing in .env.robot. Add it first, then run again."
        )
    model = _text_model(settings)
    database = RobotDatabase(settings.local_database_path)
    print(f"RAFEEQ clean GPT terminal test. Model={model}")
    print("Commands: sync, tasks, quit")
    print("Type naturally, for example: did I eat already?")
    while True:
        try:
            user_text = input("you> ").strip()
        except EOFError:
            return
        if not user_text:
            continue
        if user_text in {"quit", "exit"}:
            return
        if user_text == "sync":
            _sync(settings, database)
            continue
        if user_text == "tasks":
            print(json.dumps(_task_context(database), ensure_ascii=False, indent=2))
            continue
        try:
            answer = ask_gpt(
                settings.openai_api_key, model, user_text, _task_context(database)
            )
        except Exception as exc:
            print(f"OpenAI request failed: {exc}")
            continue
        print(f"rafeeq> {answer}")


def _text_model(settings: RobotSettings) -> str:
    # Keep this separate from the realtime voice model. It lets us test GPT reasoning
    # cleanly in the terminal without Vosk, Piper, or the old command router.
    return getattr(settings, "openai_text_model", "") or "gpt-5.6-terra"


def _sync(settings: RobotSettings, database: RobotDatabase) -> None:
    if not settings.rafeeq_device_secret:
        print("No RAFEEQ_DEVICE_SECRET configured; cannot sync backend tasks.")
        return
    client = create_device_client(
        settings.backend_base_url,
        settings.rafeeq_device_id,
        settings.rafeeq_device_secret,
    )
    try:
        version = SyncService(database, client).synchronize()
    finally:
        client.close()
    print(f"Synced RAFEEQ tasks. configuration_version={version}")


def _task_context(database: RobotDatabase) -> list[dict[str, Any]]:
    with database.session() as session:
        occurrences = list(
            session.scalars(
                select(LocalOccurrence).order_by(LocalOccurrence.scheduled_at_utc)
            ).all()
        )
        tasks: list[dict[str, Any]] = []
        for occurrence in occurrences:
            routine = session.get(LocalRoutine, occurrence.routine_id)
            if routine is None:
                continue
            tasks.append(
                {
                    "title": routine.title,
                    "type": routine.type,
                    "status": occurrence.status,
                    "scheduled_at_utc": occurrence.scheduled_at_utc.isoformat(),
                    "medication": routine.payload_json.get("medication"),
                }
            )
        return tasks


def ask_gpt(
    api_key: str,
    model: str,
    user_text: str,
    tasks: list[dict[str, Any]],
) -> str:
    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "instructions": SYSTEM_PROMPT,
            "input": (
                "Synced RAFEEQ tasks JSON:\n"
                f"{json.dumps(tasks, ensure_ascii=False)}\n\n"
                f"User: {user_text}"
            ),
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
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
    return "".join(parts).strip() or "<empty response>"


if __name__ == "__main__":
    main()
