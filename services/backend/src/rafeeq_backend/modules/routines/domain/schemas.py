from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RoutineType = Literal[
    "medication",
    "meal",
    "water",
    "appointment",
    "spiritual",
    "memory_exercise",
    "conversation",
    "custom",
]


class MedicationInput(BaseModel):
    medication_name: str = Field(min_length=1, max_length=200)
    dosage_text: str = Field(min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=1000)


class RoutineCreate(BaseModel):
    type: RoutineType
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    timezone: str = "Europe/London"
    start_date: date
    end_date: date | None = None
    recurrence_rule: str = Field(default="FREQ=DAILY", max_length=500)
    scheduled_local_time: time
    requires_confirmation: bool = True
    snooze_minutes: int = Field(default=10, ge=1, le=60)
    max_snoozes: int = Field(default=2, ge=0, le=10)
    medication: MedicationInput | None = None

    @model_validator(mode="after")
    def validate_medication(self) -> "RoutineCreate":
        if self.type == "medication" and self.medication is None:
            raise ValueError("Medication details are required")
        if self.type != "medication" and self.medication is not None:
            raise ValueError("Medication details are only valid for medication routines")
        return self


class RoutineUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    scheduled_local_time: time | None = None
    medication: MedicationInput | None = None


class MedicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    medication_name: str
    dosage_text: str
    instructions: str | None


class RoutineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    type: str
    title: str
    description: str | None
    timezone: str
    start_date: date
    recurrence_rule: str
    scheduled_local_time: time
    requires_confirmation: bool
    is_active: bool
    medication: MedicationResponse | None = None


class RoutineList(BaseModel):
    items: list[RoutineResponse]
    page: int = 1
    page_size: int = 20
    total: int


class OccurrenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    routine_id: str
    patient_id: str
    scheduled_at_utc: datetime
    status: str
    completed_at: datetime | None
    confirmation_source: str | None


class OccurrenceList(BaseModel):
    items: list[OccurrenceResponse]
    page: int = 1
    page_size: int = 20
    total: int


class CompletionRequest(BaseModel):
    confirmation_source: Literal["patient_voice", "caregiver", "robot_timeout", "manual"] = (
        "caregiver"
    )
    notes: str | None = Field(default=None, max_length=1000)


class SnoozeRequest(BaseModel):
    minutes: int = Field(default=10, ge=1, le=60)
