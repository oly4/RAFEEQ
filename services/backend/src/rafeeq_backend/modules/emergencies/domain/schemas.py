from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceEventEnvelope(BaseModel):
    schema_version: Literal[1]
    event_id: UUID
    event_type: str = Field(max_length=80)
    device_id: UUID
    patient_id: UUID
    occurred_at: datetime
    sequence: int = Field(ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class DeviceEventBatch(BaseModel):
    events: list[DeviceEventEnvelope] = Field(min_length=1, max_length=100)


class IngestResult(BaseModel):
    event_id: UUID
    status: Literal["processed", "duplicate"]
    emergency_id: str | None = None


class BatchIngestResponse(BaseModel):
    items: list[IngestResult]


class EmergencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    device_id: str | None
    type: str
    severity: str
    status: str
    detected_at: datetime
    confirmed_at: datetime | None
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None
    source_event_id: str
    metadata_json: dict[str, Any]


class EmergencyList(BaseModel):
    items: list[EmergencyResponse]
    page: int = 1
    page_size: int = 20
    total: int


class ResolveRequest(BaseModel):
    resolution_note: str = Field(min_length=2, max_length=2000)


class VerificationSimulationRequest(BaseModel):
    outcome: Literal["safe", "help", "timeout"]
