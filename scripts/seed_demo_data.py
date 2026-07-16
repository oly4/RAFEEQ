from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from rafeeq_backend.database import SessionLocal
from rafeeq_backend.models import (
    ActivityDefinition,
    CaregiverPatient,
    Device,
    DoctorNote,
    DoctorPatient,
    EmergencyContact,
    EmergencyEvent,
    EmergencyStateTransition,
    MedicationDetail,
    MemoryCategory,
    MemoryItem,
    Patient,
    Routine,
    RoutineOccurrence,
    User,
    utc_now,
)
from rafeeq_backend.modules.auth.infrastructure.security import hash_password


def required_secret(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(
            f"Set {name} in the local environment before seeding demo accounts."
        )
    return value


def main() -> None:
    caregiver_password = required_secret("DEMO_CAREGIVER_PASSWORD")
    doctor_password = required_secret("DEMO_DOCTOR_PASSWORD")
    device_secret = required_secret("DEMO_DEVICE_SECRET")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == "caregiver@demo.rafeeq.app")):
            print("Demo data already exists; no changes made.")
            return
        caregiver = User(
            role="caregiver",
            full_name="Demo Caregiver",
            email="caregiver@demo.rafeeq.app",
            password_hash=hash_password(caregiver_password),
            email_verified_at=utc_now(),
        )
        doctor = User(
            role="doctor",
            full_name="Dr Demo",
            email="doctor@demo.rafeeq.app",
            password_hash=hash_password(doctor_password),
            email_verified_at=utc_now(),
        )
        patient = Patient(
            display_name="أمينة التجريبية",
            preferred_language="ar",
            timezone="Europe/London",
            condition_notes="Placeholder demo profile; contains no real patient data.",
        )
        db.add_all([caregiver, doctor, patient])
        db.flush()
        db.add_all(
            [
                CaregiverPatient(
                    caregiver_user_id=caregiver.id,
                    patient_id=patient.id,
                    relationship_label="family",
                    is_primary=True,
                    permissions_json={"manage": True},
                ),
                DoctorPatient(
                    doctor_user_id=doctor.id,
                    patient_id=patient.id,
                    assigned_by=caregiver.id,
                ),
                EmergencyContact(
                    patient_id=patient.id,
                    name="Demo Contact One",
                    relationship="daughter",
                    phone="+440000000001",
                    priority_order=1,
                ),
                EmergencyContact(
                    patient_id=patient.id,
                    name="Demo Contact Two",
                    relationship="son",
                    phone="+440000000002",
                    priority_order=2,
                ),
            ]
        )
        device = Device(
            patient_id=patient.id,
            device_serial="SIM-DEMO-001",
            display_name="RAFEEQ Demo Simulator",
            secret_hash=sha256(device_secret.encode()).hexdigest(),
            status="online",
            last_seen_at=utc_now(),
            paired_at=utc_now(),
        )
        db.add(device)
        db.flush()
        today = datetime.now(timezone.utc).date()
        routine_specs = [
            ("medication", "دواء الصباح", time(9), "Demo medicine A", "One tablet"),
            ("medication", "دواء الظهر", time(13), "Demo medicine B", "One tablet"),
            ("medication", "دواء المساء", time(20), "Demo medicine C", "One tablet"),
            ("water", "شرب الماء", time(11), None, None),
            ("memory_exercise", "تمرين الذاكرة", time(16), None, None),
        ]
        for index, (kind, title, scheduled, medicine, dosage) in enumerate(
            routine_specs
        ):
            routine = Routine(
                patient_id=patient.id,
                type=kind,
                title=title,
                timezone=patient.timezone,
                start_date=today,
                recurrence_rule="FREQ=DAILY",
                scheduled_local_time=scheduled,
                requires_confirmation=True,
                created_by=caregiver.id,
            )
            db.add(routine)
            db.flush()
            if medicine and dosage:
                db.add(
                    MedicationDetail(
                        routine_id=routine.id,
                        medication_name=medicine,
                        dosage_text=dosage,
                        instructions="Demo only; not medical advice.",
                    )
                )
            status = (
                "completed"
                if index in (0, 3)
                else "missed"
                if index == 1
                else "pending"
            )
            db.add(
                RoutineOccurrence(
                    routine_id=routine.id,
                    patient_id=patient.id,
                    scheduled_at_utc=datetime.combine(
                        today, scheduled, tzinfo=timezone.utc
                    ),
                    status=status,
                    completed_at=utc_now() if status == "completed" else None,
                    confirmation_source="manual" if status == "completed" else None,
                )
            )
        for activity_type, title in [
            ("recognize_photos", "التعرف على الصور"),
            ("complete_phrase", "إكمال عبارة مألوفة"),
            ("calm_music", "موسيقى هادئة"),
            ("conversation", "محادثة ودية"),
            ("reading", "قراءة أو قرآن"),
            ("memory_exercise", "تمرين الذاكرة"),
        ]:
            db.add(
                ActivityDefinition(
                    patient_id=patient.id,
                    type=activity_type,
                    title=title,
                    duration_minutes=10,
                    created_by=caregiver.id,
                )
            )
        categories: list[MemoryCategory] = []
        for order, name in enumerate(
            ("العائلة", "الأصدقاء", "المناسبات", "ذكريات جديدة")
        ):
            category = MemoryCategory(
                patient_id=patient.id, name=name, sort_order=order
            )
            db.add(category)
            categories.append(category)
        db.flush()
        for index in range(8):
            db.add(
                MemoryItem(
                    patient_id=patient.id,
                    category_id=categories[index % len(categories)].id,
                    title=f"ذكرى تجريبية {index + 1}",
                    description="Placeholder, non-sensitive demonstration content.",
                    media_type="text",
                    people_labels_json=[],
                    visibility="caregivers",
                    created_by=caregiver.id,
                )
            )
        db.add(
            DoctorNote(
                patient_id=patient.id,
                doctor_user_id=doctor.id,
                text="Demo follow-up note; not clinical advice.",
                is_shared_with_caregiver=True,
                follow_up_at=utc_now() + timedelta(days=7),
            )
        )
        for event_type, status, note in [
            ("possible_fall", "false_alarm", None),
            ("sos", "resolved", "Resolved demo event"),
        ]:
            event = EmergencyEvent(
                patient_id=patient.id,
                device_id=device.id,
                type=event_type,
                severity="critical" if event_type == "sos" else "warning",
                status=status,
                detected_at=utc_now() - timedelta(days=1),
                confirmed_at=utc_now() - timedelta(days=1)
                if event_type == "sos"
                else None,
                resolved_at=utc_now() if status == "resolved" else None,
                resolved_by=caregiver.id if status == "resolved" else None,
                resolution_note=note,
                source_event_id=str(uuid4()),
                metadata_json={"demo": True},
            )
            db.add(event)
            db.flush()
            db.add(
                EmergencyStateTransition(
                    emergency_event_id=event.id,
                    from_status="acknowledged" if status == "resolved" else "verifying",
                    to_status=status,
                    actor_type="system",
                    reason="Seeded demo history",
                )
            )
        db.commit()
    print("Seeded non-sensitive RAFEEQ demo data.")


if __name__ == "__main__":
    main()
