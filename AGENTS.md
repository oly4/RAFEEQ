Exit code: 0
Wall time: 0.5 seconds
Total output lines: 2678
Output:
# RAFEEQ — Codex Build Specification

> **Purpose:** This file is the single implementation guide for building the RAFEEQ prototype.  
> **Recommended repository name:** `rafeeq`  
> **Recommended location:** place this file at the repository root and rename it to `AGENTS.md` if needed.  
> **Primary product language:** Arabic, right-to-left (RTL). English is a secondary locale.  
> **Project type:** AI-assisted elderly-care system consisting of a Raspberry Pi robot, a caregiver/doctor mobile app, and a cloud backend.

---

## 0. Instructions for Codex

Codex must treat this document as the source of truth for architecture, scope, naming, workflows, and acceptance criteria.

### Required working rules

1. Build the project incrementally in the implementation order defined in this file.
2. Keep the system runnable after every phase.
3. Do not replace the selected architecture with microservices.
4. Do not make the mobile app communicate directly with the database or hardware.
5. Do not let the fall-detection model directly send emergency notifications. It must create a detection event that is processed by the emergency policy.
6. All critical robot behavior must work without internet:
   - SOS button handling
   - fall-event verification
   - local reminders
   - local voice warnings
   - local event logging
7. Store all server timestamps in UTC. Convert to the user’s local timezone only in clients.
8. Use UUIDs for public entity IDs and event IDs.
9. Use migrations for all database changes.
10. Add automated tests for every business-critical feature.
11. Build hardware adapters and simulation adapters so the system can run on a normal development computer without a Raspberry Pi.
12. Never store passwords, API keys, tokens, or encryption secrets in source control.
13. Do not upload continuous camera video or microphone audio by default.
14. Do not implement diagnosis, medication changes, or clinical decision-making. RAFEEQ is a monitoring, reminder, communication, and escalation prototype.
15. When a requirement is unclear, prefer the safest minimal implementation and document the assumption in `docs/assumptions.md`.

### Source-of-truth priority

When implementation details conflict, use this order:

1. This specification
2. Automated tests and database migrations
3. API/OpenAPI contracts
4. Project documentation
5. UI mockups
6. Developer assumptions

---

# 1. Product Summary

RAFEEQ is an AI-powered smart health-monitoring and assistance system for elderly people, especially people living alone or living with Alzheimer’s disease or memory impairment.

The system has three connected parts:

1. **RAFEEQ Robot**
   - Runs on a Raspberry Pi.
   - Uses a camera for fall or unusual-event detection.
   - Uses a microphone and speaker for voice interaction.
   - Uses an SOS button for immediate help requests.
   - Uses a servo motor to rotate the head or camera.
   - Runs reminders locally.
   - Stores events locally when offline.
   - Synchronizes with the backend when online.

2. **RAFEEQ Mobile Application**
   - Caregiver/family mode.
   - Doctor mode.
   - Patient dashboard.
   - Daily routines and medication reminders.
   - Memory-support content.
   - Activities.
   - Emergency alerts and emergency history.
   - Medical/activity reports.
   - Doctor profile, notes, appointments, and report sharing.
   - Settings, notification preferences, privacy, language, and accessibility.

3. **RAFEEQ Backend**
   - Authentication and role-based access.
   - Patient, caregiver, doctor, and device management.
   - Routines, medication schedules, activities, and memories.
   - Emergency-event lifecycle.
   - Notifications.
   - Device synchronization.
   - Reports and audit logs.
   - REST API, WebSocket updates, and MQTT integration.

---

# 2. Product Goals and Non-Goals

## 2.1 Goals

The MVP must:

- Help caregivers monitor one or more elderly patients.
- Help patients follow routines and medication reminders.
- Allow a patient to request help using the physical SOS button.
- Detect possible falls locally and verify them before escalation.
- Notify caregivers quickly when a confirmed emergency occurs.
- Continue core robot behavior during internet outages.
- Give doctors a read-only overview of assigned patients and their reports.
- Support Arabic RTL layouts and accessible interaction.
- Produce an end-to-end demonstration using real or simulated robot hardware.

## 2.2 Non-goals for the MVP

Do not build these in the first implementation:

- Medical diagnosis.
- Automatic medication dosage changes.
- Hospital or national EHR integration.
- Insurance integration.
- Continuous cloud video surveillance.
- Continuous cloud audio recording.
- Autonomous movement around the home.
- Multi-robot fleet management beyond basic device registration.
- Advanced large-language-model conversation that can make medical claims.
- Full telemedicine.
- Production certification as a medical device.

