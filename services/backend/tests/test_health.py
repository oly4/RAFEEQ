from fastapi.testclient import TestClient

from rafeeq_backend.main import app


def test_liveness() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_is_returned() -> None:
    response = TestClient(app).get("/health/ready", headers={"x-request-id": "test-request"})
    assert response.headers["x-request-id"] == "test-request"
