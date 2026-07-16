from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select

from fastapi import APIRouter

from rafeeq_backend.models import (
    ActivityDefinition,
    ActivityLog,
    Device,
    EmergencyEvent,
    Routine,
    RoutineOccurrence,
)
from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.patients.application.policies import require_patient_access
from rafeeq_backend.modules.reports.domain.schemas import ReportSummary

router = APIRouter(tags=["reports"])


@router.get("/patients/{patient_id}/reports/summary", response_model=ReportSummary)
def report_summary(
    patient_id: str,
    user: CurrentUser,
    db: DbSession,
    period: Literal["all", "week", "month", "quarter"] = "all",
) -> ReportSummary:
    require_patient_access(db, user, patient_id)
    now = datetime.now(timezone.utc)
    period_days = {"week": 7, "month": 30, "quarter": 90}
    range_days = period_days.get(period)
    range_start_at = now - timedelta(days=range_days) if range_days else None
    occurrence_statement = select(RoutineOccurrence).where(
        RoutineOccurrence.patient_id == patient_id,
        RoutineOccurrence.status != "cancelled",
    )
    if range_start_at is not None:
        occurrence_statement = occurrence_statement.where(
            RoutineOccurrence.scheduled_at_utc >= range_start_at
        )
    occurrences = list(db.scalars(occurrence_statement).all())
    completed = [item for item in occurrences if item.status == "completed"]
    medication_ids = set(
        db.scalars(
            select(Routine.id).where(Routine.patient_id == patient_id, Routine.type == "medication")
        ).all()
    )
    medication = [item for item in occurrences if item.routine_id in medication_ids]
    medication_completed = [item for item in medication if item.status == "completed"]
    missed_medication = [item for item in medication if item.status in ("missed", "skipped")]
    activity_statement = select(ActivityLog).where(
        ActivityLog.patient_id == patient_id, ActivityLog.status == "completed"
    )
    if range_start_at is not None:
        activity_statement = activity_statement.where(ActivityLog.started_at >= range_start_at)
    activity_logs = list(db.scalars(activity_statement).all())
    activity_rows = db.execute(
        select(ActivityDefinition.id, ActivityDefinition.type).where(
            ActivityDefinition.patient_id == patient_id
        )
    ).all()
    activity_types: dict[str, str] = {row[0]: row[1] for row in activity_rows}
    memory_completed = len(
        [log for log in activity_logs if activity_types.get(log.activity_id) == "memory_exercise"]
    )
    conversations = len(
        [log for log in activity_logs if activity_types.get(log.activity_id) == "conversation"]
    )
    emergency_statement = select(EmergencyEvent).where(EmergencyEvent.patient_id == patient_id)
    if range_start_at is not None:
        emergency_statement = emergency_statement.where(
            EmergencyEvent.detected_at >= range_start_at
        )
    emergencies = list(db.scalars(emergency_statement).all())
    acknowledgement_seconds = [
        (item.acknowledged_at - item.detected_at).total_seconds()
        for item in emergencies
        if item.acknowledged_at is not None
    ]
    device = db.scalar(select(Device).where(Device.patient_id == patient_id))

    trend_start = range_start_at or (now - timedelta(days=7))
    trend_span = max(7, (now - trend_start).days)
    bucket_span = timedelta(days=trend_span / 7)
    medication_trend: list[float] = []
    memory_trend: list[int] = []
    for index in range(7):
        bucket_start = trend_start + bucket_span * index
        bucket_end = trend_start + bucket_span * (index + 1)
        bucket_medication = [
            item
            for item in medication
            if bucket_start <= item.scheduled_at_utc.replace(tzinfo=timezone.utc) < bucket_end
        ]
        bucket_completed = [item for item in bucket_medication if item.status == "completed"]
        medication_trend.append(
            round(len(bucket_completed) * 100 / len(bucket_medication), 1)
            if bucket_medication
            else 0
        )
        memory_trend.append(
            len(
                [
                    log
                    for log in activity_logs
                    if activity_types.get(log.activity_id) == "memory_exercise"
                    and bucket_start <= log.started_at.replace(tzinfo=timezone.utc) < bucket_end
                ]
            )
        )

    return ReportSummary(
        period=period,
        range_start=(range_start_at or trend_start).date(),
        range_end=now.date(),
        routine_completion_rate=round(len(completed) * 100 / len(occurrences), 1)
        if occurrences
        else 0,
        medication_adherence_rate=round(len(medication_completed) * 100 / len(medication), 1)
        if medication
        else 0,
        missed_medication_count=len(missed_medication),
        memory_activities_completed=memory_completed,
        total_activity_sessions=len(activity_logs),
        conversation_interactions=conversations,
        emergency_count=len(emergencies),
        average_emergency_acknowledgment_seconds=(
            round(sum(acknowledgement_seconds) / len(acknowledgement_seconds), 1)
            if acknowledgement_seconds
            else None
        ),
        device_online_percentage=100 if device and device.status == "online" else 0,
        medication_adherence_trend=medication_trend,
        memory_activity_trend=memory_trend,
        disclaimer="Adherence and activity indicators only; not a medical diagnosis.",
    )