These may be documented as future work but must not block the MVP.

---

# 3. Users, Roles, and Permissions

## 3.1 Patient

The patient mainly interacts with the robot.

Allowed actions:

- Hear reminders.
- Confirm, snooze, or decline reminders by voice or button.
- Ask simple approved questions.
- Hear daily schedule information.
- Press the SOS button.
- Respond to fall-verification prompts.
- Participate in configured memory and activity exercises.

The patient does not need a normal mobile login in the MVP.

## 3.2 Caregiver / Family Member

Allowed actions:

- Create and manage a patient profile.
- Pair a robot device.
- View the caregiver dashboard.
- Create and edit routines.
- Create and edit medication schedules.
- Add activities and memory content.
- View adherence and activity reports.
- Receive emergency notifications.
- Acknowledge and resolve alerts.
- Manage emergency contacts.
- Manage notification preferences.
- Assign or invite a doctor.
- View device connection and synchronization status.

## 3.3 Doctor

Allowed actions:

- View assigned patients only.
- View patient summary and trends.
- View medication-adherence and activity reports.
- View emergency history.
- Add notes.
- Mark follow-up recommendations.
- Manage appointments or follow-up dates.
- Export/share a report where permitted.

Doctor mode must not allow editing caregiver-owned schedules unless explicitly granted later.

## 3.4 System Administrator

This is an internal maintenance role, not a primary UI in the MVP.

Allowed actions:

- Disable compromised accounts.
- Inspect device registration.
- View operational logs without exposing unnecessary patient content.
- Manage application-level configuration.

---

# 4. Core User Journeys

## 4.1 Caregiver onboarding and device pairing

1. Caregiver creates an account.
2. Caregiver verifies email or phone.
3. Caregiver creates a patient profile.
4. Caregiver enters emergency contacts.
5. Robot displays or speaks a temporary pairing code.
6. Caregiver enters the pairing code in the app.
7. Backend links the robot to the patient.
8. Robot downloads the patient’s active schedule and preferences.
9. Dashboard displays the robot as online and synchronized.

## 4.2 Create a medication reminder

1. Caregiver opens the patient’s daily routine.
2. Caregiver creates a medication item:
   - medication name
   - dosage text
   - time
   - repeat schedule
   - instructions
   - confirmation requirement
3. Backend validates and saves the schedule.
4. Backend publishes a synchronization command.
5. Robot receives the updated schedule.
6. Robot stores it in local SQLite.
7. At the scheduled time, the robot speaks the reminder.
8. Patient confirms, snoozes, or does not respond.
9. Robot logs the result.
10. Result synchronizes to the backend.
11. Dashboard and reports update.

## 4.3 SOS emergency

1. Patient presses the physical SOS button.
2. Robot immediately:
   - creates a local event
   - plays a calm confirmation message
   - marks the event as confirmed
   - attempts to publish the event
3. Backend receives the event idempotently.
4. Backend creates an emergency record.
5. Caregivers receive push and live in-app notifications.
6. A caregiver acknowledges the emergency.
7. The system records who acknowledged it and when.
8. The emergency is later resolved with an optional resolution note.

## 4.4 Possible fall

1. Camera pipeline identifies a possible fall.
2. Fall detector creates `PossibleFallDetected`.
3. Emergency manager enters `VERIFYING`.
4. Robot asks: “Are you okay?”
5. Verification window runs for a configurable duration.
6. Outcomes:
   - Patient confirms they are okay → event becomes `FALSE_ALARM`.
   - Patient requests help → event becomes `CONFIRMED`.
   - No response → event becomes `CONFIRMED_BY_TIMEOUT`.
7. Confirmed events notify caregivers.
8. All state changes are logged.

## 4.5 Doctor review

1. Doctor signs in.
2. Doctor selects an assigned patient.
3. Doctor views:
   - patient summary
   - medication adherence
   - routine completion
   - activity engagement
   - emergency-event history
4. Doctor adds a note or follow-up date.
5. Caregiver can view the note if sharing is enabled.

---

# 5. Required Architecture

Use an **Edge–Cloud Modular Monolith with Event-Driven Communication**.

