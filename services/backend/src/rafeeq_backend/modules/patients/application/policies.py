from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from rafeeq_backend.models import CaregiverPatient, DoctorPatient, User


def can_access_patient(db: Session, user: User, patient_id: str) -> bool:
    if user.role == "admin":
        return True
    if user.role == "caregiver":
        query = select(
            exists().where(
                CaregiverPatient.caregiver_user_id == user.id,
                CaregiverPatient.patient_id == patient_id,
            )
        )
        return bool(db.scalar(query))
    if user.role == "doctor":
        query = select(
            exists().where(
                DoctorPatient.doctor_user_id == user.id,
                DoctorPatient.patient_id == patient_id,
                DoctorPatient.revoked_at.is_(None),
            )
        )
        return bool(db.scalar(query))
    return False


def require_patient_access(db: Session, user: User, patient_id: str) -> None:
    if not can_access_patient(db, user, patient_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")


def require_caregiver_access(db: Session, user: User, patient_id: str) -> None:
    if user.role != "caregiver" or not can_access_patient(db, user, patient_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Caregiver access required"
        )
