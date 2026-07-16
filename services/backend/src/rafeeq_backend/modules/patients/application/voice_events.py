from __future__ import annotations

from itertools import count
from typing import Any

_VOICE_COMMAND_SEQUENCE = count(1)
_VOICE_COMMAND_EVENTS: dict[str, list[dict[str, object]]] = {}


def store_voice_command_event(patient_id: str, event: dict[str, Any]) -> None:
    payload: dict[str, object] = dict(event)
    payload["assistant_text"] = ""
    payload["audio_data_url"] = None
    payload["sequence"] = next(_VOICE_COMMAND_SEQUENCE)
    events = _VOICE_COMMAND_EVENTS.setdefault(patient_id, [])
    events.append(payload)
    del events[:-20]


def list_voice_command_events(patient_id: str, since: int = 0) -> dict[str, object]:
    items = [
        item
        for item in _VOICE_COMMAND_EVENTS.get(patient_id, [])
        if int(item.get("sequence", 0)) > since
    ]
    latest_sequence = since
    if items:
        latest_sequence = max(int(item.get("sequence", since)) for item in items)
    return {"items": items, "latest_sequence": latest_sequence}
