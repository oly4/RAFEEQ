from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from rafeeq_backend.models import (
    AuditLog,
    CaregiverPatient,
    Device,
    DeviceEvent,
    EmergencyEvent,
    EmergencyStateTransition,
    MedicationDetail,
    Notification,
    Patient,
    Routine,
    RoutineOccurrence,
    utc_now,
)
from rafeeq_backend.modules.emergencies.domain.schemas import DeviceEventEnvelope, IngestResult
from rafeeq_backend.modules.patients.application.voice_events import store_voice_command_event


def _transition(
    db: Session,
    emergency: EmergencyEvent,
    from_status: str | None,
    to_status: str,
    actor_type: str,
    actor_id: str | None,
    reason: str,
) -> None:
    db.add(
        EmergencyStateTransition(
            emergency_event_id=emergency.id,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )
    )
    emergency.status = to_status


def _queue_caregiver_notifications(db: Session, emergency: EmergencyEvent, patient_id: str) -> None:
    caregiver_ids = db.scalars(
        select(CaregiverPatient.caregiver_user_id).where(CaregiverPatient.patient_id == patient_id)
    ).all()
    for caregiver_id in caregiver_ids:
        db.add(
            Notification(
                user_id=caregiver_id,
                patient_id=patient_id,
                emergency_event_id=emergency.id,
                channel="websocket",
                title="تنبيه طارئ من رفيق",
                body="افتح تطبيق رفيق لعرض تفاصيل التنبيه.",
                status="pending",
            )
        )
    _transition(
        db,
        emergency,
        "confirmed",
        "notified",
        "system",
        None,
        "Caregiver notifications queued",
    )


def _duplicate_result(
    db: Session, event: DeviceEventEnvelope, existing: DeviceEvent
) -> IngestResult:
    emergency = db.scalar(
        select(EmergencyEvent).where(EmergencyEvent.source_event_id == existing.source_event_id)
    )
    if emergency is None and existing.event_type == "fall_verification_result":
        related = str(existing.payload_json.get("related_event_id", ""))
        emergency = db.scalar(
            select(EmergencyEvent).where(EmergencyEvent.source_event_id == related)
        )
    return IngestResult(
        event_id=event.event_id,
        status="duplicate",
        emergency_id=emergency.id if emergency else None,
    )


