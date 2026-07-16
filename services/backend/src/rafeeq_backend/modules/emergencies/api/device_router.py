from fastapi import APIRouter, HTTPException

from rafeeq_backend.models import utc_now
from rafeeq_backend.modules.auth.api.dependencies import DbSession
from rafeeq_backend.modules.devices.api.dependencies import CurrentDevice
from rafeeq_backend.modules.emergencies.application.service import ingest_event
from rafeeq_backend.modules.emergencies.domain.schemas import (
    BatchIngestResponse,
    DeviceEventBatch,
)
from rafeeq_backend.modules.notifications.infrastructure.realtime import realtime_hub
from rafeeq_backend.models import EmergencyEvent

router = APIRouter(prefix="/device-api/v1", tags=["device-api"])


@router.post("/events/batch", response_model=BatchIngestResponse)
async def ingest_batch(
    request: DeviceEventBatch, device: CurrentDevice, db: DbSession
) -> BatchIngestResponse:
    items = []
    for event in request.events:
        if str(event.device_id) != device.id or str(event.patient_id) != device.patient_id:
            raise HTTPException(status_code=403, detail="Event ownership mismatch")
        items.append(ingest_event(db, device, event))
    device.last_seen_at = utc_now()
    device.status = "online"
    db.commit()
    for item in items:
        if item.emergency_id:
            emergency = db.get(EmergencyEvent, item.emergency_id)
            if emergency:
                await realtime_hub.broadcast_emergency(emergency)
    return BatchIngestResponse(items=items)