```text
┌────────────────────────────────────────────┐
│ RAFEEQ Robot / Raspberry Pi                │
│                                            │
│ Camera, microphone, speaker, SOS, servo    │
│ Local event bus                            │
│ Reminder scheduler                         │
│ Fall detector                              │
│ Emergency state machine                    │
│ Voice interaction                          │
│ SQLite                                     │
│ Outbox / synchronization client            │
└─────────────────────┬──────────────────────┘
                      │ MQTT + HTTPS
                      │
┌─────────────────────▼──────────────────────┐
│ Backend Modular Monolith                   │
│                                            │
│ Auth, patients, routines, medication       │
│ memories, activities, emergencies          │
│ notifications, reports, devices, audit     │
│ PostgreSQL + Redis                         │
└─────────────────────┬──────────────────────┘
                      │ REST + WebSocket
                      │
┌─────────────────────▼──────────────────────┐
│ Flutter Mobile App                         │
│ Caregiver mode + Doctor mode               │
│ Offline cache + push notifications         │
└────────────────────────────────────────────┘
```

## 5.1 Why not microservices

The team and product are at prototype/MVP stage. Microservices would create unnecessary deployment, debugging, security, and data-consistency complexity. Keep one backend deployment with strict internal module boundaries.

## 5.2 Backend module boundaries

Required modules:

- `auth`
- `users`
- `patients`
- `caregivers`
- `doctors`
- `devices`
- `routines`
- `medications`
- `activities`
- `memories`
- `emergencies`
- `notifications`
- `reports`
- `synchronization`
- `audit`

Each backend module should use this internal structure:

```text
module_name/
├── domain/
├── application/
├── infrastructure/
├── api/
└── tests/
```

Do not import another module’s infrastructure implementation directly. Cross-module communication must use application services, domain events, or declared interfaces.

---

# 6. Selected Technology Stack

These are implementation decisions, not suggestions.

## 6.1 Mobile

- Flutter
- Dart
- Riverpod for state management and dependency injection
- GoRouter for navigation
- Dio for HTTP
- WebSocket client for live events
- Firebase Cloud Messaging for push notifications
- Drift for offline structured storage
- Freezed and `json_serializable` for immutable models and serialization
- Secure storage for tokens
- Localization using ARB files
- Arabic RTL as the primary layout mode

## 6.2 Backend

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Redis for live-event coordination, rate limiting, and lightweight caching
- Paho MQTT or an equivalent maintained MQTT client
- WebSocket endpoints
- JWT access tokens plus rotating refresh tokens
- Pytest
- Ruff
- MyPy
- Docker

## 6.3 Robot / Edge

- Python 3.12+
- OpenCV
- MediaPipe, TensorFlow Lite, or a replaceable pose-estimation implementation
- Pydantic
- SQLite
- SQLAlchemy or SQLModel for local persistence
- APScheduler for reminders
- Paho MQTT
- Systemd service definitions
- Pytest
- Hardware abstraction interfaces

## 6.4 Infrastructure

- Docker Compose for local development and initial deployment
- Nginx or Caddy as reverse proxy
- PostgreSQL
- Redis
- Mosquitto MQTT broker
- Backend container
- Optional MinIO/S3-compatible object storage for approved media
- FCM credentials supplied only through environment secrets

---

# 7. Monorepo Layout

Create this structure:

```text
rafeeq/
├── AGENTS.md
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── apps/
│   └── mobile/
├── services/
│   └── backend/
├── edge/
│   └── robot/
├── packages/
│   └── contracts/
├── infra/
│   ├── nginx/
│   ├── mosquitto/
│   └── systemd/
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── mqtt.md
│   ├── security.md
│   ├── assumptions.md
│   └── demo-script.md
└── scripts/
    ├── seed_demo_data.py
    ├── run_robot_simulator.py
    └── verify_environment.py
```

## 7.1 Shared contracts

`packages/contracts` must contain:

- JSON Schema definitions for MQTT events.
- Example payloads.
- API error envelope.
- Enumerations shared across components.
- Versioned event names.

The backend remains the source of truth for the REST OpenAPI schema. Generate client models where practical; do not manually duplicate contracts without tests.

---

# 8. Mobile App Navigation and Screens

The mobile app must be Arabic-first and RTL.

## 8.1 App-level navigation

Unauthenticated:

```text
Splash
→ Welcome
→ Login
→ Create Account
→ Verification
```

Authenticated caregiver:

```text
Dashboard
├── Routine
├── Activities
├── Memories
├── Reports
├── Emergencies
├── Doctor
└── Settings
```

Authenticated doctor:

```text
Doctor Dashboard
├── Assigned Patients
├── Patient Summary
├── Medical Reports
├── Emergency History
├── Notes
└── Appointments
```

Use a role switch only when the authenticated user has both caregiver and doctor permissions. Never expose a visual role switch that grants permissions the account does not have.

## 8.2 Welcome screen

Required elements:

- RAFEEQ logo/robot illustration.
- Product name.
- Arabic subtitle describing elderly and Alzheimer’s care.
- Primary button: Login.
- Secondary button: Create account.
- Terms of service and privacy links.
- Language switch.

