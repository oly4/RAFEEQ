# API

The backend owns the REST OpenAPI contract at `/docs`. Product APIs use `/api/v1`; robot APIs use `/device-api/v1`; live app subscriptions use `/ws/patients/{patient_id}`.

Implemented API groups:

- rotating JWT authentication: register, login, refresh, logout, current user
- relation-authorized patients and aggregated dashboard
- routines, medication details, occurrences, complete/snooze/skip
- simulated device provisioning plus per-device authenticated snapshots, acknowledgments, heartbeat, and event batches
- idempotent SOS and possible-fall verification state transitions
- caregiver emergency history, acknowledgment, and resolution
- activities, activity sessions, memory categories, and memory items
- doctor assignment, assigned-patient access, and shared notes
- adherence, activity, device, and emergency report summary
- authenticated WebSocket emergency updates

All access checks use caregiver-patient or doctor-patient relationships. The application returns the versioned error envelope from `packages/contracts/schemas/api-error-v1.schema.json`.

Development-only endpoints under `/api/v1` allow provisioning a simulated robot and triggering SOS/fall scenarios. They return `404` outside development mode.
