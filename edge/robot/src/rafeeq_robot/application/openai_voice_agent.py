from __future__ import annotations

import json
from typing import Any

import httpx

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
        text_model: str,
        reasoning_effort: str,
        timeout_seconds: int = 25,
    ) -> None:
        self.fallback = fallback
        self.reminders = reminders
        self.speaker = speaker
        self.api_key = api_key
        self.model = model
        self.text_model = text_model
        self.reasoning_effort = reasoning_effort
        self.timeout_seconds = timeout_seconds

    def handle_text(self, transcript: str, source: str = "openai_realtime") -> VoiceResult:
        if not self.api_key:
            print("OpenAI API key is not configured; using safety command router.")
            return self.fallback.handle_text(transcript, source)
        try:
            message = self._ask_openai(transcript)
        except Exception as exc:
            print(f"GPT Realtime unavailable; trying OpenAI text model: {exc}")
            try:
                message = self._ask_openai_text(transcript, source)
            except Exception as text_exc:
                print(f"OpenAI text model unavailable; using safety command router: {text_exc}")
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

    def _ask_openai_text(self, transcript: str, source: str) -> str:
        task_context = [task_status_to_dict(item) for item in self.reminders.list_task_statuses()]
        payload: dict[str, Any] = {
            "model": self.text_model,
            "instructions": _TEXT_PLANNER_INSTRUCTIONS,
            "input": (
                f"User said: {transcript}\n\n"
                "Current synced RAFEEQ tasks JSON:\n"
                f"{json.dumps(task_context, ensure_ascii=False)}"
            ),
            "max_output_tokens": 600,
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("output_text")
        raw_text = text.strip() if isinstance(text, str) else _extract_response_text(data)
        plan = _parse_json_object(raw_text)
        if plan is None:
            return raw_text
        return self._execute_plan(plan, transcript, source)

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
        if name == "complete_task":
            return self._tool_task_result(
                self.reminders.complete_best_match(str(arguments.get("query") or "")),
            )
        if name == "snooze_task":
            minutes = _bounded_minutes(arguments.get("minutes"), 10)
            return self._tool_task_result(
                self.reminders.snooze_best_match(str(arguments.get("query") or ""), minutes),
            )
        if name == "decline_task":
            return self._tool_task_result(
                self.reminders.miss_best_match(str(arguments.get("query") or "")),
            )
        if name == "undo_complete_task":
            return self._tool_task_result(
                self.reminders.undo_best_match_completion(str(arguments.get("query") or "")),
            )
        if name == "request_help":
            if self.fallback.emergencies is None:
                return {"handled": False, "message": "Emergency manager is not available."}
            event_id = self.fallback.emergencies.trigger_sos()
            return {"handled": True, "event_id": event_id}
        if name == "send_app_action":
            action = str(arguments.get("action") or "unknown")
            assistant_text = str(arguments.get("assistant_text") or _default_action_text(action))
            self._record_app_action(action, "", assistant_text)
            return {"handled": True, "action": action}
        return {"error": f"Unknown tool: {name}"}

    def _execute_plan(
        self,
        plan: dict[str, Any],
        transcript: str,
        source: str,
    ) -> str:
        del source
        action = str(plan.get("action") or "answer")
        assistant_text = str(plan.get("assistant_text") or "").strip()
        query = str(plan.get("query") or transcript)
        if action == "answer":
            return assistant_text or "أبشر، وش تحتاج؟"
        if action == "complete_task":
            status = self.reminders.complete_best_match(query)
            if status is None:
                return "ما لقيت المهمة المقصودة. قل اسمها بعد يا رفيق."
            return assistant_text or f"تم، علّمت {status.title} كمنجزة."
        if action == "snooze_task":
            minutes = _bounded_minutes(plan.get("minutes"), 10)
            status = self.reminders.snooze_best_match(query, minutes)
            if status is None:
                return "ما لقيت المهمة المقصودة عشان أؤجلها."
            return assistant_text or f"تم، بأذكرك في {status.title} بعد {minutes} دقائق."
        if action == "decline_task":
            status = self.reminders.miss_best_match(query)
            if status is None:
                return "ما لقيت المهمة المقصودة عشان أسجلها كغير منجزة."
            return assistant_text or f"تم، سجلت أن {status.title} لم تكتمل الآن."
        if action == "undo_complete_task":
            status = self.reminders.undo_best_match_completion(query)
            if status is None:
                return "ما لقيت مهمة مكتملة أشيل منها علامة تم."
            return assistant_text or f"تم، شلت علامة الإنجاز من {status.title}."
        if action == "request_help":
            if self.fallback.emergencies is None:
                return "خدمة الطوارئ غير جاهزة الآن."
            self.fallback.emergencies.trigger_sos()
            return assistant_text or "تم طلب المساعدة. ابق هادئاً، سيتم تنبيه العائلة."
        if action in {
            "open_album",
            "open_activities",
            "start_poem_test",
            "start_photo_test",
            "open_routine",
            "open_dashboard",
            "open_settings",
            "add_routine",
            "edit_routine",
            "delete_routine",
            "complete_routine",
            "undo_complete_routine",
        }:
            message = assistant_text or _default_action_text(action)
            self._record_app_action(action, transcript, message)
            return message
        if action in {"start_activity", "request_add_task", "request_edit_task", "request_delete_task"}:
            mapped_action = {
                "start_activity": "open_activities",
                "request_add_task": "add_routine",
                "request_edit_task": "edit_routine",
                "request_delete_task": "delete_routine",
            }[action]
            message = _default_action_text(mapped_action)
            if action == "request_add_task":
                routine = plan.get("routine")
                if isinstance(routine, dict) and routine.get("title") and routine.get("time_24h"):
                    self._record_routine_create(transcript, message, routine)
                    return message
            self._record_app_action(mapped_action, transcript, message)
            return message
        return assistant_text or "ما فهمت الطلب كامل. قل يا رفيق ثم الأمر بهدوء."

    def _record_app_action(self, action: str, transcript: str, assistant_text: str) -> None:
        self.fallback.outbox.record(
            "voice_app_action",
            {
                "action": action,
                "transcript": transcript,
                "assistant_text": assistant_text,
                "used_openai": True,
            },
        )

    def _record_routine_create(
        self,
        transcript: str,
        assistant_text: str,
        routine: dict[str, Any],
    ) -> None:
        self.fallback.outbox.record(
            "voice_routine_create",
            {
                "transcript": transcript,
                "assistant_text": assistant_text,
                "routine": routine,
                "used_openai": True,
            },
        )

    @staticmethod
    def _tool_task_result(status: RoutineTaskStatus | None) -> dict[str, Any]:
        if status is None:
            return {"handled": False, "task": None}
        return {"handled": True, "task": task_status_to_dict(status)}


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


def _extract_response_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    output = data.get("output")
    if not isinstance(output, list):
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts).strip()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _bounded_minutes(value: Any, default: int) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        minutes = default
    return max(1, min(120, minutes))