## 8.3 Caregiver dashboard

Required elements:

- Current patient card.
- Patient connection status.
- Robot connection and synchronization status.
- Emergency indicator.
- Daily completion percentage.
- Summary cards:
  - medication
  - memory exercises
  - routine/tasks
- Latest report shortcut.
- Doctor shortcut.
- Latest alert card.
- Quick actions:
  - add reminder
  - call patient/contact
  - open memories
  - open emergency history
- Bottom navigation.

Dashboard data must come from one aggregated endpoint to reduce round trips.

## 8.4 Reports overview

Required elements:

- Day/week/month filter.
- Selected date range.
- Overall completion percentage.
- Medication adherence.
- Memory exercises completed.
- Reading or spiritual activities completed.
- Conversation or interaction count.
- Empty state.
- Loading state.
- Error state.
- Export/share action for authorized roles.

## 8.5 Doctor profile

Required elements:

- Doctor identity and specialty text.
- Contact action.
- Request consultation action.
- Send latest report action.
- Latest shared report.
- Doctor notes.
- Upcoming appointments/follow-ups.

## 8.6 Emergency alert screen

Required elements:

- Large emergency status card.
- Event type.
- Event time.
- Patient name.
- Verification status.
- Device status.
- Primary emergency action.
- Call caregiver/contact action.
- Optional video-call placeholder, disabled unless implemented.
- Acknowledge action.
- Resolve action.
- Emergency-event history list.

Do not use color alone to communicate severity. Include icon and text.

## 8.7 Daily routine screen

Required elements:

- Date selector.
- Chronological items.
- Item time.
- Item type.
- Completion state.
- Confirmation source:
  - patient voice
  - caregiver
  - robot timeout
  - manual
- Add activity action.
- Edit and disable actions for caregivers.
- Read-only view for doctors unless granted permission.

Supported routine item types:

- medication
- meal
- water
- appointment
- prayer/spiritual activity
- memory exercise
- conversation
- custom activity

## 8.8 Activities screen

Required activity cards:

- Recognize photos.
- Complete a poem or familiar phrase.
- Calm music.
- Friendly conversation.
- Quran/reading activity.
- Memory exercise.
- Custom activity.

Each activity must have:

- title
- description
- activity type
- duration estimate
- instructions
- enabled/disabled state
- completion log

## 8.9 Memory support screen

Required tabs:

- Photos
- Videos
- Audio

Required categories:

- Family
- Friends
- Events
- New memories
- Custom categories

Each memory item must support:

- title
- description
- category
- media type
- optional date
- people labels entered by caregiver
- optional spoken prompt
- privacy visibility
- created by
- created time

Do not implement automatic face recognition in the MVP. Keep manually entered people labels. If face recognition is added later, it must require explicit consent and local processing by default.

## 8.10 Settings

Required sections:

- Patient profile.
- Caregivers and emergency contacts.
- Patient condition notes.
- Assigned doctor.
- Notification settings.
- Reminder settings.
- Accessibility.
- Language.
- Privacy and data controls.
- Device management.
- Logout.

Accessibility settings:

- text-size scale
- high contrast
- reduced motion
- voice volume
- speech speed
- reminder repetition count

## 8.11 Doctor dashboard

Required elements:

- Assigned-patient selector.
- Patient status summary.
- Medication adherence.
- Routine completion.
- Memory activity completion.
- Emergency-event count.
- Weekly activity trend.
- View full report.
- Request consultation/follow-up.
- Add note.

Health-summary percentages in the UI must be clearly labeled as adherence/activity indicators unless real validated medical sensors are added.

## 8.12 Medical reports

Required elements:

- Daily/weekly/monthly filter.
- Date range.
- Medication-adherence chart.
- Routine-completion chart.
- Memory-activity chart.
- Emergency-event summary.
- Doctor notes.
- Export to a shareable PDF in a later phase.
- In the first MVP, a printable HTML/report view is acceptable.

## 8.13 Emergency history

Required event types:

- SOS pressed.
- Possible…4712 tokens truncated…rrences or otherwise guarantee consistent execution.

---

# 19. Voice Interaction

MVP voice interaction is command-oriented, not unrestricted medical conversation.

Supported intents:

```text
confirm_reminder
snooze_reminder
decline_reminder
confirm_safe
request_help
ask_current_time
ask_today_schedule
start_memory_activity
repeat_message
stop_speaking
```

Requirements:

