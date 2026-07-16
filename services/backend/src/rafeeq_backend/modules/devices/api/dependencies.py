import hmac
from hashlib import sha256
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from rafeeq_backend.models import Device
from rafeeq_backend.modules.auth.api.dependencies import DbSession


def device_secret_hash(secret: str) -> str:
    return sha256(secret.encode("utf-8")).hexdigest()


def get_current_device(
    db: DbSession,
    device_id: Annotated[str, Header(alias="X-Device-Id")],
    device_secret: Annotated[str, Header(alias="X-Device-Secret")],
) -> Device:
    device = db.get(Device, device_id)
    supplied = device_secret_hash(device_secret)
    if device is None or not hmac.compare_digest(device.secret_hash, supplied):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device credentials",
        )
    if device.status == "disabled" or device.patient_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device is unavailable")
    return device


CurrentDevice = Annotated[Device, Depends(get_current_device)]
