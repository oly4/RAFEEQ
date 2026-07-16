from datetime import timezone

from fastapi import WebSocket

from rafeeq_backend.models import EmergencyEvent, utc_now


class RealtimeHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, patient_id: str, websocket: WebSocket) -> None:
        self._connections.setdefault(patient_id, set()).add(websocket)

    def disconnect(self, patient_id: str, websocket: WebSocket) -> None:
        connections = self._connections.get(patient_id)
        if connections:
            connections.discard(websocket)
            if not connections:
                self._connections.pop(patient_id, None)

    async def broadcast_emergency(self, emergency: EmergencyEvent) -> None:
        message = {
            "type": "emergency.updated",
            "version": 1,
            "patient_id": emergency.patient_id,
            "occurred_at": utc_now().astimezone(timezone.utc).isoformat(),
            "data": {
                "id": emergency.id,
                "type": emergency.type,
                "status": emergency.status,
                "severity": emergency.severity,
            },
        }
        stale: list[WebSocket] = []
        for websocket in self._connections.get(emergency.patient_id, set()).copy():
            try:
                await websocket.send_json(message)
            except RuntimeError:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(emergency.patient_id, websocket)


realtime_hub = RealtimeHub()