- Arabic first.
- Short prompts.
- Fallback to button or timeout.
- Log intent and confidence, not raw audio by default.
- Never provide diagnosis or medication advice.
- Medical questions must return a safe response such as:
  “Please contact your caregiver or doctor.”
- Provide a simulated text-input voice adapter for development.
- Speech-to-text and text-to-speech providers must be replaceable.

---

# 20. Offline-First Synchronization

The robot must use an outbox pattern.

## 20.1 Outgoing robot events

```text
Create domain event
→ save local event
→ save outbox record in same local transaction
→ publish through MQTT/HTTPS
→ receive acknowledgment
→ mark outbox record synced
```

Retry with exponential backoff and jitter.

## 20.2 Incoming configuration

Backend snapshot includes:

- patient profile subset
- active routines
- medication details
- activities
- approved memory prompts/metadata
- emergency settings
- voice preferences
- device configuration version

Robot acknowledges the configuration version after applying it.

## 20.3 Conflict rules

- Backend is authoritative for caregiver-created schedules and settings.
- Robot is authoritative for locally observed event timestamps and completion records.
- Use version numbers or `updated_at` checks for mutable records.
- Never silently overwrite conflicting caregiver edits.
- Duplicate events are ignored by event ID.
- Offline events preserve original `occurred_at`.

---

# 21. Mobile App Architecture

Use feature-first Clean Architecture with Riverpod.

```text
apps/mobile/lib/
├── app/
│   ├── app.dart
│   ├── router.dart
│   └── bootstrap.dart
├── core/
│   ├── auth/
│   ├── networking/
│   ├── storage/
│   ├── localization/
│   ├── design_system/
│   ├── errors/
│   └── widgets/
└── features/
    ├── onboarding/
    ├── dashboard/
    ├── patients/
    ├── devices/
    ├── routines/
    ├── activities/
    ├── memories/
    ├── emergencies/
    ├── reports/
    ├── doctor/
    ├── notifications/
    └── settings/
```

Each feature:

```text
feature/
├── data/
│   ├── data_sources/
│   ├── dto/
│   └── repositories/
├── domain/
│   ├── entities/
│   ├── repositories/
│   └── use_cases/
└── presentation/
    ├── controllers/
    ├── screens/
    └── widgets/
```

Flow:

```text
Screen
→ Riverpod controller/view model
→ use case
→ repository interface
→ remote/local data source
```

Do not call Dio directly from widgets.

## 21.1 Mobile offline behavior

Cache:

- current patient summary
- current-day routine
- last report summary
- emergency history
- notification list
- device status

Offline caregiver actions that may queue:

- mark notification read
- add non-urgent note
- routine completion correction

Do not queue high-risk operations silently, such as resolving an emergency, unless the UI clearly shows pending synchronization.

---

# 22. Backend Internal Patterns

Use:

- Repository pattern for persistence.
- Application service/use-case pattern.
- Domain events for cross-module reactions.
- Unit of Work for transactional operations.
- Strategy pattern for replaceable notification and detection behavior.
- Adapter pattern for external services.
- Outbox pattern for reliable notifications and MQTT publishing.
- State pattern or explicit transition service for emergencies.

Example emergency use case:

```text
IngestDeviceEvent
→ validate device ownership
→ deduplicate source event
→ store DeviceEvent
→ create/update EmergencyEvent
→ store state transition
→ store NotificationOutbox messages
→ commit transaction
→ async worker sends notifications
```

---

# 23. Notifications

Required channels:

- In-app live update through WebSocket.
- Push through Firebase Cloud Messaging.

Optional later:

- SMS.
- Email.

Notification priority:

```text
Critical:
- SOS
- confirmed fall
- unacknowledged emergency escalation

Warning:
- missed medication
- repeated non-response
- device offline

Informational:
- routine completed
- report ready
- device synchronized
```

Rules:

- Critical alerts bypass normal quiet-hour suppression.
- Respect user preferences for non-critical alerts.
- Deduplicate notifications.
- Record delivery attempts.
- Retry transient failures.
- Do not expose sensitive medical details in lock-screen push text by default.
- Use a generic push message and load details after authenticated app open.

---

# 24. WebSocket Events

Authenticated app clients subscribe by authorized patient.

Event envelope:

```json
{
  "type": "emergency.updated",
  "version": 1,
  "patient_id": "uuid",
  "occurred_at": "2026-07-10T14:22:10Z",
  "data": {}
}
```

Required event types:

```text
device.status_changed
device.sync_completed
routine.occurrence_updated
emergency.created
emergency.updated
notification.created
report.summary_updated
doctor.note_created
```

Always re-check authorization at connection and subscription time.

---

# 25. Reporting Rules

Report metrics:

