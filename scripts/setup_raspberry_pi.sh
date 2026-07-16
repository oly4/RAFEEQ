#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${RAFEEQ_REPO_URL:-https://github.com/oly4/RAFEEQ.git}"
INSTALL_DIR="${RAFEEQ_INSTALL_DIR:-/opt/rafeeq}"
SERVICE_USER="${RAFEEQ_SERVICE_USER:-rafeeq}"
BACKEND_PORT="${RAFEEQ_BACKEND_PORT:-8000}"
CAMERA_INDEX="${CAMERA_INDEX:-0}"

log() {
  printf "\n\033[1;35m==> %s\033[0m\n" "$*"
}

need_sudo() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script with sudo:"
    echo "  sudo bash scripts/setup_raspberry_pi.sh"
    exit 1
  fi
}

ensure_user() {
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --create-home --shell /bin/bash "$SERVICE_USER"
  fi
}

ensure_repo() {
  if [ ! -d "$INSTALL_DIR/.git" ]; then
    rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
  else
    git -C "$INSTALL_DIR" pull --ff-only
  fi
  chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
}

ensure_python_runner() {
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_RUNNER="python3.12"
    return
  fi

  if python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PY
  then
    PYTHON_RUNNER="python3"
    return
  fi

  log "Python 3.12 was not found; installing uv-managed Python 3.12"
  if ! command -v uv >/dev/null 2>&1; then
    sudo -u "$SERVICE_USER" bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
  fi
  sudo -u "$SERVICE_USER" bash -lc '~/.local/bin/uv python install 3.12'
  PYTHON_RUNNER="sudo -u $SERVICE_USER ~/.local/bin/uv run --python 3.12 python"
}

make_venv() {
  local dir="$1"
  local extras="$2"
  log "Creating Python environment in $dir"
  if [[ "$PYTHON_RUNNER" == sudo*uv* ]]; then
    sudo -u "$SERVICE_USER" bash -lc "cd '$dir' && ~/.local/bin/uv venv --python 3.12 .venv"
    sudo -u "$SERVICE_USER" bash -lc "cd '$dir' && .venv/bin/python -m pip install -U pip"
  else
    sudo -u "$SERVICE_USER" bash -lc "cd '$dir' && $PYTHON_RUNNER -m venv .venv && .venv/bin/python -m pip install -U pip"
  fi
  sudo -u "$SERVICE_USER" bash -lc "cd '$dir' && .venv/bin/python -m pip install -e '$extras'"
}

random_secret() {
  openssl rand -hex 32
}

write_env_files() {
  log "Writing /etc/rafeeq environment files"
  mkdir -p /etc/rafeeq "$INSTALL_DIR/data"
  chmod 750 /etc/rafeeq

  local jwt_access jwt_refresh demo_caregiver demo_doctor demo_device openai_key
  jwt_access="$(random_secret)"
  jwt_refresh="$(random_secret)"
  demo_caregiver="${DEMO_CAREGIVER_PASSWORD:-Rafeeq-Test-2026!}"
  demo_doctor="${DEMO_DOCTOR_PASSWORD:-Rafeeq-Test-2026!}"
  demo_device="${DEMO_DEVICE_SECRET:-$(random_secret)}"
  openai_key="${OPENAI_API_KEY:-}"

  cat >/etc/rafeeq/backend.env <<EOF
APP_ENV=development
APP_BASE_URL=http://0.0.0.0:${BACKEND_PORT}
DATABASE_URL=postgresql+psycopg://rafeeq:rafeeq@127.0.0.1:5432/rafeeq
REDIS_URL=redis://127.0.0.1:6379/0
JWT_ACCESS_SECRET=${jwt_access}
JWT_REFRESH_SECRET=${jwt_refresh}
JWT_ACCESS_TTL_MINUTES=15
JWT_REFRESH_TTL_DAYS=30
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
CORS_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://localhost:3000,http://127.0.0.1:3000
LOG_LEVEL=INFO
DEMO_CAREGIVER_PASSWORD=${demo_caregiver}
DEMO_DOCTOR_PASSWORD=${demo_doctor}
DEMO_DEVICE_SECRET=${demo_device}
OPENAI_API_KEY=${openai_key}
OPENAI_TEXT_MODEL=gpt-5.4-nano
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy
EOF
  chmod 640 /etc/rafeeq/backend.env
  chown root:"$SERVICE_USER" /etc/rafeeq/backend.env
}

