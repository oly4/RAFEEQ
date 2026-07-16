from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from rafeeq_backend.models import MedicationDetail, Routine, RoutineOccurrence, utc_now
from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.patients.application.policies import (
    require_caregiver_access,
    require_patient_access,
)
from rafeeq_backend.modules.routines.domain.schemas import (
    CompletionRequest,
    MedicationResponse,
    OccurrenceList,
    OccurrenceResponse,
    RoutineCreate,
    RoutineList,
    RoutineResponse,
    RoutineUpdate,
    SnoozeRequest,
)

router = APIRouter(tags=["routines"])


def routine_response(routine: Routine, medication: MedicationDetail | None) -> RoutineResponse:
    response = RoutineResponse.model_validate(routine)
    response.medication = MedicationResponse.model_validate(medication) if medication else None
    return response


@router.get("/patients/{patient_id}/routines", response_model=RoutineList)
def list_routines(patient_id: str, user: CurrentUser, db: DbSession) -> RoutineList:
    require_patient_access(db, user, patient_id)
    routines = list(
        db.scalars(
            select(Routine)
            .where(Routine.patient_id == patient_id, Routine.is_active.is_(True))
            .order_by(Routine.scheduled_local_time)
        ).all()
    )
    medication_by_routine = (
        {
            item.routine_id: item
            for item in db.scalars(
                select(MedicationDetail).where(
                    MedicationDetail.routine_id.in_([routine.id for routine in routines])
                )
            ).all()
        }
        if routines
        else {}
    )
    return RoutineList(
        items=[routine_response(item, medication_by_routine.get(item.id)) for item in routines],
        total=len(routines),
    )


@router.post(
    "/patients/{patient_id}/routines",
    response_model=RoutineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_routine(
    patient_id: str, request: RoutineCreate, user: CurrentUser, db: DbSession
) -> RoutineResponse:
    if user.role == "doctor":
        require_patient_access(db, user, patient_id)
        if request.type != "medication":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Doctors can only add medication routines",
            )
    else:
        require_caregiver_access(db, user, patient_id)
    try:
        local_zone = ZoneInfo(request.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Unknown timezone") from exc
    routine = Routine(
        patient_id=patient_id,
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
        created_by=user.id,
    )
    db.add(routine)
    db.flush()
    medication = None
    if request.medication:
        medication = MedicationDetail(routine_id=routine.id, **request.medication.model_dump())
        db.add(medication)
    scheduled_local = datetime.combine(
        request.start_date, request.scheduled_local_time, tzinfo=local_zone
    )
    db.add(
        RoutineOccurrence(
            routine_id=routine.id,
            patient_id=patient_id,
            scheduled_at_utc=scheduled_local.astimezone(timezone.utc),
            status="pending",
        )
    )
    db.commit()
    db.refresh(routine)
    if medication:
        db.refresh(medication)
    return routine_response(routine, medication)


def _get_routine_for_caregiver(db: DbSession, routine_id: str, user: CurrentUser) -> Routine:
    routine = db.get(Routine, routine_id)
    if routine is None or not routine.is_active:
        raise HTTPException(status_code=404, detail="Routine not found")
    require_caregiver_access(db, user, routine.patient_id)
    return routine


def _routine_medication(db: DbSession, routine_id: str) -> MedicationDetail | None:
    return db.scalar(select(MedicationDetail).where(MedicationDetail.routine_id == routine_id))


@router.patch("/routines/{routine_id}", response_model=RoutineResponse)
def update_routine(
    routine_id: str, request: RoutineUpdate, user: CurrentUser, db: DbSession
) -> RoutineResponse:
    routine = _get_routine_for_caregiver(db, routine_id, user)
    if request.title is not None:
        routine.title = request.title.strip()
    if request.description is not None:
        routine.description = request.description.strip() or None
    if request.scheduled_local_time is not None:
        routine.scheduled_local_time = request.scheduled_local_time
        try:
            local_zone = ZoneInfo(routine.timezone)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="Unknown timezone") from exc
        pending_occurrences = list(
            db.scalars(
                select(RoutineOccurrence).where(
                    RoutineOccurrence.routine_id == routine.id,
                    RoutineOccurrence.status.in_(("pending", "reminded", "snoozed")),
                )
            ).all()
        )
        for occurrence in pending_occurrences:
            local_day = occurrence.scheduled_at_utc.astimezone(local_zone).date()
            updated_local = datetime.combine(
                local_day, request.scheduled_local_time, tzinfo=local_zone
            )
            occurrence.scheduled_at_utc = updated_local.astimezone(timezone.utc)
    medication = _routine_medication(db, routine.id)
    if routine.type == "medication":
        if request.medication is None:
            raise HTTPException(status_code=422, detail="Medication details are required")
        if medication is None:
            medication = MedicationDetail(routine_id=routine.id, **request.medication.model_dump())
            db.add(medication)
        else:
            medication.medication_name = request.medication.medication_name.strip()
            medication.dosage_text = request.medication.dosage_text.strip()
            medication.instructions = request.medication.instructions
        routine.title = request.medication.medication_name.strip()
    elif request.medication is not None:
        raise HTTPException(
            status_code=422, detail="Medication details are only valid for medication routines"
        )
    db.commit()
    db.refresh(routine)
    if medication is not None:
        db.refresh(medication)
    return routine_response(routine, medication)


