# Architecture

RAFEEQ is an edge-cloud modular monolith. The robot owns critical offline behavior; the backend owns shared configuration and APIs; the app never connects directly to hardware or databases.

```mermaid
flowchart LR
  Robot[Robot / simulator\nSQLite + outbox] <-->|MQTT + HTTPS| Backend[FastAPI modular monolith\nPostgreSQL + Redis]
  Backend <-->|REST + WebSocket| Mobile[Flutter app\nArabic RTL first]
```

```mermaid
sequenceDiagram
  Caregiver->>Backend: Create reminder
  Backend-->>Robot: Sync snapshot
  Robot->>Robot: Store and schedule locally
  Robot->>Patient: Speak reminder
  Patient-->>Robot: Confirm
  Robot-->>Backend: Completion event (idempotent)
  Backend-->>Mobile: Report update
```

```mermaid
sequenceDiagram
  Patient->>Robot: Press SOS
  Robot->>Robot: Store event + outbox
  Robot-->>Patient: Calm confirmation
  Robot-->>Backend: SOS event
  Backend-->>Mobile: Live critical alert
  Mobile->>Backend: Acknowledge, then resolve
```

```mermaid
stateDiagram-v2
  [*] --> DETECTED
  DETECTED --> VERIFYING: possible fall
  DETECTED --> CONFIRMED: SOS
  VERIFYING --> FALSE_ALARM: patient safe
  VERIFYING --> CONFIRMED: help or timeout
  CONFIRMED --> NOTIFIED
  NOTIFIED --> ACKNOWLEDGED
  ACKNOWLEDGED --> RESOLVED
  CONFIRMED --> RESOLVED
```

```mermaid
sequenceDiagram
  Detector->>Robot: PossibleFallDetected
  Robot->>Patient: Are you okay?
  alt Patient confirms safe
    Patient-->>Robot: I am okay
    Robot->>Robot: FALSE_ALARM
  else Help or timeout
    Robot->>Robot: CONFIRMED
    Robot-->>Backend: Emergency event
  end
```

```mermaid
sequenceDiagram
  Robot->>Robot: Event + outbox in one transaction
  Note over Robot,Backend: Internet unavailable
  Robot->>Robot: Retry with backoff and jitter
  Robot-->>Backend: Batch preserving event UUID and occurred_at
  Backend-->>Robot: Idempotent acknowledgement
  Robot->>Robot: Mark outbox row synced
```