- routine completion rate
- medication adherence rate
- missed medication count
- memory activities completed
- total activity sessions
- conversation interactions
- emergency counts by type
- average emergency acknowledgment time
- device online percentage

Definitions must be explicit.

Example medication adherence:

```text
completed medication occurrences
÷
eligible scheduled medication occurrences
```

Exclude cancelled occurrences. Define whether skipped items count as non-adherent and keep the rule consistent.

No report metric should be labeled as a medical diagnosis.

---

# 26. Security and Privacy

RAFEEQ handles sensitive personal and health-related information.

Required controls:

- TLS for all external communication.
- Encrypted secrets.
- Password hashing.
- Role- and relation-based authorization.
- Device-specific credentials.
- Audit logging.
- Token revocation.
- Rate limiting.
- Input validation.
- File-upload validation.
- Secure media URLs with expiry.
- Minimal data collection.
- Data-retention configuration.
- Account and device deactivation.
- Privacy-safe notification text.
- No raw camera upload by default.
- No raw microphone upload by default.
- No production secrets in logs.
- Remove or mask tokens and passwords from error reports.
- Consent record before storing personal memory media.
- A privacy notice explaining camera and microphone use.

For the prototype, document legal and regulatory review as pending. Do not claim compliance certification unless independently completed.

---

# 27. Observability

## 27.1 Structured logging

Every component must log JSON or structured fields:

```text
timestamp
level
service
request_id_or_event_id
device_id_optional
patient_id_optional
event_type
message
error_code_optional
```

Do not log:

- passwords
- access tokens
- refresh tokens
- device secrets
- raw audio
- raw video
- full sensitive notes unless explicitly required

## 27.2 Health endpoints

Backend:

```text
GET /health/live
GET /health/ready
```

Robot local diagnostics:

```text
camera_available
microphone_available
speaker_available
sos_button_available
mqtt_connected
backend_reachable
database_writable
last_sync_at
```

## 27.3 Metrics

Track:

- API latency and error rate
- MQTT connection status
- device heartbeat age
- event-ingestion failures
- notification delivery failures
- outbox backlog
- WebSocket connection count
- sync duration
- fall-detector processing rate
- robot CPU temperature and load where available

---

# 28. Environment Variables

Create `.env.example` with no real secrets.

Backend:

```text
APP_ENV=development
APP_BASE_URL=http://localhost:8000
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://redis:6379/0
JWT_ACCESS_SECRET=
JWT_REFRESH_SECRET=
JWT_ACCESS_TTL_MINUTES=15
JWT_REFRESH_TTL_DAYS=30
MQTT_HOST=mosquitto
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
FCM_PROJECT_ID=
FCM_CREDENTIALS_PATH=
OBJECT_STORAGE_ENDPOINT=
OBJECT_STORAGE_BUCKET=
OBJECT_STORAGE_ACCESS_KEY=
OBJECT_STORAGE_SECRET_KEY=
CORS_ALLOWED_ORIGINS=
LOG_LEVEL=INFO
```

Robot:

```text
RAFEEQ_DEVICE_ID=
RAFEEQ_DEVICE_SECRET=
RAFEEQ_PATIENT_ID=
BACKEND_BASE_URL=
MQTT_HOST=
MQTT_PORT=
MQTT_USERNAME=
MQTT_PASSWORD=
LOCAL_DATABASE_PATH=./data/robot.db
HARDWARE_MODE=simulation
CAMERA_INDEX=0
FALL_VERIFICATION_TIMEOUT_SECONDS=20
FALL_DETECTION_COOLDOWN_SECONDS=60
LOG_LEVEL=INFO
```

Mobile:

Use build-time environment configuration for:

```text
API_BASE_URL
WS_BASE_URL
APP_ENV
```

Never embed server secrets in the mobile app.

---

# 29. Testing Strategy

## 29.1 Backend tests

- Domain unit tests.
- Application-service tests.
- Repository integration tests with PostgreSQL.
- API tests.
- Authorization tests.
- Migration tests.
- Event-idempotency tests.
- Emergency-state transition tests.
- Notification outbox tests.
- WebSocket authorization tests.

## 29.2 Robot tests

- Hardware adapter contract tests.
- Reminder scheduling tests.
- Restart-recovery tests.
- Offline outbox tests.
- MQTT reconnect tests.
- Duplicate command tests.
- SOS path tests.
- Fall verification state-machine tests.
- Mock fall detector integration test.
- SQLite migration tests.

## 29.3 Mobile tests