@router.delete("/routines/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routine(routine_id: str, user: CurrentUser, db: DbSession) -> None:
    routine = _get_routine_for_caregiver(db, routine_id, user)
    routine.is_active = False
    for occurrence in db.scalars(
        select(RoutineOccurrence).where(
            RoutineOccurrence.routine_id == routine.id,
            RoutineOccurrence.status.in_(("pending", "reminded", "snoozed")),
        )
    ).all():
        occurrence.status = "cancelled"
        occurrence.confirmation_source = "caregiver"
    db.commit()


@router.get("/patients/{patient_id}/routine-occurrences", response_model=OccurrenceList)
def list_occurrences(patient_id: str, user: CurrentUser, db: DbSession) -> OccurrenceList:
    require_patient_access(db, user, patient_id)
    items = list(
        db.scalars(
            select(RoutineOccurrence)
            .where(RoutineOccurrence.patient_id == patient_id)
            .order_by(RoutineOccurrence.scheduled_at_utc)
        ).all()
    )
    return OccurrenceList(
        items=[OccurrenceResponse.model_validate(item) for item in items], total=len(items)
    )


def get_occurrence(db: DbSession, occurrence_id: str) -> RoutineOccurrence:
    occurrence = db.get(RoutineOccurrence, occurrence_id)
    if occurrence is None:
        raise HTTPException(status_code=404, detail="Occurrence not found")
    return occurrence


@router.post("/routine-occurrences/{occurrence_id}/complete", response_model=OccurrenceResponse)
def complete_occurrence(
    occurrence_id: str, request: CompletionRequest, user: CurrentUser, db: DbSession
) -> OccurrenceResponse:
    occurrence = get_occurrence(db, occurrence_id)
    require_caregiver_access(db, user, occurrence.patient_id)
    if occurrence.status in ("cancelled", "completed"):
        if occurrence.status == "completed":
            return OccurrenceResponse.model_validate(occurrence)
        raise HTTPException(status_code=409, detail="Occurrence cannot be completed")
    occurrence.status = "completed"
    occurrence.completed_at = utc_now()
    occurrence.confirmation_source = request.confirmation_source
    occurrence.notes = request.notes
    db.commit()
    db.refresh(occurrence)
    return OccurrenceResponse.model_validate(occurrence)


@router.post(
    "/routine-occurrences/{occurrence_id}/undo-complete",
    response_model=OccurrenceResponse,
)
def undo_complete_occurrence(
    occurrence_id: str, user: CurrentUser, db: DbSession
) -> OccurrenceResponse:
    occurrence = get_occurrence(db, occurrence_id)
    require_caregiver_access(db, user, occurrence.patient_id)
    if occurrence.status != "completed":
        return OccurrenceResponse.model_validate(occurrence)
    occurrence.status = "pending"
    occurrence.completed_at = None
    occurrence.confirmation_source = None
    occurrence.notes = None
    db.commit()
    db.refresh(occurrence)
    return OccurrenceResponse.model_validate(occurrence)


@router.post("/routine-occurrences/{occurrence_id}/snooze", response_model=OccurrenceResponse)
def snooze_occurrence(
    occurrence_id: str, request: SnoozeRequest, user: CurrentUser, db: DbSession
) -> OccurrenceResponse:
    occurrence = get_occurrence(db, occurrence_id)
    require_caregiver_access(db, user, occurrence.patient_id)
    if occurrence.status not in ("pending", "reminded", "snoozed"):
        raise HTTPException(status_code=409, detail="Occurrence cannot be snoozed")
    occurrence.status = "snoozed"
    occurrence.scheduled_at_utc += timedelta(minutes=request.minutes)
    db.commit()
    db.refresh(occurrence)
    return OccurrenceResponse.model_validate(occurrence)


@router.post("/routine-occurrences/{occurrence_id}/skip", response_model=OccurrenceResponse)
def skip_occurrence(occurrence_id: str, user: CurrentUser, db: DbSession) -> OccurrenceResponse:
    occurrence = get_occurrence(db, occurrence_id)
    require_caregiver_access(db, user, occurrence.patient_id)
    if occurrence.status == "completed":
        raise HTTPException(status_code=409, detail="Completed occurrence cannot be skipped")
    occurrence.status = "skipped"
    occurrence.confirmation_source = "caregiver"
    db.commit()
    db.refresh(occurrence)
    return OccurrenceResponse.model_validate(occurrence)
