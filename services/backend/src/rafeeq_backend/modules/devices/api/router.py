import hmac
import json
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from rafeeq_backend.config import get_settings
from rafeeq_backend.models import AuditLog, Device, utc_now
from rafeeq_backend.modules.auth.api.dependencies import CurrentUser, DbSession
from rafeeq_backend.modules.devices.api.dependencies import device_secret_hash
from rafeeq_backend.modules.devices.domain.schemas import (
    CameraControlStatus,
    DeviceList,
    DeviceResponse,
    ProvisionedDevice,
    RaspberryPiNetworkStatus,
    RobotSpeechDemoRequest,
    RobotSpeechDemoResponse,
    SpeakerVolumeRequest,
    SpeakerVolumeStatus,
    WifiConnectRequest,
)
from rafeeq_backend.modules.patients.application.policies import (
    require_caregiver_access,
    require_patient_access,
)

router = APIRouter(tags=["devices"])
ROBOT_SPEECH_COMMAND_DIR = Path("/tmp/rafeeq-runtime/voice-commands")


def _camera_status_message(active: bool) -> str:
    if active:
        return "Fall detection camera is running"
    return "Fall detection camera is stopped"


def _camera_service_name() -> str:
    service_name = get_settings().camera_service_name.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", service_name):
        raise HTTPException(
            status_code=500, detail="Invalid camera service configuration"
        )
    return service_name


def _camera_is_active(service_name: str) -> bool:
    result = subprocess.run(
        ["/usr/bin/systemctl", "is-active", "--quiet", service_name],
        check=False,
        timeout=5,
    )
    return result.returncode == 0


def _run_camera_control(action: str, service_name: str) -> None:
    if action not in {"start", "stop"}:
        raise HTTPException(status_code=500, detail="Invalid camera control action")
    try:
        result = subprocess.run(
            ["sudo", "-n", "/usr/bin/systemctl", action, service_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504, detail="Camera service control timed out"
        ) from exc
    if result.returncode != 0:
        detail = (
            result.stderr or result.stdout or "Camera service control failed"
        ).strip()
        raise HTTPException(status_code=503, detail=detail)
    expected_active = action == "start"
    deadline = 20
    for _ in range(deadline):
        if _camera_is_active(service_name) == expected_active:
            return
        time.sleep(1)
    state = "running" if expected_active else "stopped"
    raise HTTPException(
        status_code=504,
        detail=f"Camera service did not report {state} after {deadline} seconds",
    )


def _camera_control_response() -> CameraControlStatus:
    settings = get_settings()
    service_name = _camera_service_name()
    active = False
    if settings.camera_control_enabled:
        active = _camera_is_active(service_name)
    return CameraControlStatus(
        enabled=settings.camera_control_enabled,
        active=active,
        service_name=service_name,
        message=_camera_status_message(active),
    )


def _require_camera_control_enabled() -> None:
    if not get_settings().camera_control_enabled:
        raise HTTPException(status_code=404, detail="Camera control is not enabled")


def _require_network_control_enabled() -> None:
    if not get_settings().network_control_enabled:
        raise HTTPException(status_code=404, detail="Network control is not enabled")


def _require_speaker_control_enabled() -> None:
    if not get_settings().speaker_control_enabled:
        raise HTTPException(status_code=404, detail="Speaker control is not enabled")


def _network_helper_path() -> str:
    helper = get_settings().network_control_helper.strip()
    if not helper.startswith("/opt/rafeeq/") or not helper.endswith(".py"):
        raise HTTPException(status_code=500, detail="Invalid network helper configuration")
    return helper


def _speaker_helper_path() -> str:
    helper = get_settings().speaker_control_helper.strip()
    if not helper.startswith("/opt/rafeeq/") or not helper.endswith(".py"):
        raise HTTPException(status_code=500, detail="Invalid speaker helper configuration")
    return helper


def _run_network_helper(
    action: str,
    payload: dict[str, str] | None = None,
) -> RaspberryPiNetworkStatus:
    _require_network_control_enabled()
    helper = _network_helper_path()
    command = ["sudo", "-n", helper, action]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            input=json.dumps(payload or {}),
            text=True,
            timeout=50,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Network command timed out") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Network command failed").strip()
        if "Traceback (most recent call last)" in detail:
            last_line = detail.splitlines()[-1].strip()
            detail = f"Network command failed: {last_line}"
        raise HTTPException(status_code=503, detail=detail)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="Invalid network helper output") from exc
    return RaspberryPiNetworkStatus(
        enabled=True,
        message=data.get("message"),
        **{key: value for key, value in data.items() if key != "message"},
    )


def _run_speaker_helper(
    action: str,
    payload: dict[str, int] | None = None,
) -> SpeakerVolumeStatus:
    _require_speaker_control_enabled()
    if action not in {"status", "set", "test"}:
        raise HTTPException(status_code=500, detail="Invalid speaker command")
    helper = _speaker_helper_path()
    command = ["sudo", "-n", helper, action]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            input=json.dumps(payload or {}),
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Speaker command timed out") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Speaker command failed").strip()
        raise HTTPException(status_code=503, detail=detail)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=503, detail="Invalid speaker helper output") from exc
    return SpeakerVolumeStatus(**data)


