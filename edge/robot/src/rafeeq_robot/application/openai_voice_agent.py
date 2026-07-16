from __future__ import annotations

import json
from typing import Any

from websockets.sync.client import connect

from rafeeq_robot.application.reminder_service import ReminderService, RoutineTaskStatus
from rafeeq_robot.application.voice_interactor import VoiceIntentRouter, VoiceResult
from rafeeq_robot.hardware.interfaces import SpeakerAdapter


class OpenAIRealtimeVoiceAgent:
    """OpenAI reasoning layer over RAFEEQ's local, safety-checked voice tools.

    The microphone/STT and speaker can stay local. This class sends the transcript and
    non-sensitive task status to GPT Realtime, lets the model choose read-only RAFEEQ
    tools, and speaks the final natural answer. If GPT Realtime is unavailable, the
    deterministic command router remains only as a safety fallback for core RAFEEQ
    actions.
    """

    def __init__(
        self,
        fallback: VoiceIntentRouter,
        reminders: ReminderService,
        speaker: SpeakerAdapter,
        api_key: str,
        model: str,
        timeout_seconds: int = 25,
    ) -> None:
        self.fallback = fallback
        self.reminders = reminders
        self.speaker = speaker
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def handle_text(self, transcript: str, source: str = "openai_realtime") -> VoiceResult:
        if not self.api_key:
            print("OpenAI API key is not configured; using safety command router.")
            return self.fallback.handle_text(transcript, source)
        try:
            message = self._ask_openai(transcript)
        except Exception as exc:
            print(f"GPT Realtime unavailable; using safety command router: {exc}")
            return self.fallback.handle_text(transcript, source)
        if not message:
            return self.fallback.handle_text(transcript, source)
        self.speaker.speak(message, "ar")
        self.fallback.outbox.record(
            "voice_command_recognized",
            {
                "intent": "openai_conversation",
                "confidence": 0.8,
                "source": source,
            },
        )
        return VoiceResult("openai_conversation", True, message)

    def _ask_openai(self, transcript: str) -> str:
        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        with connect(
            url,
            additional_headers=headers,
            open_timeout=self.timeout_seconds,
            close_timeout=5,
        ) as ws:
            self._send_session(ws)
            self._send_user_message(ws, transcript)
            return self._collect_response(ws)

    def _send_session(self, ws: Any) -> None:
        ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["text"],
                        "instructions": _SYSTEM_INSTRUCTIONS,
                        "tools": _TOOLS,
                        "tool_choice": "auto",
                    },
                }
            )
        )

    def _send_user_message(self, ws: Any, transcript: str) -> None:
        task_context = [task_status_to_dict(item) for item in self.reminders.list_task_statuses()]
        ws.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    f"User said: {transcript}\n\n"
                                    "Current synced RAFEEQ tasks JSON:\n"
                                    f"{json.dumps(task_context, ensure_ascii=False)}"
                                ),
                            }
                        ],
                    },
                }
            )
        )
        ws.send(json.dumps({"type": "response.create", "response": {"modalities": ["text"]}}))

    def _collect_response(self, ws: Any) -> str:
        response_parts: list[str] = []
        handled_tool_calls = 0
        while True:
            raw = ws.recv(timeout=self.timeout_seconds)
            event = json.loads(raw)
            event_type = str(event.get("type", ""))
            if event_type.endswith(".delta") and isinstance(event.get("delta"), str):
                response_parts.append(str(event["delta"]))
                continue
            if event_type == "response.output_item.done":
                item = event.get("item") or {}
                if isinstance(item, dict) and item.get("type") == "function_call":
                    handled_tool_calls += 1
                    if handled_tool_calls > 4:
                        raise RuntimeError("Too many OpenAI tool calls")
                    self._handle_tool_call(ws, item)
                    continue
                message = _extract_message_text(item)
                if message:
                    response_parts.append(message)
            if event_type in {"response.text.done", "response.output_text.done"}:
                text = event.get("text")
                if isinstance(text, str):
                    response_parts.append(text)
            if event_type == "response.done":
                return "".join(response_parts).strip()
            if event_type == "error":
                error = event.get("error") or {}
                raise RuntimeError(error.get("message") or event)

    def _handle_tool_call(self, ws: Any, item: dict[str, Any]) -> None:
        call_id = str(item.get("call_id") or "")
        name = str(item.get("name") or "")
        try:
            arguments = json.loads(str(item.get("arguments") or "{}"))
        except json.JSONDecodeError:
            arguments = {}
        output = self._run_tool(name, arguments)
        ws.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(output, ensure_ascii=False),
                    },
                }
            )
        )
        ws.send(json.dumps({"type": "response.create", "response": {"modalities": ["text"]}}))

    def _run_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "get_today_tasks":
            return {
                "tasks": [task_status_to_dict(item) for item in self.reminders.list_task_statuses()]
            }
        if name == "get_task_status":
            query = str(arguments.get("query") or "")
            status = self.reminders.find_task_status(query)
            return {"task": task_status_to_dict(status) if status else None}
        if name == "get_medication_status":
            completed_at = self.reminders.latest_completed_medication_at()
            return {
                "completed": completed_at is not None,
                "completed_at_utc": completed_at.isoformat() if completed_at else None,
            }
        return {"error": f"Unknown tool: {name}"}


def task_status_to_dict(status: RoutineTaskStatus | None) -> dict[str, Any] | None:
    if status is None:
        return None
    return {
        "title": status.title,
        "type": status.routine_type,
        "status": status.status,
        "scheduled_at_utc": status.scheduled_at_utc.isoformat(),
    }


def _extract_message_text(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    content = item.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        for key in ("text", "transcript"):
            value = part.get(key)
            if isinstance(value, str):
                parts.append(value)
    return "".join(parts)


_SYSTEM_INSTRUCTIONS = """
You are RAFEEQ, a calm Saudi Najdi/Riyadh-style elderly-care voice assistant.
Understand Arabic and English, but speak the final answer in short, natural Saudi
Najdi/Riyadh Arabic. Be respectful, warm like family, and use neutral wording that
works for any patient gender. Prefer gentle phrases like "أبشر", "تم", "وش تقصد؟",
and "ما لقيت المهمة" without exaggerating slang.
You are not a doctor. Never diagnose, recommend doses, or change medication.
For task, routine, meal, water, activity, or medication status questions, use the
available tools instead of guessing. If records are missing, say that no synced
record is available and ask the caregiver to sync the app.
Do not claim a task or medicine was completed unless the tool output says it is
completed. Keep answers one sentence unless the user asks for details.
""".strip()


_TOOLS = [
    {
        "type": "function",
        "name": "get_today_tasks",
        "description": "Return the synced RAFEEQ tasks and their completion status.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_task_status",
        "description": "Return the best matching synced RAFEEQ task status for a user query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The task, meal, routine, or activity the user asked about.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_medication_status",
        "description": "Return whether the latest synced/local medication reminder was completed.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]