def ingest_event(db: Session, device: Device, event: DeviceEventEnvelope) -> IngestResult:
    patient_id = device.patient_id
    if patient_id is None:
        raise ValueError("Device is not paired to a patient")
    event_id = str(event.event_id)
    existing = db.scalar(select(DeviceEvent).where(DeviceEvent.source_event_id == event_id))
    if existing:
        return _duplicate_result(db, event, existing)
    normalized = DeviceEvent(
        source_event_id=event_id,
        device_id=device.id,
        patient_id=patient_id,
        event_type=event.event_type,
        payload_json={**event.payload, "sequence": event.sequence},
        occurred_at=event.occurred_at,
    )
    db.add(normalized)
    emergency: EmergencyEvent | None = None
    if event.event_type == "sos_pressed":
        emergency = EmergencyEvent(
            patient_id=patient_id,
            device_id=device.id,
            type="sos",
            severity="critical",
            status="detected",
            detected_at=event.occurred_at,
            confirmed_at=event.occurred_at,
            source_event_id=event_id,
            metadata_json={"confirmation": "physical_or_simulated_sos"},
        )
        db.add(emergency)
        db.flush()
        _transition(db, emergency, None, "detected", "device", device.id, "SOS event received")
        _transition(
            db, emergency, "detected", "confirmed", "system", None, "SOS skips verification"
        )
        _queue_caregiver_notifications(db, emergency, patient_id)
        db.add(
            AuditLog(
                actor_device_id=device.id,
                action="emergency.sos_ingested",
                entity_type="emergency",
                entity_id=emergency.id,
                metadata_json={"source_event_id": event_id},
            )
        )
    elif event.event_type == "possible_fall_detected":
        emergency = EmergencyEvent(
            patient_id=patient_id,
            device_id=device.id,
            type="possible_fall",
            severity="warning",
            status="detected",
            confidence=event.payload.get("confidence"),
            detected_at=event.occurred_at,
            source_event_id=event_id,
            metadata_json={"reason_codes": event.payload.get("reason_codes", [])},
        )
        db.add(emergency)
        db.flush()
        _transition(db, emergency, None, "detected", "device", device.id, "Possible fall detected")
        _transition(
            db, emergency, "detected", "verifying", "system", None, "Patient verification started"
        )
    elif event.event_type == "fall_verification_result":
        related_event_id = str(event.payload.get("related_event_id", ""))
        emergency = db.scalar(
            select(EmergencyEvent).where(EmergencyEvent.source_event_id == related_event_id)
        )
        if emergency and emergency.status == "verifying":
            outcome = str(event.payload.get("outcome", "timeout"))
            if outcome == "safe":
                _transition(
                    db,
                    emergency,
                    "verifying",
                    "false_alarm",
                    "device",
                    device.id,
                    "Patient confirmed safe",
                )
                emergency.metadata_json = {
                    **emergency.metadata_json,
                    "verification_outcome": "safe",
                }
            else:
                reason = "Patient requested help" if outcome == "help" else "Verification timed out"
                _transition(db, emergency, "verifying", "confirmed", "system", None, reason)
                emergency.type = "confirmed_fall"
                emergency.severity = "critical"
                emergency.confirmed_at = event.occurred_at
                emergency.metadata_json = {
                    **emergency.metadata_json,
                    "verification_outcome": outcome,
                    "confirmed_by_timeout": outcome == "timeout",
                }
                _queue_caregiver_notifications(db, emergency, patient_id)
    elif event.event_type in ("reminder_completed", "reminder_snoozed", "reminder_missed"):
        occurrence_id = str(event.payload.get("occurrence_id", ""))
        occurrence = db.get(RoutineOccurrence, occurrence_id)
        if occurrence and occurrence.patient_id == patient_id:
            if event.event_type == "reminder_completed":
                occurrence.status = "completed"
                occurrence.completed_at = event.occurred_at
                occurrence.confirmation_source = str(
                    event.payload.get("confirmation_source", "patient_voice")
                )
            elif event.event_type == "reminder_snoozed":
                occurrence.status = "snoozed"
            else:
                occurrence.status = "missed"
    elif event.event_type == "voice_app_action":
        action = str(event.payload.get("action") or "unknown")
        allowed_actions = {
            "open_dashboard",
            "open_routine",
            "open_activities",
            "open_album",
            "open_settings",
            "start_poem_test",
            "start_photo_test",
            "add_routine",
            "edit_routine",
            "delete_routine",
            "complete_routine",
            "undo_complete_routine",
            "unknown",
        }
        if action not in allowed_actions:
            action = "unknown"
        store_voice_command_event(
            patient_id,
            {
                "transcript": str(event.payload.get("transcript") or ""),
                "action": action,
                "assistant_text": str(event.payload.get("assistant_text") or ""),
                "audio_data_url": None,
                "routine_created": False,
                "routine_title": None,
                "needs_confirmation": False,
                "used_openai": bool(event.payload.get("used_openai", True)),
            },
        )
    elif event.event_type == "voice_routine_create":
        created = _create_voice_routine_from_device_event(db, device, patient_id, event)
        if created is not None:
            store_voice_command_event(
                patient_id,
                {
                    "transcript": str(event.payload.get("transcript") or ""),
                    "action": "add_routine",
                    "assistant_text": str(
                        event.payload.get("assistant_text") or f"تم، أضفت {created.title}."
                    ),
                    "audio_data_url": None,
                    "routine_created": True,
                    "routine_title": created.title,
                    "needs_confirmation": False,
                    "used_openai": bool(event.payload.get("used_openai", True)),
                },
            )
    db.commit()
    return IngestResult(
        event_id=event.event_id,
        status="processed",
        emergency_id=emergency.id if emergency else None,
    )


