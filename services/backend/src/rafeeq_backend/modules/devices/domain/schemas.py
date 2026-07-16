from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str | None
    device_serial: str
    display_name: str
    status: str
    last_seen_at: datetime | None
    last_sync_at: datetime | None


class ProvisionedDevice(DeviceResponse):
    device_secret: str


class DeviceList(BaseModel):
    items: list[DeviceResponse]
    page: int = 1
    page_size: int = 20
    total: int