seed_and_write_robot_env() {
  log "Running migrations and demo seed"
  set -a
  # shellcheck disable=SC1091
  source /etc/rafeeq/backend.env
  set +a
  sudo -u "$SERVICE_USER" bash -lc "cd '$INSTALL_DIR/services/backend' && set -a && source /etc/rafeeq/backend.env && set +a && .venv/bin/alembic upgrade head"
  sudo -u "$SERVICE_USER" bash -lc "cd '$INSTALL_DIR' && set -a && source /etc/rafeeq/backend.env && set +a && services/backend/.venv/bin/python scripts/seed_demo_data.py"

  log "Resolving seeded patient and device IDs"
  local ids patient_id device_id
  ids="$(sudo -u "$SERVICE_USER" bash -lc "cd '$INSTALL_DIR' && set -a && source /etc/rafeeq/backend.env && set +a && services/backend/.venv/bin/python - <<'PY'
from sqlalchemy import select
from rafeeq_backend.database import SessionLocal
from rafeeq_backend.models import Device, Patient
with SessionLocal() as db:
    patient = db.scalar(select(Patient).order_by(Patient.created_at.desc()))
    device = db.scalar(select(Device).where(Device.patient_id == patient.id).order_by(Device.created_at.desc()))
    print(patient.id)
    print(device.id)
PY
")"
  patient_id="$(printf '%s\n' "$ids" | sed -n '1p')"
  device_id="$(printf '%s\n' "$ids" | sed -n '2p')"

  local pi_ip demo_device openai_key
  pi_ip="$(hostname -I | awk '{print $1}')"
  demo_device="$(grep '^DEMO_DEVICE_SECRET=' /etc/rafeeq/backend.env | cut -d= -f2-)"
  openai_key="$(grep '^OPENAI_API_KEY=' /etc/rafeeq/backend.env | cut -d= -f2-)"

  cat >/etc/rafeeq/robot.env <<EOF
RAFEEQ_DEVICE_ID=${device_id}
RAFEEQ_DEVICE_SECRET=${demo_device}
RAFEEQ_PATIENT_ID=${patient_id}
BACKEND_BASE_URL=http://127.0.0.1:${BACKEND_PORT}
LOCAL_DATABASE_PATH=${INSTALL_DIR}/data/robot.db
HARDWARE_MODE=raspberry_pi
CAMERA_INDEX=${CAMERA_INDEX}
FALL_VERIFICATION_TIMEOUT_SECONDS=10
FALL_DETECTION_COOLDOWN_SECONDS=60
VOICE_INTERACTION_PROVIDER=vosk
VOICE_REASONING_PROVIDER=openai
SPEAKER_PROVIDER=console
VOSK_MODEL_PATH=${INSTALL_DIR}/.run/models/vosk-ar
VOSK_INPUT_DEVICE=
VOSK_SAMPLE_RATE=16000
VOICE_LISTEN_SECONDS=15
OPENAI_API_KEY=${openai_key}
OPENAI_TEXT_MODEL=gpt-5.4-nano
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy
EOF
  chmod 640 /etc/rafeeq/robot.env
  chown root:"$SERVICE_USER" /etc/rafeeq/robot.env

  cat >/etc/rafeeq/summary.txt <<EOF
RAFEEQ Raspberry Pi setup complete.
Pi IP: ${pi_ip}
Backend health: http://${pi_ip}:${BACKEND_PORT}/health/ready
Flutter command on Windows:
  .\\scripts\\run_app_windows.ps1 -BackendHost ${pi_ip} -RemoteBackend

Demo family:
  caregiver@demo.rafeeq.app / ${DEMO_CAREGIVER_PASSWORD:-Rafeeq-Test-2026!}
Demo doctor:
  doctor@demo.rafeeq.app / ${DEMO_DOCTOR_PASSWORD:-Rafeeq-Test-2026!}
EOF
}

install_services() {
  log "Installing systemd services"
  install -m 0644 "$INSTALL_DIR/infra/systemd/rafeeq-backend.service" /etc/systemd/system/rafeeq-backend.service
  install -m 0644 "$INSTALL_DIR/infra/systemd/rafeeq-robot.service" /etc/systemd/system/rafeeq-robot.service
  install -m 0644 "$INSTALL_DIR/infra/systemd/rafeeq-camera.service" /etc/systemd/system/rafeeq-camera.service
  systemctl daemon-reload
  systemctl enable rafeeq-backend rafeeq-robot rafeeq-camera
  systemctl restart rafeeq-backend
  sleep 4
  systemctl restart rafeeq-robot
  systemctl restart rafeeq-camera || true
}

main() {
  need_sudo
  log "Installing OS packages"
  apt-get update
  apt-get install -y git curl ca-certificates openssl docker.io docker-compose-plugin \
    ffmpeg alsa-utils portaudio19-dev libopencv-dev python3 python3-venv python3-pip

  ensure_user
  usermod -aG docker "$SERVICE_USER" || true
  ensure_repo
  ensure_python_runner

  log "Starting Postgres, Redis, and Mosquitto"
  docker compose -f "$INSTALL_DIR/docker-compose.yml" up -d postgres redis mosquitto
  for _ in $(seq 1 40); do
    if docker compose -f "$INSTALL_DIR/docker-compose.yml" exec -T postgres pg_isready -U rafeeq >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  make_venv "$INSTALL_DIR/services/backend" "."
  make_venv "$INSTALL_DIR/edge/robot" ".[voice]"
  log "Installing vision dependencies; if this fails, camera service may need manual MediaPipe setup"
  sudo -u "$SERVICE_USER" bash -lc "cd '$INSTALL_DIR/edge/robot' && .venv/bin/python -m pip install -e '.[vision]'" || true

  write_env_files
  seed_and_write_robot_env
  install_services

  log "Done"
  cat /etc/rafeeq/summary.txt
  echo
  echo "Service checks:"
  systemctl --no-pager --full status rafeeq-backend | sed -n '1,12p' || true
  systemctl --no-pager --full status rafeeq-robot | sed -n '1,12p' || true
  systemctl --no-pager --full status rafeeq-camera | sed -n '1,12p' || true
}

main "$@"