def _create_voice_routine_from_device_event(
    db: Session,
    device: Device,
    patient_id: str,
    event: DeviceEventEnvelope,
) -> Routine | None:
    patient = db.get(Patient, patient_id)
    routine_data = event.payload.get("routine")
    if patient is None or not isinstance(routine_data, dict):
        return None
    title = str(routine_data.get("title") or "").strip()
    time_24h = str(routine_data.get("time_24h") or "").strip()
    routine_type = str(routine_data.get("type") or "custom").strip()
    if not title or not time_24h:
        return None
    if routine_type not in {
        "medication",
        "appointment",
        "meal",
        "water",
        "spiritual",
        "memory_exercise",
        "conversation",
        "custom",
    }:
        routine_type = "custom"
    try:
        hour_text, minute_text = time_24h.split(":", 1)
        scheduled_time = time(int(hour_text), int(minute_text[:2]))
    except (TypeError, ValueError):
        return None
    try:
        local_zone = ZoneInfo(patient.timezone)
    except ZoneInfoNotFoundError:
        local_zone = timezone.utc
    caregiver_id = db.scalar(
        select(CaregiverPatient.caregiver_user_id)
        .where(CaregiverPatient.patient_id == patient_id)
        .order_by(CaregiverPatient.is_primary.desc(), CaregiverPatient.created_at)
        .limit(1)
    )
    if caregiver_id is None:
        return None
    today = datetime.now(local_zone).date()
    description_raw = routine_data.get("description")
    routine = Routine(
        patient_id=patient_id,
        type=routine_type,
        title=title[:200],
        description=str(description_raw).strip() if description_raw else None,
        timezone=patient.timezone,
        start_date=today,
        recurrence_rule="FREQ=DAILY",
        scheduled_local_time=scheduled_time,
        requires_confirmation=True,
        snooze_minutes=10,
        max_snoozes=2,
        created_by=str(caregiver_id),
    )
    db.add(routine)
    db.flush()
    if routine_type == "medication":
        medication_raw = routine_data.get("medication")
        medication_data = medication_raw if isinstance(medication_raw, dict) else {}
        medication_name = str(medication_data.get("medication_name") or title).strip()
        dosage_text = str(medication_data.get("dosage_text") or "حسب الوصفة").strip()
        instructions_raw = medication_data.get("instructions")
        db.add(
            MedicationDetail(
                routine_id=routine.id,
                medication_name=medication_name[:200],
                dosage_text=dosage_text[:200],
                instructions=str(instructions_raw).strip() if instructions_raw else None,
            )
        )
        routine.title = medication_name[:200]
    scheduled_local = datetime.combine(today, scheduled_time, tzinfo=local_zone)
    db.add(
        RoutineOccurrence(
            routine_id=routine.id,
            patient_id=patient_id,
            scheduled_at_utc=scheduled_local.astimezone(timezone.utc),
            status="pending",
        )
    )
    db.add(
        AuditLog(
            actor_device_id=device.id,
            action="routine.created_by_voice",
            entity_type="routine",
            entity_id=routine.id,
            metadata_json={
                "patient_id": patient_id,
                "transcript": str(event.payload.get("transcript") or ""),
            },
        )
    )
    return routine


def transition_by_user(
    db: Session,
    emergency: EmergencyEvent,
    user_id: str,
    target: str,
    note: str | None = None,
) -> EmergencyEvent:
    now = utc_now()
    if target == "acknowledged":
        if emergency.status in ("acknowledged", "resolved"):
            return emergency
        if emergency.status != "notified":
            raise ValueError("Emergency cannot be acknowledged from its current state")
        _transition(
            db, emergency, "notified", "acknowledged", "user", user_id, "Caregiver acknowledged"
        )
        emergency.acknowledged_at = now
        emergency.acknowledged_by = user_id
    elif target == "resolved":
        if emergency.status == "resolved":
            return emergency
        if emergency.status not in ("acknowledged", "confirmed"):
            raise ValueError("Emergency cannot be resolved from its current state")
        if emergency.severity == "critical" and not note:
            raise ValueError("A resolution note is required")
        previous = emergency.status
        _transition(db, emergency, previous, "resolved", "user", user_id, note or "Resolved")
        emergency.resolved_at = now
        emergency.resolved_by = user_id
        emergency.resolution_note = note
    db.add(
        AuditLog(
            actor_user_id=user_id,
            action=f"emergency.{target}",
            entity_type="emergency",
            entity_id=emergency.id,
            metadata_json={},
        )
    )
    db.commit()
    db.refresh(emergency)
    return emergency
