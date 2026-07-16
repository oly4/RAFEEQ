import secrets

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from rafeeq_backend.config import get_settings
from rafeeq_backend.models import AuditLog, Device, utc_now
from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.devices.api.dependencies import device_secret_hash
from rafeeq_backend.modules.devices.domain.schemas import (
    DeviceList,
    DeviceResponse,
    ProvisionedDevice,
)
from rafeeq_backend.modules.patients.application.policies import (
    require_caregiver_access,
    require_patient_access,
)

router = APIRouter(tags=["devices"])


@router.get("/patients/{patient_id}/devices", response_model=DeviceList)
def list_devices(patient_id: str, user: CurrentUser, db: DbSession) -> DeviceList:
    require_patient_access(db, user, patient_id)
    items = list(db.scalars(select(Device).where(Device.patient_id == patient_id)).all())
    return DeviceList(
        items=[DeviceResponse.model_validate(item) for item in items], total=len(items)
    )


@router.post(
    "/patients/{patient_id}/devices/simulated",
    response_model=ProvisionedDevice,
    status_code=status.HTTP_201_CREATED,
)
def provision_simulated_device(
    patient_id: str, user: CurrentUser, db: DbSession
) -> ProvisionedDevice:
    if get_settings().app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")
    require_caregiver_access(db, user, patient_id)
    existing = db.scalar(select(Device).where(Device.patient_id == patient_id))
    if existing:
        raise HTTPException(status_code=409, detail="A device is already paired")
    secret = secrets.token_urlsafe(48)
    device = Device(
        patient_id=patient_id,
        device_serial=f"SIM-{secrets.token_hex(6).upper()}",
        display_name="RAFEEQ Simulator",
        secret_hash=device_secret_hash(secret),
        status="online",
        paired_at=utc_now(),
        last_seen_at=utc_now(),
    )
    db.add(device)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="device.simulator_provisioned",
            entity_type="device",
            entity_id=device.id,
            metadata_json={"patient_id": patient_id},
        )
    )
    db.commit()
    db.refresh(device)
    return ProvisionedDevice(
        **DeviceResponse.model_validate(device).model_dump(), device_secret=secret
    )
