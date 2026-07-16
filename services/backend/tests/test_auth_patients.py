from collections.abc import Generator
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rafeeq_backend.database import Base, get_db
from rafeeq_backend.main import app


def make_client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def register_and_login(client: TestClient, email: str) -> str:
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test Caregiver",
            "email": email,
            "password": "safe-password-123",
            "role": "caregiver",
        },
    )
    assert registration.status_code == 201, registration.text
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "safe-password-123",
        },
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_caregiver_can_create_and_read_own_patient() -> None:
    client = make_client()
    token = register_and_login(client, "caregiver@example.com")
    created = client.post(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
        json={"display_name": "أمينة", "relationship_label": "daughter"},
    )
    assert created.status_code == 201, created.text
    patient_id = created.json()["id"]
    fetched = client.get(
        f"/api/v1/patients/{patient_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == "أمينة"


def test_unrelated_caregiver_is_denied_patient_access() -> None:
    client = make_client()
    owner = register_and_login(client, "owner@example.com")
    other = register_and_login(client, "other@example.com")
    patient_id = client.post(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {owner}"},
        json={"display_name": "Fatima"},
    ).json()["id"]
    denied = client.get(
        f"/api/v1/patients/{patient_id}",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert denied.status_code == 404


def test_refresh_token_rotates_and_cannot_be_reused() -> None:
    client = make_client()
    register_and_login(client, "refresh@example.com")
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "refresh@example.com",
            "password": "safe-password-123",
        },
    ).json()
    first_refresh = login["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert replay.status_code == 401


def test_medication_routine_materializes_and_completes_occurrence() -> None:
    client = make_client()
    token = register_and_login(client, "routine@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    patient_id = client.post(
        "/api/v1/patients", headers=headers, json={"display_name": "Amina"}
    ).json()["id"]
    routine = client.post(
        f"/api/v1/patients/{patient_id}/routines",
        headers=headers,
        json={
            "type": "medication",
            "title": "Morning medicine",
            "start_date": "2026-07-13",
            "scheduled_local_time": "09:00:00",
            "medication": {"medication_name": "Demo medicine", "dosage_text": "One tablet"},
        },
    )
    assert routine.status_code == 201, routine.text
    occurrences = client.get(
        f"/api/v1/patients/{patient_id}/routine-occurrences", headers=headers
    ).json()["items"]
    assert len(occurrences) == 1
    completed = client.post(
        f"/api/v1/routine-occurrences/{occurrences[0]['id']}/complete",
        headers=headers,
        json={"confirmation_source": "caregiver"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


def test_device_snapshot_includes_completed_app_tasks() -> None:
    client = make_client()
    token = register_and_login(client, "snapshot-tasks@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    patient_id = client.post(
        "/api/v1/patients", headers=headers, json={"display_name": "Amina"}
    ).json()["id"]
    device = client.post(f"/api/v1/patients/{patient_id}/devices/simulated", headers=headers).json()
    routine = client.post(
        f"/api/v1/patients/{patient_id}/routines",
        headers=headers,
        json={
            "type": "custom",
            "title": "Lunch",
            "start_date": "2026-07-13",
            "scheduled_local_time": "12:00:00",
        },
    )
    assert routine.status_code == 201, routine.text
    occurrence = client.get(
        f"/api/v1/patients/{patient_id}/routine-occurrences", headers=headers
    ).json()["items"][0]
    client.post(
        f"/api/v1/routine-occurrences/{occurrence['id']}/complete",
        headers=headers,
        json={"confirmation_source": "caregiver"},
    )

    snapshot = client.get(
        "/device-api/v1/sync/snapshot",
        headers={"X-Device-Id": device["id"], "X-Device-Secret": device["device_secret"]},
    )

    assert snapshot.status_code == 200, snapshot.text
    synced_occurrence = snapshot.json()["routines"][0]["occurrences"][0]
    assert synced_occurrence["id"] == occurrence["id"]
    assert synced_occurrence["status"] == "completed"


def test_device_can_create_confirmed_voice_routine_but_not_medication() -> None:
    client = make_client()
    token = register_and_login(client, "voice-routine@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    patient_id = client.post(
        "/api/v1/patients", headers=headers, json={"display_name": "Amina"}
    ).json()["id"]
    device = client.post(f"/api/v1/patients/{patient_id}/devices/simulated", headers=headers).json()
    device_headers = {
        "X-Device-Id": device["id"],
        "X-Device-Secret": device["device_secret"],
    }

    created = client.post(
        "/device-api/v1/voice-routines",
        headers=device_headers,
        json={
            "type": "appointment",
            "title": "Meeting",
            "description": "Created by voice after confirmation.",
            "start_date": "2026-07-14",
            "end_date": "2026-07-14",
            "recurrence_rule": "FREQ=DAILY;COUNT=1",
            "scheduled_local_time": "09:00:00",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["title"] == "Meeting"

    snapshot = client.get(
        "/device-api/v1/sync/snapshot",
        headers=device_headers,
    )
    titles = [item["title"] for item in snapshot.json()["routines"]]
    assert "Meeting" in titles

    denied = client.post(
        "/device-api/v1/voice-routines",
        headers=device_headers,
        json={
            "type": "medication",
            "title": "Medicine",
            "start_date": "2026-07-14",
            "scheduled_local_time": "10:00:00",
            "medication": {"medication_name": "Demo", "dosage_text": "One tablet"},
        },
    )
    assert denied.status_code == 409


def test_sos_ingestion_is_idempotent_and_can_be_acknowledged_and_resolved() -> None:
    client = make_client()
    token = register_and_login(client, "sos@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    patient_id = client.post(
        "/api/v1/patients", headers=headers, json={"display_name": "Amina"}
    ).json()["id"]
    provisioned = client.post(f"/api/v1/patients/{patient_id}/devices/simulated", headers=headers)
    assert provisioned.status_code == 201, provisioned.text
    device = provisioned.json()
    event_id = str(uuid4())
    event = {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": "sos_pressed",
        "device_id": device["id"],
        "patient_id": patient_id,
        "occurred_at": "2026-07-13T12:00:00Z",
        "sequence": 1,
        "payload": {},
    }
    device_headers = {
        "X-Device-Id": device["id"],
        "X-Device-Secret": device["device_secret"],
    }
    first = client.post(
        "/device-api/v1/events/batch", headers=device_headers, json={"events": [event]}
    )
    second = client.post(
        "/device-api/v1/events/batch", headers=device_headers, json={"events": [event]}
    )
    assert first.status_code == 200, first.text
    assert second.json()["items"][0]["status"] == "duplicate"
    emergency_id = first.json()["items"][0]["emergency_id"]
    acknowledged = client.post(f"/api/v1/emergencies/{emergency_id}/acknowledge", headers=headers)
    assert acknowledged.json()["status"] == "acknowledged"
    resolved = client.post(
        f"/api/v1/emergencies/{emergency_id}/resolve",
        headers=headers,
        json={"resolution_note": "Caregiver confirmed the patient is safe."},
    )
    assert resolved.json()["status"] == "resolved"
    history = client.get(f"/api/v1/patients/{patient_id}/emergencies", headers=headers).json()[
        "items"
    ]
    assert len(history) == 1


def test_websocket_subscription_rechecks_patient_authorization() -> None:
    client = make_client()
    owner = register_and_login(client, "socket-owner@example.com")
    unrelated = register_and_login(client, "socket-other@example.com")
    patient_id = client.post(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {owner}"},
        json={"display_name": "Amina"},
    ).json()["id"]
    with client.websocket_connect(f"/ws/patients/{patient_id}") as websocket:
        websocket.send_json({"type": "authenticate", "token": owner})
        assert websocket.receive_json()["type"] == "connection.ready"
    with client.websocket_connect(f"/ws/patients/{patient_id}") as websocket:
        websocket.send_json({"type": "authenticate", "token": unrelated})
        try:
            websocket.receive_json()
            raise AssertionError("Unrelated caregiver subscription should close")
        except WebSocketDisconnect as exc:
            assert exc.code == 4403


def test_possible_fall_safe_and_timeout_verification_paths() -> None:
    client = make_client()
    token = register_and_login(client, "falls@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    patient_id = client.post(
        "/api/v1/patients", headers=headers, json={"display_name": "Amina"}
    ).json()["id"]
    device = client.post(f"/api/v1/patients/{patient_id}/devices/simulated", headers=headers).json()
    possible = client.post(f"/api/v1/devices/{device['id']}/simulate-fall", headers=headers)
    assert possible.status_code == 200, possible.text
    assert possible.json()["status"] == "verifying"
    safe = client.post(
        f"/api/v1/emergencies/{possible.json()['id']}/simulate-verification",
        headers=headers,
        json={"outcome": "safe"},
    )
    assert safe.json()["status"] == "false_alarm"

    second = client.post(f"/api/v1/devices/{device['id']}/simulate-fall", headers=headers).json()
    timeout = client.post(
        f"/api/v1/emergencies/{second['id']}/simulate-verification",
        headers=headers,
        json={"outcome": "timeout"},
    )
    assert timeout.json()["status"] == "notified"
    assert timeout.json()["type"] == "confirmed_fall"
    assert timeout.json()["metadata_json"]["confirmed_by_timeout"] is True


def test_activities_memories_and_report_metrics() -> None:
    client = make_client()
    token = register_and_login(client, "content@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    patient_id = client.post(
        "/api/v1/patients", headers=headers, json={"display_name": "Amina"}
    ).json()["id"]
    activity = client.post(
        f"/api/v1/patients/{patient_id}/activities",
        headers=headers,
        json={
            "type": "memory_exercise",
            "title": "Recognize a family photo",
            "duration_minutes": 10,
        },
    )
    assert activity.status_code == 201, activity.text
    log = client.post(f"/api/v1/activities/{activity.json()['id']}/start", headers=headers).json()
    completed = client.post(f"/api/v1/activity-logs/{log['id']}/complete", headers=headers)
    assert completed.json()["status"] == "completed"
    category = client.post(
        f"/api/v1/patients/{patient_id}/memory-categories",
        headers=headers,
        json={"name": "Family"},
    ).json()
    memory = client.post(
        f"/api/v1/patients/{patient_id}/memories",
        headers=headers,
        json={
            "category_id": category["id"],
            "title": "Family picnic",
            "description": "A consented demo memory",
            "media_type": "text",
            "people_labels": ["Amina"],
        },
    )
    assert memory.status_code == 201, memory.text
    memory_id = memory.json()["id"]
    updated_memory = client.patch(
        f"/api/v1/memories/{memory_id}",
        headers=headers,
        json={
            "title": "Updated family picnic",
            "description": "Updated demo memory",
            "people_labels": ["Amina", "Sara"],
            "spoken_prompt": "A calm hint for the patient",
        },
    )
    assert updated_memory.status_code == 200, updated_memory.text
    assert updated_memory.json()["title"] == "Updated family picnic"
    assert updated_memory.json()["people_labels_json"] == ["Amina", "Sara"]
    deleted_memory = client.delete(f"/api/v1/memories/{memory_id}", headers=headers)
    assert deleted_memory.status_code == 204, deleted_memory.text
    memory_list = client.get(f"/api/v1/patients/{patient_id}/memories", headers=headers)
    assert memory_list.status_code == 200, memory_list.text
    assert memory_list.json()["items"] == []
    report = client.get(f"/api/v1/patients/{patient_id}/reports/summary", headers=headers)
    assert report.json()["memory_activities_completed"] == 1
    assert report.json()["total_activity_sessions"] == 1
    weekly = client.get(
        f"/api/v1/patients/{patient_id}/reports/summary?period=week",
        headers=headers,
    )
    assert weekly.status_code == 200, weekly.text
    assert weekly.json()["period"] == "week"
    assert len(weekly.json()["medication_adherence_trend"]) == 7
    assert len(weekly.json()["memory_activity_trend"]) == 7
    assert weekly.json()["range_start"] <= weekly.json()["range_end"]
    invalid_period = client.get(
        f"/api/v1/patients/{patient_id}/reports/summary?period=year",
        headers=headers,
    )
    assert invalid_period.status_code == 422


def test_assigned_doctor_can_view_patient_and_add_shared_note() -> None:
    client = make_client()
    caregiver = register_and_login(client, "doctor-owner@example.com")
    caregiver_headers = {"Authorization": f"Bearer {caregiver}"}
    patient_id = client.post(
        "/api/v1/patients",
        headers=caregiver_headers,
        json={"display_name": "Amina"},
    ).json()["id"]
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Dr Samir",
            "email": "doctor@example.com",
            "password": "safe-password-123",
            "role": "doctor",
        },
    )
    assert registration.status_code == 201
    doctor = client.post(
        "/api/v1/auth/login",
        json={"email": "doctor@example.com", "password": "safe-password-123"},
    ).json()["access_token"]
    invited = client.post(
        f"/api/v1/patients/{patient_id}/doctors/invite",
        headers=caregiver_headers,
        json={"email": "doctor@example.com"},
    )
    assert invited.status_code == 200, invited.text
    doctor_headers = {"Authorization": f"Bearer {doctor}"}
    assigned = client.get("/api/v1/doctor/patients", headers=doctor_headers)
    assert assigned.json()["total"] == 1
    note = client.post(
        f"/api/v1/doctor/patients/{patient_id}/notes",
        headers=doctor_headers,
        json={"text": "Continue the current reminder routine."},
    )
    assert note.status_code == 201, note.text
    caregiver_notes = client.get(
        f"/api/v1/doctor/patients/{patient_id}/notes", headers=caregiver_headers
    )
    assert caregiver_notes.json()[0]["text"].startswith("Continue")


def test_assigned_doctor_can_add_medication_routine_only() -> None:
    client = make_client()
    caregiver = register_and_login(client, "doctor-med-owner@example.com")
    caregiver_headers = {"Authorization": f"Bearer {caregiver}"}
    patient_id = client.post(
        "/api/v1/patients",
        headers=caregiver_headers,
        json={"display_name": "Amina"},
    ).json()["id"]
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Dr Medication",
            "email": "doctor-med@example.com",
            "password": "safe-password-123",
            "role": "doctor",
        },
    )
    assert registration.status_code == 201
    doctor = client.post(
        "/api/v1/auth/login",
        json={"email": "doctor-med@example.com", "password": "safe-password-123"},
    ).json()["access_token"]
    invited = client.post(
        f"/api/v1/patients/{patient_id}/doctors/invite",
        headers=caregiver_headers,
        json={"email": "doctor-med@example.com"},
    )
    assert invited.status_code == 200, invited.text
    doctor_headers = {"Authorization": f"Bearer {doctor}"}

    created = client.post(
        f"/api/v1/patients/{patient_id}/routines",
        headers=doctor_headers,
        json={
            "type": "medication",
            "title": "Evening medicine",
            "start_date": "2026-07-16",
            "scheduled_local_time": "20:00:00",
            "medication": {
                "medication_name": "Evening medicine",
                "dosage_text": "One tablet",
                "instructions": "After dinner",
            },
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["type"] == "medication"

    routines = client.get(
        f"/api/v1/patients/{patient_id}/routines",
        headers=caregiver_headers,
    )
    assert "Evening medicine" in [item["title"] for item in routines.json()["items"]]

    denied = client.post(
        f"/api/v1/patients/{patient_id}/routines",
        headers=doctor_headers,
        json={
            "type": "appointment",
            "title": "Follow-up call",
            "start_date": "2026-07-16",
            "scheduled_local_time": "10:00:00",
        },
    )
    assert denied.status_code == 403
