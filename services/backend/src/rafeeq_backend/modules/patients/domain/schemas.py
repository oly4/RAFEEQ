from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PatientCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=200)
    date_of_birth: date | None = None
    condition_notes: str | None = Field(default=None, max_length=4000)
    preferred_language: str = "ar"
    timezone: str = "Europe/London"
    emergency_instructions: str | None = Field(default=None, max_length=2000)
    relationship_label: str = Field(default="family", max_length=100)


class PatientUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    condition_notes: str | None = Field(default=None, max_length=4000)
    preferred_language: str | None = None
    timezone: str | None = None
    emergency_instructions: str | None = Field(default=None, max_length=2000)


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    display_name: str
    date_of_birth: date | None
    condition_notes: str | None
    preferred_language: str
    timezone: str
    emergency_instructions: str | None
    created_at: datetime
    updated_at: datetime


class PatientList(BaseModel):
    items: list[PatientResponse]
    page: int = 1
    page_size: int = 20
    total: int


class DashboardSummary(BaseModel):
    patient: PatientResponse
    device_status: str
    daily_completion_percentage: int
    medication_total: int
    medication_completed: int
    medication_pending: int = 0
    routine_total: int
    routine_completed: int
    active_emergencies: int


class EmergencyContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    relationship: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)


class EmergencyContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    relationship: str
    phone: str
    email: str | None
    priority_order: int
    is_active: bool


class AlertRecipientResponse(BaseModel):
    id: str | None = None
    name: str
    relationship: str
    email: str | None = None
    phone: str | None = None
    source: str


class CareProfileUpdate(BaseModel):
    relationship_label: str | None = Field(default=None, max_length=100)
    likes: str | None = Field(default=None, max_length=1000)
    dislikes: str | None = Field(default=None, max_length=1000)
    disease_stage: str | None = Field(default=None, max_length=120)
    care_description: str | None = Field(default=None, max_length=1500)
    condition_notes: str | None = Field(default=None, max_length=4000)


class CareProfileResponse(BaseModel):
    patient_id: str
    display_name: str
    relationship_label: str | None = None
    likes: str | None = None
    dislikes: str | None = None
    disease_stage: str | None = None
    care_description: str | None = None
    condition_notes: str | None = None
    alert_recipients: list[AlertRecipientResponse] = Field(default_factory=list)
    emergency_contacts: list[EmergencyContactResponse] = Field(default_factory=list)


class VoiceCommandRequest(BaseModel):
    audio_data_url: str = Field(min_length=1, max_length=16_000_000)
    emit_event: bool = True


class VoiceCommandResponse(BaseModel):
    transcript: str = ""
    action: Literal[
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
    ]
    assistant_text: str
    audio_data_url: str | None = None
    routine_created: bool = False
    routine_title: str | None = None
    needs_confirmation: bool = False
    used_openai: bool = False