def _require_network_admin_pin(admin_pin: str) -> None:
    configured = get_settings().network_control_admin_pin
    expected = configured.get_secret_value() if configured is not None else ""
    if not expected or not hmac.compare_digest(admin_pin, expected):
        raise HTTPException(status_code=403, detail="Invalid Raspberry Pi admin PIN")


def _openai_echo_speech_text(text: str) -> tuple[str, bool]:
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key:
        return text, False
    payload = {
        "model": settings.openai_text_model,
        "instructions": (
            "You are RAFEEQ's prototype speech dispatcher. Return exactly the user "
            "provided message as plain text. Do not translate, rewrite, add, or remove words."
        ),
        "input": text,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return text, False
    echoed = _response_text(data).strip()
    return echoed or text, bool(echoed)


def _response_text(data: dict[str, object]) -> str:
    if isinstance(data.get("output_text"), str):
        return str(data["output_text"])
    chunks: list[str] = []
    for output in data.get("output", []):  # type: ignore[union-attr]
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(str(content["text"]))
    return "\n".join(chunks)


def _queue_robot_speech(text: str, locale: str) -> None:
    ROBOT_SPEECH_COMMAND_DIR.mkdir(parents=True, exist_ok=True)
    command_path = ROBOT_SPEECH_COMMAND_DIR / f"{uuid4()}.json"
    command_path.write_text(
        json.dumps({"text": text, "locale": locale}, ensure_ascii=False),
        encoding="utf-8",
    )


@router.get(
    "/devices/camera/fall-detection",
    response_model=CameraControlStatus,
)
def get_fall_detection_camera_status() -> CameraControlStatus:
    return _camera_control_response()


@router.post(
    "/devices/camera/fall-detection/start",
    response_model=CameraControlStatus,
)
def start_fall_detection_camera() -> CameraControlStatus:
    _require_camera_control_enabled()
    service_name = _camera_service_name()
    _run_camera_control("start", service_name)
    return _camera_control_response()


@router.post(
    "/devices/camera/fall-detection/stop",
    response_model=CameraControlStatus,
)
def stop_fall_detection_camera() -> CameraControlStatus:
    _require_camera_control_enabled()
    service_name = _camera_service_name()
    _run_camera_control("stop", service_name)
    return _camera_control_response()


@router.get(
    "/devices/raspberry-pi/network",
    response_model=RaspberryPiNetworkStatus,
)
def get_raspberry_pi_network_status() -> RaspberryPiNetworkStatus:
    return _run_network_helper("status")


@router.get(
    "/devices/raspberry-pi/network/scan",
    response_model=RaspberryPiNetworkStatus,
)
def scan_raspberry_pi_wifi() -> RaspberryPiNetworkStatus:
    return _run_network_helper("scan")


@router.post(
    "/devices/raspberry-pi/network/connect",
    response_model=RaspberryPiNetworkStatus,
)
def connect_raspberry_pi_wifi(request: WifiConnectRequest) -> RaspberryPiNetworkStatus:
    _require_network_admin_pin(request.admin_pin)
    return _run_network_helper(
        "connect",
        {"ssid": request.ssid, "password": request.password},
    )


@router.get(
    "/devices/raspberry-pi/speaker",
    response_model=SpeakerVolumeStatus,
)
def get_raspberry_pi_speaker_volume() -> SpeakerVolumeStatus:
    return _run_speaker_helper("status")


@router.post(
    "/devices/raspberry-pi/speaker",
    response_model=SpeakerVolumeStatus,
)
def set_raspberry_pi_speaker_volume(
    request: SpeakerVolumeRequest,
) -> SpeakerVolumeStatus:
    return _run_speaker_helper(
        "set",
        {"volume_percent": request.volume_percent},
    )


@router.post(
    "/devices/raspberry-pi/speaker/test",
    response_model=SpeakerVolumeStatus,
)
def test_raspberry_pi_speaker() -> SpeakerVolumeStatus:
    return _run_speaker_helper("test")


@router.post(
    "/devices/raspberry-pi/demo-speech",
    response_model=RobotSpeechDemoResponse,
)
def send_raspberry_pi_demo_speech(
    request: RobotSpeechDemoRequest,
) -> RobotSpeechDemoResponse:
    locale = "ar" if request.locale.lower().startswith("ar") else "en"
    assistant_text, used_openai = _openai_echo_speech_text(request.text.strip())
    _queue_robot_speech(assistant_text, locale)
    return RobotSpeechDemoResponse(
        queued=True,
        assistant_text=assistant_text,
        locale=locale,
        used_openai=used_openai,
        message="Speech queued for RAFEEQ robot.",
    )


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
