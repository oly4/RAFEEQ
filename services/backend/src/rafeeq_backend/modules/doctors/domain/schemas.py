from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class DoctorInviteRequest(BaseModel):
    email: EmailStr


class DoctorAssignmentResponse(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    can_view_reports: bool
    can_add_notes: bool


class DoctorNoteCreate(BaseModel):
    text: str = Field(min_length=2, max_length=5000)
    is_shared_with_caregiver: bool = True
    follow_up_at: datetime | None = None


class DoctorNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    doctor_user_id: str
    text: str
    is_shared_with_caregiver: bool
    follow_up_at: datetime | None
    created_at: datetime
    updated_at: datetime
