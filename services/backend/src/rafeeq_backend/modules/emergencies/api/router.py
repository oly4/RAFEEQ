from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from rafeeq_backend.config import get_settings
from rafeeq_backend.models import Device, EmergencyEvent
from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.emergencies.application.service import ingest_event, transition_by_user
from rafeeq_backend.modules.emergencies.domain.schemas import (
    DeviceEventEnvelope,
    EmergencyList,
    EmergencyResponse,
    ResolveRequest,
    VerificationSimulationRequest,
)
from rafeeq_backend.modules.patients.application.policies import (
    require_caregiver_access,
    require_patient_access,
)
from rafeeq_backend.modules.notifications.infrastructure.realtime import realtime_hub

router = APIRouter(tags=["emergencies"])


@router.get("/patients/{patient_id}/emergencies", response_model=EmergencyList)
def list_emergencies(patient_id: str, user: CurrentUser, db: DbSession) -> EmergencyList:
    require_patient_access(db, user, patient_id)
    items = list(
        db.scalars(
            select(EmergencyEvent)
            .where(EmergencyEvent.patient_id == patient_id)
            .order_by(EmergencyEvent.detected_at.desc())
        ).all()
    )
    return EmergencyList(
        items=[EmergencyResponse.model_validate(item) for item in items], total=len(items)
    )


def _authorized_emergency(emergency_id: str, user: CurrentUser, db: DbSession) -> EmergencyEvent:
    emergency = db.get(EmergencyEvent, emergency_id)
    if emergency is None:
        raise HTTPException(status_code=404, detail="Emergency not found")
    require_caregiver_access(db, user, emergency.patient_id)
    return emergency


@router.post("/emergencies/{emergency_id}/acknowledge", response_model=EmergencyResponse)
async def acknowledge(emergency_id: str, user: CurrentUser, db: DbSession) -> EmergencyResponse:
    emergency = _authorized_emergency(emergency_id, user, db)
    try:
        updated = transition_by_user(db, emergency, user.id, "acknowledged")
        await realtime_hub.broadcast_emergency(updated)
        return EmergencyResponse.model_validate(updated)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/emergencies/{emergency_id}/resolve", response_model=EmergencyResponse)
async def resolve(
    emergency_id: str, request: ResolveRequest, user: CurrentUser, db: DbSession
) -> EmergencyResponse:
    emergency = _authorized_emergency(emergency_id, user, db)
    try:
        updated = transition_by_user(db, emergency, user.id, "resolved", request.resolution_note)
        await realtime_hub.broadcast_emergency(updated)
        return EmergencyResponse.model_validate(updated)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/devices/{device_id}/simulate-sos", response_model=EmergencyResponse)
async def simulate_sos(device_id: str, user: CurrentUser, db: DbSession) -> EmergencyResponse:
    if get_settings().app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")
    device = db.get(Device, device_id)
    if device is None or device.patient_id is None:
        raise HTTPException(status_code=404, detail="Device not found")
    require_caregiver_access(db, user, device.patient_id)
    now = datetime.now(timezone.utc)
    event_id = uuid4()
    result = ingest_event(
        db,
        device,
        DeviceEventEnvelope(
            schema_version=1,
            event_id=event_id,
            event_type="sos_pressed",
            device_id=UUID(device.id),
            patient_id=UUID(device.patient_id),
            occurred_at=now,
            sequence=0,
            payload={"simulation": True},
        ),
    )
    emergency = db.get(EmergencyEvent, result.emergency_id)
    if emergency:
        await realtime_hub.broadcast_emergency(emergency)
    return EmergencyResponse.model_validate(emergency)


@router.post("/devices/{device_id}/simulate-fall", response_model=EmergencyResponse)
async def simulate_fall(device_id: str, user: CurrentUser, db: DbSession) -> EmergencyResponse:
    if get_settings().app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")
    device = db.get(Device, device_id)
    if device is None or device.patient_id is None:
        raise HTTPException(status_code=404, detail="Device not found")
    require_caregiver_access(db, user, device.patient_id)
    result = ingest_event(
        db,
        device,
        DeviceEventEnvelope(
            schema_version=1,
            event_id=uuid4(),
            event_type="possible_fall_detected",
            device_id=UUID(device.id),
            patient_id=UUID(device.patient_id),
            occurred_at=datetime.now(timezone.utc),
            sequence=0,
            payload={
                "simulation": True,
                "confidence": 0.82,
                "reason_codes": ["mock_trigger"],
            },
        ),
    )
    emergency = db.get(EmergencyEvent, result.emergency_id)
    if emergency:
        await realtime_hub.broadcast_emergency(emergency)
    return EmergencyResponse.model_validate(emergency)


@router.post(
    "/emergencies/{emergency_id}/simulate-verification",
    response_model=EmergencyResponse,
)
async def simulate_verification(
    emergency_id: str,
    request: VerificationSimulationRequest,
    user: CurrentUser,
    db: DbSession,
) -> EmergencyResponse:
    if get_settings().app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")
    emergency = _authorized_emergency(emergency_id, user, db)
    if emergency.status != "verifying" or emergency.device_id is None:
        raise HTTPException(status_code=409, detail="Emergency is not awaiting verification")
    device = db.get(Device, emergency.device_id)
    if device is None or device.patient_id is None:
        raise HTTPException(status_code=404, detail="Device not found")
    result = ingest_event(
        db,
        device,
        DeviceEventEnvelope(
            schema_version=1,
            event_id=uuid4(),
            event_type="fall_verification_result",
            device_id=UUID(device.id),
            patient_id=UUID(device.patient_id),
            occurred_at=datetime.now(timezone.utc),
            sequence=0,
            payload={
                "related_event_id": emergency.source_event_id,
                "outcome": request.outcome,
                "simulation": True,
            },
        ),
    )
    updated = db.get(EmergencyEvent, result.emergency_id)
    if updated:
        await realtime_hub.broadcast_emergency(updated)
    return EmergencyResponse.model_validate(updated)