- Domain/use-case unit tests.
- Riverpod controller tests.
- Widget tests for all key screens.
- RTL layout tests.
- Accessibility semantics tests.
- Navigation and permission tests.
- Offline cache tests.
- Emergency live-update tests.
- Golden tests for core screens if practical.

## 29.4 End-to-end tests

Required scenarios:

1. Caregiver registers and creates a patient.
2. Simulated robot pairs with patient.
3. Caregiver creates a medication reminder.
4. Robot synchronizes and executes it.
5. Patient confirms in simulator.
6. Dashboard and report update.
7. Simulator triggers SOS.
8. Caregiver receives live alert.
9. Caregiver acknowledges and resolves it.
10. Doctor views the emergency in the assigned patient report.
11. Robot goes offline, creates an event, reconnects, and synchronizes exactly once.
12. Possible fall is cancelled by patient-safe confirmation.
13. Possible fall escalates after no response.

---

# 30. Performance and Reliability Targets

These are prototype targets under normal local or cloud test conditions.

- SOS button local reaction: under 1 second.
- Robot spoken confirmation after SOS: under 2 seconds.
- Online emergency visible in caregiver app: target under 5 seconds.
- Dashboard initial data load: target under 2 seconds on normal connectivity.
- No event loss during temporary internet outage.
- Duplicate MQTT delivery must not create duplicate records.
- Robot must recover automatically after process restart.
- Backend must return structured errors.
- Mobile app must never crash on an empty API response.
- Robot must continue reminders when backend is unavailable.
- Critical local database writes must be transactional.

---

# 31. Development and Local Run Commands

Create a Makefile with commands similar to:

```text
make setup
make up
make down
make logs
make migrate
make seed
make backend-test
make robot-test
make mobile-test
make lint
make format
make robot-sim
```

Expected local workflow:

```text
cp .env.example .env
docker compose up -d postgres redis mosquitto
make migrate
make seed
make backend
make robot-sim
flutter run
```

Document exact commands in `README.md`.

---

# 32. Demo Data

Seed:

- One caregiver.
- One doctor.
- One patient.
- One paired simulated robot.
- Two emergency contacts.
- Three medication reminders.
- Five routine items.
- Six activity definitions.
- Four memory categories.
- Eight sample memory items using non-sensitive placeholder assets.
- Several completed and missed routine occurrences.
- One false fall alarm.
- One resolved SOS event.
- One doctor note.

Use obvious demo credentials only in local development and document that they must never be deployed.

---

# 33. Implementation Phases

Codex must implement in this order.

## Phase 1 — Repository foundation

Deliver:

- monorepo structure
- Docker Compose
- backend skeleton
- robot skeleton
- Flutter skeleton
- shared contracts folder
- linting and tests
- `.env.example`
- README

Exit criteria:

- all components start
- health checks pass
- CI-style local commands work

## Phase 2 — Backend identity and patient management

Deliver:

- database models and migrations
- auth
- roles
- patients
- caregiver-patient relation
- doctor-patient relation
- emergency contacts
- authorization tests

Exit criteria:

- caregiver can create and read own patient
- unrelated users are denied

## Phase 3 — Mobile onboarding and navigation

Deliver:

- RTL theme
- login
- register
- patient selector
- caregiver navigation
- doctor navigation
- secure token storage

Exit criteria:

- app authenticates against backend
- role-based navigation works

## Phase 4 — Device pairing and simulator

Deliver:

- device registration
- pairing code
- simulator hardware adapters
- MQTT connection
- heartbeat
- device status screen

Exit criteria:

- simulated robot pairs and appears online

## Phase 5 — Routines and medication reminders

Deliver:

- routine CRUD
- recurrence
- occurrence generation
- mobile daily routine
- robot sync
- local scheduler
- completion/snooze/missed results

Exit criteria:

- end-to-end reminder works online
- reminder still executes offline

## Phase 6 — Emergency pipeline

Deliver:

- SOS adapter
- emergency state machine
- event ingestion
- notification outbox
- WebSocket events
- push integration abstraction
- mobile emergency screen
- acknowledge/resolve workflow

Exit criteria:

- SOS appears in app without duplication
- history and transitions are stored

## Phase 7 — Fall detection and verification

Deliver:

- mock detector
- rule-based or pose detector
- verification prompts
- false-alarm flow
- timeout escalation
- cooldown
- tests

Exit criteria:

- both safe-confirmation and no-response scenarios work

## Phase 8 — Activities and memories

Deliver:

- activity definitions and logs
- memory categories/items
- media upload abstraction
- mobile screens
- robot prompt integration

Exit criteria:

- caregiver configures content
- robot can start an activity from synchronized data