def _default_action_text(action: str) -> str:
    return {
        "open_dashboard": "تم، فتحت لك الصفحة الرئيسية.",
        "open_routine": "تم، فتحت لك الروتين.",
        "open_activities": "تم، فتحت لك الأنشطة.",
        "open_album": "تم، فتحت لك الألبوم.",
        "open_settings": "تم، فتحت لك الإعدادات.",
        "start_poem_test": "أبشر، نبدأ تمرين القصيدة بهدوء.",
        "start_photo_test": "تم، نبدأ تمرين الصور.",
        "add_routine": "تم، أضفت المهمة.",
        "edit_routine": "تم، فتحت لك تعديل الروتين.",
        "delete_routine": "تم، فتحت لك حذف المهمة.",
        "complete_routine": "تم، حدثت حالة المهمة.",
        "undo_complete_routine": "تم، حدثت حالة المهمة.",
    }.get(action, "تم.")


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
You may mark a synced task done, snoozed, missed, or request emergency help only
when the patient clearly asks. You may trigger app actions for album, activities,
photo exercises, and poem exercises. Do not directly create caregiver-owned
schedules from patient voice; ask the caregiver to confirm schedule changes.
Do not claim a task or medicine was completed unless the tool output says it is
completed. Keep answers one sentence unless the user asks for details.
Do not use Markdown, bullets, asterisks, emoji, or English status labels in spoken
answers. Translate stored status values into natural Arabic before speaking.
""".strip()


_TEXT_PLANNER_INSTRUCTIONS = (
    _SYSTEM_INSTRUCTIONS
    + "\nReturn only compact JSON. Allowed actions: answer, complete_task, snooze_task, "
    "decline_task, undo_complete_task, request_help, open_album, open_activities, "
    "start_poem_test, start_photo_test, start_activity, open_routine, open_dashboard, "
    "open_settings, request_add_task, request_edit_task, request_delete_task. "
    "Use complete_task when the user says they finished/did/took a "
    "task or medicine. Use decline_task when they say they did not do it. Use "
    "snooze_task when they ask to remind later. Use undo_complete_task when they say "
    "remove the done mark. Use request_help for help/emergency. Use open_album for "
    "album/photos memories, start_photo_test for photo recognition games, and "
    "start_poem_test for poem/poetry exercises. Use request_add_task for adding "
    "schedule items, request_edit_task for editing, and request_delete_task for "
    "deleting. The robot opens the correct app function immediately. Do not say "
    "you need permission or confirmation; say that you opened the correct function. "
    "The robot still must not directly bypass backend authorization for caregiver-owned schedule storage. "
    "For request_add_task include routine object: "
    "{type:'appointment'|'meal'|'water'|'spiritual'|'memory_exercise'|'conversation'|'custom'|'medication', "
    "title:string, time_24h:'HH:MM', description:string|null, medication:null or "
    "{medication_name:string,dosage_text:string,instructions:string|null}}. "
    "If the user says appointment, use type appointment. If they say task without a specific type, use custom. "
    "Required JSON keys: action, assistant_text, query, minutes, routine. Keep assistant_text plain spoken Arabic and do not claim success before "
    "the robot executes the action."
)


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
    {
        "type": "function",
        "name": "complete_task",
        "description": "Mark the best matching synced RAFEEQ task occurrence as completed.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "snooze_task",
        "description": "Snooze the best matching synced RAFEEQ task occurrence.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "minutes": {"type": "integer", "minimum": 1, "maximum": 120},
            },
            "required": ["query", "minutes"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "decline_task",
        "description": "Mark the best matching synced RAFEEQ task occurrence as missed.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "undo_complete_task",
        "description": "Remove the completed mark from the best matching completed task.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "request_help",
        "description": "Trigger RAFEEQ SOS help request.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "send_app_action",
        "description": "Send a supported app action event such as album, poem, or photo activity.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "open_dashboard",
                        "open_routine",
                        "open_activities",
                        "open_album",
                        "start_poem_test",
                        "start_photo_test",
                    ],
                },
                "assistant_text": {"type": "string"},
            },
            "required": ["action", "assistant_text"],
            "additionalProperties": False,
        },
    },
]
