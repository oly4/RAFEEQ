from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from rafeeq_backend.models import (
    CaregiverPatient,
    MedicationDetail,
    Patient,
    Routine,
    RoutineOccurrence,
    utc_now,
)
from rafeeq_backend.modules.auth.api.dependencies import DbSession
from rafeeq_backend.modules.devices.api.dependencies import CurrentDevice
from rafeeq_backend.modules.routines.domain.schemas import RoutineCreate, RoutineResponse
from rafeeq_backend.modules.synchronization.domain.schemas import (
    DeviceStatusResponse,
    HeartbeatRequest,
    SyncAckRequest,
    SyncSnapshot,
)

router = APIRouter(prefix="/device-api/v1", tags=["device-api"])


@router.get("/sync/snapshot", response_model=SyncSnapshot)
def sync_snapshot(device: CurrentDevice, db: DbSession) -> SyncSnapshot:
    patient = db.get(Patient, device.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Paired patient not found")
    routines = list(
        db.scalars(
            select(Routine)
            .where(Routine.patient_id == device.patient_id, Routine.is_active.is_(True))
            .order_by(Routine.scheduled_local_time)
        ).all()
    )
    routine_ids = [item.id for item in routines]
    medications = (
        {
            item.routine_id: item
            for item in db.scalars(
                select(MedicationDetail).where(MedicationDetail.routine_id.in_(routine_ids))
            ).all()
        }
        if routine_ids
        else {}
    )
    occurrences = (
        list(
            db.scalars(
                select(RoutineOccurrence).where(RoutineOccurrence.routine_id.in_(routine_ids))
            ).all()
        )
        if routine_ids
        else []
    )
    occurrences_by_routine: dict[str, list[RoutineOccurrence]] = {}
    for occurrence in occurrences:
        occurrences_by_routine.setdefault(occurrence.routine_id, []).append(occurrence)
    generated_at = utc_now()
    version_parts = [item.updated_at.astimezone(timezone.utc).isoformat() for item in routines]
    configuration_version = max(version_parts, default=generated_at.isoformat())
    routine_payload = []
    for routine in routines:
        medication = medications.get(routine.id)
        routine_payload.append(
            {
                "id": routine.id,
                "type": routine.type,
                "title": routine.title,
                "description": routine.description,
                "timezone": routine.timezone,
                "scheduled_local_time": routine.scheduled_local_time.isoformat(),
                "recurrence_rule": routine.recurrence_rule,
                "requires_confirmation": routine.requires_confirmation,
                "snooze_minutes": routine.snooze_minutes,
                "max_snoozes": routine.max_snoozes,
                "medication": {
                    "medication_name": medication.medication_name,
                    "dosage_text": medication.dosage_text,
                    "instructions": medication.instructions,
                }
                if medication
                else None,
                "occurrences": [
                    {
                        "id": occurrence.id,
                        "scheduled_at_utc": occurrence.scheduled_at_utc,
                        "status": occurrence.status,
                    }
                    for occurrence in occurrences_by_routine.get(routine.id, [])
                ],
            }
        )
    return SyncSnapshot(
        configuration_version=configuration_version,
        generated_at=generated_at,
        patient={
            "id": patient.id,
            "display_name": patient.display_name,
            "preferred_language": patient.preferred_language,
            "timezone": patient.timezone,
            "accessibility_preferences": patient.accessibility_preferences_json,
        },
        routines=routine_payload,
        emergency_settings={"fall_verification_timeout_seconds": 20},
        voice_preferences={"locale": patient.preferred_language},
    )


@router.post(
    "/voice-routines",
    response_model=RoutineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_voice_routine(
    request: RoutineCreate, device: CurrentDevice, db: DbSession
) -> RoutineResponse:
    if device.patient_id is None:
        raise HTTPException(status_code=409, detail="Device is not paired to a patient")
    if request.type == "medication":
        raise HTTPException(
            status_code=409,
            detail="Medication schedules must be created by a caregiver in the app",
        )
    try:
        local_zone = ZoneInfo(request.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Unknown timezone") from exc

    caregiver_link = db.scalar(
        select(CaregiverPatient)
        .where(CaregiverPatient.patient_id == device.patient_id)
        .order_by(CaregiverPatient.is_primary.desc(), CaregiverPatient.created_at)
    )
    if caregiver_link is None:
        raise HTTPException(status_code=409, detail="No caregiver linked to patient")

    routine = Routine(
        patient_id=device.patient_id,
        type=request.type,
        title=request.title.strip(),
        description=request.description,
        timezone=request.timezone,
        start_date=request.start_date,
        end_date=request.end_date,
        recurrence_rule=request.recurrence_rule,
        scheduled_local_time=request.scheduled_local_time,
        requires_confirmation=request.requires_confirmation,
        snooze_minutes=request.snooze_minutes,
        max_snoozes=request.max_snoozes,
        created_by=caregiver_link.caregiver_user_id,
    )
    db.add(routine)
    db.flush()
    scheduled_local = datetime.combine(
        request.start_date, request.scheduled_local_time, tzinfo=local_zone
    )
    db.add(
        RoutineOccurrence(
            routine_id=routine.id,
            patient_id=device.patient_id,
            scheduled_at_utc=scheduled_local.astimezone(timezone.utc),
            status="pending",
        )
    )
    db.commit()
    db.refresh(routine)
    return RoutineResponse.model_validate(routine)


@router.post("/sync/ack", response_model=DeviceStatusResponse)
def sync_ack(request: SyncAckRequest, device: CurrentDevice, db: DbSession) -> DeviceStatusResponse:
    now = utc_now()
    device.last_sync_at = now
    device.last_seen_at = now
    device.status = "online"
    db.commit()
    return DeviceStatusResponse(status="synced", server_time=now)


@router.post("/heartbeat", response_model=DeviceStatusResponse)
def heartbeat(
    request: HeartbeatRequest, device: CurrentDevice, db: DbSession
) -> DeviceStatusResponse:
    now = utc_now()
    device.last_seen_at = now
    device.status = "online"
    db.commit()
    return DeviceStatusResponse(status="online", server_time=now)
