from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class CameraControlStatus(BaseModel):
    enabled: bool
    active: bool
    service_name: str
    message: str | None = None


class WifiNetwork(BaseModel):
    ssid: str
    signal: int | None = None
    security: str | None = None
    active: bool = False


class RaspberryPiNetworkStatus(BaseModel):
    enabled: bool
    connected: bool
    ssid: str | None = None
    connection: str | None = None
    interface: str | None = None
    state: str | None = None
    ip_addresses: list[str] = []
    wifi_networks: list[WifiNetwork] = []
    message: str | None = None


class WifiConnectRequest(BaseModel):
    ssid: str
    password: str
    admin_pin: str


class RobotSpeechDemoRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    locale: str = Field(default="en", max_length=8)


class RobotSpeechDemoResponse(BaseModel):
    queued: bool
    assistant_text: str
    locale: str
    used_openai: bool = False
    message: str | None = None
