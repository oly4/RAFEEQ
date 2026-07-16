from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SyncSnapshot(BaseModel):
    configuration_version: str
    generated_at: datetime
    patient: dict[str, Any]
    routines: list[dict[str, Any]]
    emergency_settings: dict[str, Any]
    voice_preferences: dict[str, Any]


class SyncAckRequest(BaseModel):
    configuration_version: str = Field(min_length=1, max_length=200)


class HeartbeatRequest(BaseModel):
    software_version: str = Field(default="0.1.0", max_length=80)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class DeviceStatusResponse(BaseModel):
    status: str
    server_time: datetime