## Phase 9 — Reports and doctor mode

Deliver:

- report aggregation
- doctor dashboard
- medical reports
- emergency history
- doctor notes and follow-up date
- export-ready report view

Exit criteria:

- doctor sees only assigned patients
- metrics match seeded event data

## Phase 10 — Hardening and deployment

Deliver:

- security review
- retry and outbox hardening
- observability
- backup documentation
- production-like Docker configuration
- Raspberry Pi systemd services
- demo script
- final E2E test suite

Exit criteria:

- full demo works after fresh setup
- offline/reconnect scenario passes
- no critical test failures

---

# 34. Acceptance Criteria

The project is accepted when all of the following are true:

1. A caregiver can register, log in, and create a patient.
2. A simulated or real robot can be paired using a temporary code.
3. The dashboard displays patient, routine, device, and alert summaries.
4. A caregiver can create a medication reminder.
5. The robot receives and stores the reminder.
6. The reminder executes without internet after synchronization.
7. Patient confirmation updates the backend and report.
8. The physical or simulated SOS button creates one emergency.
9. The caregiver receives a live alert and can acknowledge it.
10. The caregiver can resolve the alert with a note.
11. A possible fall enters verification before escalation.
12. “I am okay” produces a false-alarm outcome.
13. No response produces a confirmed emergency.
14. Duplicate event delivery does not create duplicate emergencies.
15. Offline robot events synchronize after reconnection.
16. Doctor mode shows assigned patients only.
17. Doctor can view reports and add notes.
18. Arabic RTL layout works on all primary screens.
19. Core screens have loading, empty, error, and retry states.
20. Automated tests cover the emergency and reminder state machines.
21. No raw video or audio is uploaded by default.
22. Secrets are not committed.
23. Database migrations work from an empty database.
24. The full system can be started from documented commands.
25. The demo can run using simulation mode without physical hardware.

---

# 35. Definition of Done for Every Feature

A feature is not done until it has:

- domain model
- migration if required
- repository implementation
- application use case
- API or device contract
- authorization checks
- input validation
- error handling
- logging
- unit tests
- integration tests where appropriate
- mobile loading/empty/error states
- Arabic and English strings
- RTL verification
- documentation update
- no embedded secrets
- no new lint/type errors

---

# 36. Known Assumptions

Use these assumptions until the team changes them:

- One robot is paired to one patient at a time.
- A patient may have multiple caregivers.
- A patient may have multiple doctors, but only assigned doctors can see data.
- Android is the first mobile target; architecture remains cross-platform.
- The robot has a camera, microphone, speaker, SOS button, servo, Wi-Fi, and power supply.
- The Raspberry Pi can run the selected local detection pipeline at acceptable speed.
- Health percentages in early UI are adherence/activity metrics, not sensor-validated clinical measurements.
- Internet may be unavailable temporarily.
- Memory media is uploaded only by authorized caregivers.
- Face recognition is not part of the MVP.
- SMS and email are optional later channels.
- The backend is a modular monolith.
- Docker Compose is sufficient for the prototype deployment.
- Device commands are auditable and permission-protected.
- Emergency-service calling is not automatic in the MVP unless a legally reviewed integration is added.

Record changed assumptions in `docs/assumptions.md`.

---

# 37. Required Documentation

Codex must keep these documents updated:

- `README.md`: setup, run, test, and demo.
- `docs/architecture.md`: component and sequence diagrams.
- `docs/api.md`: API usage and authentication.
- `docs/mqtt.md`: topics, payloads, QoS, retry, and examples.
- `docs/security.md`: threat model and privacy decisions.
- `docs/assumptions.md`: unresolved or changed assumptions.
- `docs/demo-script.md`: exact demonstration steps.

Required diagrams in Mermaid:

- system context
- component architecture
- caregiver reminder sequence
- SOS sequence
- fall verification sequence
- offline synchronization sequence
- emergency state machine

---

# 38. Final Codex Instruction

Build RAFEEQ as a reliable, testable, Arabic-first prototype. Prioritize emergency correctness, offline operation, patient privacy, and simple caregiver usability over advanced AI features.

Start with simulation mode and an end-to-end vertical slice:

```text
Caregiver creates reminder
→ backend saves it
→ robot simulator synchronizes
→ reminder executes
→ simulator confirms it
→ dashboard and report update
```

Then implement the SOS vertical slice:

```text
SOS pressed
→ local event stored
→ backend ingests idempotently
→ caregiver receives live alert
→ caregiver acknowledges
→ caregiver resolves
→ report includes the event
```

Do not begin advanced fall-detection work until both vertical slices are stable and tested.


