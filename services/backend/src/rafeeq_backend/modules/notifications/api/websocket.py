import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from rafeeq_backend.models import User
from rafeeq_backend.modules.auth.api.dependencies import DbSession
from rafeeq_backend.modules.auth.infrastructure.security import decode_jwt
from rafeeq_backend.modules.notifications.infrastructure.realtime import realtime_hub
from rafeeq_backend.modules.patients.application.policies import can_access_patient

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/patients/{patient_id}")
async def patient_updates(websocket: WebSocket, patient_id: str, db: DbSession) -> None:
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        message = json.loads(raw)
        if message.get("type") != "authenticate" or not message.get("token"):
            await websocket.close(code=4401, reason="Authentication required")
            return
        payload = decode_jwt(str(message["token"]), "access")
        user = db.get(User, payload["sub"])
        if user is None or not can_access_patient(db, user, patient_id):
            await websocket.close(code=4403, reason="Patient access denied")
            return
        await realtime_hub.connect(patient_id, websocket)
        await websocket.send_json({"type": "connection.ready", "version": 1})
        while True:
            received = await websocket.receive_text()
            if received == "ping":
                await websocket.send_text("pong")
    except HTTPException:
        await websocket.close(code=4401, reason="Invalid token")
    except (WebSocketDisconnect, json.JSONDecodeError):
        pass
    finally:
        realtime_hub.disconnect(patient_id, websocket)
