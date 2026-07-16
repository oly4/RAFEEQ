# RAFEEQ

RAFEEQ is an Arabic-first, privacy-conscious elderly-care prototype composed of a FastAPI modular monolith, an offline-first Raspberry Pi robot application, and a Flutter caregiver/doctor app. Simulation mode is the default so development does not require physical hardware.

## Current implementation

The runnable prototype now includes rotating-token authentication, relation-authorized patient profiles, Arabic-first caregiver and doctor modes, medication reminders, offline robot SQLite/outbox behavior, device synchronization, SOS and fall verification, live emergency updates, activities, memory-support content, doctor notes, and reports. Development simulation controls make the critical paths demonstrable without Raspberry Pi hardware.

## Prerequisites

- Python 3.12+
- Docker Desktop and Docker Compose
- Flutter stable SDK (for mobile development)
- GNU Make is optional; equivalent commands may be run directly on Windows

## Run locally

```sh
cp .env.example .env
docker compose up -d
curl http://localhost:8000/health/ready
python scripts/run_robot_simulator.py
```

For Python-only development, create a virtual environment and install both editable packages:

```sh
python -m venv .venv
.venv/Scripts/python -m pip install -e "services/backend[dev]" -e "edge/robot[dev]"
.venv/Scripts/python -m pytest services/backend/tests edge/robot/tests
python scripts/verify_environment.py
```

Demo seeding requires `DEMO_CAREGIVER_PASSWORD`, `DEMO_DOCTOR_PASSWORD`, and `DEMO_DEVICE_SECRET` in the local environment. No demo passwords are stored in source control.

Mobile commands:

```sh
cd apps/mobile
flutter pub get
flutter gen-l10n
flutter test
flutter run
```

Never deploy the sample database password or anonymous local MQTT configuration. Supply production secrets out of band.

## Safari demonstration

On this workstation the app is served at `http://10.78.178.45:8080`, with its API at port `8000`. Both processes bind to the LAN interface. The iPhone must be connected to the same Wi-Fi. Rebuild with `C:\\flutter\\bin\\flutter.bat build web --no-wasm-dry-run` after UI changes.

The Flutter client uses the RAFEEQ lavender, rounded-card Apple-style presentation on every target. The family experience contains the ten reference views: role selection, family entry, home, reports, treating doctor, sent reports, emergency, routine, albums, and settings. The preview frame remains visible in Safari so the web demonstration matches the supplied mockups. Sign-in, account creation, patient data, reminders, camera access, emergency actions, reports, memories, doctor assignment, and role permissions remain connected to the backend rather than being static mock content.

Native iOS compilation and signing require macOS, Xcode, and an Apple identity. The Safari build exercises the same Flutter feature code but is not an App Store package.

### Safari camera test

Camera access requires HTTPS. The camera test is a local live preview only: audio is disabled, and no frames are recorded, saved, analyzed, or uploaded.

Generate a development certificate for the workstation's current LAN IP:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_local_https.ps1 -LanIp 10.78.178.45
```

The HTTPS Flutter build is served on port `8443`, and the TLS backend is served on port `8444`. On the Apple device, install and fully trust the generated `rafeeq-dev-ca.cer` certificate before opening the HTTPS app. Development CA keys remain under ignored `.run/tls` and must never be used in production.

## Laptop-camera fall-detection demo

The laptop demo uses the local webcam, OpenCV, MediaPipe pose landmarks, and a pinned
MIT-licensed Random Forest model trained on temporal pose features. The trained model is
downloaded once from its pinned source commit and verified with SHA-256 before loading.
Frames stay in memory and are never saved or uploaded. This remains a research prototype,
not a medical device or a reliable safety monitor. Attribution and the upstream license are
recorded in `edge/robot/THIRD_PARTY_NOTICES.md`.

```powershell
C:\Python313\python.exe -m venv edge\robot\.venv --system-site-packages
edge\robot\.venv\Scripts\python.exe -m pip install -e "edge\robot[dev,vision]"
edge\robot\.venv\Scripts\rafeeq-fall-demo.exe
```

Stand far enough from the laptop for your full body to remain visible and wait until the preview
says `ML READY`. To test, **do not perform a real fall**: lower yourself safely sideways onto a
sofa or exercise mat. During verification press `S` for safe, `H` for help, or `T` for timeout.
Press `F` only to test the verification pipeline manually and `Q` to quit. Use
`rafeeq-fall-demo --detector heuristic` only when comparing the earlier rule-based fallback.

The demo always records possible-fall and verification events in its local SQLite outbox. To
synchronize verified `help` or `timeout` outcomes to the caregiver app, configure the paired
device values `RAFEEQ_DEVICE_ID`, `RAFEEQ_DEVICE_SECRET`, `RAFEEQ_PATIENT_ID`, and
`BACKEND_BASE_URL` in `.env.robot`. Without those credentials the safety-critical local prompt,
timeout, and event log continue to work offline.

## AI voice preparation

RAFEEQ is prepared for an OpenAI Realtime voice layer with `gpt-realtime-2.1-mini`.
Do not place the OpenAI API key in Flutter or source control. Store it in `.env.robot`
or a deployment secret manager:

```env
VOICE_INTERACTION_PROVIDER=simulation
OPENAI_API_KEY=
OPENAI_REALTIME_MODEL=gpt-realtime-2.1-mini
VOICE_MAX_SESSION_SECONDS=120
VOICE_REMINDER_SNOOZE_MINUTES=10
VOICE_UPLOAD_AUDIO=false
```

The current implementation includes a safe simulated voice router. In the robot console,
use `voice yes I took it`, `voice remind me later`, `voice no`, or `voice help` after a
reminder is active. See `docs/ai-voice.md` for the subscription/setup checklist.
