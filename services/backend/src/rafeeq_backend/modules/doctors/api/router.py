from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from rafeeq_backend.models import DoctorNote, DoctorPatient, Patient, User
from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.doctors.domain.schemas import (
    DoctorAssignmentResponse,
    DoctorInviteRequest,
    DoctorNoteCreate,
    DoctorNoteResponse,
)
from rafeeq_backend.modules.patients.application.policies import (
    require_caregiver_access,
    require_patient_access,
)
from rafeeq_backend.modules.patients.domain.schemas import PatientList, PatientResponse

router = APIRouter(tags=["doctors"])


@router.post("/patients/{patient_id}/doctors/invite", response_model=DoctorAssignmentResponse)
def invite_doctor(
    patient_id: str, request: DoctorInviteRequest, user: CurrentUser, db: DbSession
) -> DoctorAssignmentResponse:
    require_caregiver_access(db, user, patient_id)
    doctor = db.scalar(
        select(User).where(
            User.email == str(request.email).lower(),
            User.role == "doctor",
            User.is_active.is_(True),
        )
    )
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor account not found")
    assignment = db.get(DoctorPatient, (doctor.id, patient_id))
    if assignment is None:
        assignment = DoctorPatient(
            doctor_user_id=doctor.id,
            patient_id=patient_id,
            assigned_by=user.id,
            can_view_reports=True,
            can_add_notes=True,
        )
        db.add(assignment)
        db.commit()
    return DoctorAssignmentResponse(
        id=doctor.id,
        full_name=doctor.full_name,
        email=doctor.email,
        can_view_reports=assignment.can_view_reports,
        can_add_notes=assignment.can_add_notes,
    )


@router.get("/patients/{patient_id}/doctors", response_model=list[DoctorAssignmentResponse])
def list_doctors(
    patient_id: str, user: CurrentUser, db: DbSession
) -> list[DoctorAssignmentResponse]:
    require_patient_access(db, user, patient_id)
    rows = db.execute(
        select(User, DoctorPatient)
        .join(DoctorPatient, DoctorPatient.doctor_user_id == User.id)
        .where(DoctorPatient.patient_id == patient_id, DoctorPatient.revoked_at.is_(None))
    ).all()
    return [
        DoctorAssignmentResponse(
            id=doctor.id,
            full_name=doctor.full_name,
            email=doctor.email,
            can_view_reports=assignment.can_view_reports,
            can_add_notes=assignment.can_add_notes,
        )
        for doctor, assignment in rows
    ]


@router.get("/doctor/patients", response_model=PatientList)
def doctor_patients(user: CurrentUser, db: DbSession) -> PatientList:
    if user.role != "doctor":
        raise HTTPException(status_code=403, detail="Doctor access required")
    patients = list(
        db.scalars(
            select(Patient)
            .join(DoctorPatient)
            .where(DoctorPatient.doctor_user_id == user.id, DoctorPatient.revoked_at.is_(None))
        ).all()
    )
    return PatientList(
        items=[PatientResponse.model_validate(item) for item in patients], total=len(patients)
    )


@router.get("/doctor/patients/{patient_id}/notes", response_model=list[DoctorNoteResponse])
def list_doctor_notes(
    patient_id: str, user: CurrentUser, db: DbSession
) -> list[DoctorNoteResponse]:
    require_patient_access(db, user, patient_id)
    statement = select(DoctorNote).where(DoctorNote.patient_id == patient_id)
    if user.role == "caregiver":
        statement = statement.where(DoctorNote.is_shared_with_caregiver.is_(True))
    items = db.scalars(statement.order_by(DoctorNote.created_at.desc())).all()
    return [DoctorNoteResponse.model_validate(item) for item in items]


@router.post(
    "/doctor/patients/{patient_id}/notes",
    response_model=DoctorNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_doctor_note(
    patient_id: str, request: DoctorNoteCreate, user: CurrentUser, db: DbSession
) -> DoctorNoteResponse:
    if user.role != "doctor":
        raise HTTPException(status_code=403, detail="Doctor access required")
    require_patient_access(db, user, patient_id)
    assignment = db.get(DoctorPatient, (user.id, patient_id))
    if assignment is None or not assignment.can_add_notes:
        raise HTTPException(status_code=403, detail="Note permission is required")
    note = DoctorNote(patient_id=patient_id, doctor_user_id=user.id, **request.model_dump())
    db.add(note)
    db.commit()
    db.refresh(note)
    return DoctorNoteResponse.model_validate(note)
