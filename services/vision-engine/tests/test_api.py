"""
Trinetra Vision Engine API & Camera Adapter Automated Tests
Validates health checks, camera lifecycle, frame encoding, and error boundaries
using the FakeCameraAdapter (no physical hardware required).
"""

import pytest
import sys
import os

# Ensure services/vision-engine is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.camera.adapter import (
    CameraInitializationError,
    CameraNotActiveError,
    FakeCameraAdapter,
)
from app.main import create_app, camera_manager


@pytest.fixture
def fake_adapter():
    """Provides a fresh, clean FakeCameraAdapter."""
    adapter = FakeCameraAdapter(width=320, height=240)
    yield adapter
    if adapter.is_active():
        adapter.stop()


@pytest.fixture
def test_client(fake_adapter):
    """Provides a FastAPI TestClient configured with the fake adapter."""
    from fastapi.testclient import TestClient
    app = create_app(adapter=fake_adapter)
    with TestClient(app) as client:
        yield client
    if fake_adapter.is_active():
        fake_adapter.stop()


def test_health_endpoint(test_client):
    """GET /api/health returns 200 OK and service identifiers."""
    response = test_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "trinetra-vision-engine"
    assert "version" in data


def test_camera_status_inactive(test_client):
    """GET /api/camera/status correctly reflects inactive camera state."""
    response = test_client.get("/api/camera/status")
    assert response.status_code == 200
    data = response.json()
    assert data["active"] is False
    assert data["frames_captured"] == 0
    assert data["adapter"] == "FakeCameraAdapter"


def test_camera_frame_when_inactive_returns_409(test_client):
    """GET /api/camera/frame returns 409 Conflict when camera is not started."""
    response = test_client.get("/api/camera/frame")
    assert response.status_code == 409
    data = response.json()
    assert "detail" in data
    assert "not active" in data["detail"].lower()


def test_camera_start_and_status(test_client):
    """POST /api/camera/start successfully transitions camera to active."""
    start_resp = test_client.post("/api/camera/start")
    assert start_resp.status_code == 200
    data = start_resp.json()
    assert data["active"] is True
    assert data["status"] == "started"

    status_resp = test_client.get("/api/camera/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["active"] is True


def test_camera_frame_retrieval(test_client):
    """GET /api/camera/frame returns genuine JPEG binary bytes when camera is active."""
    test_client.post("/api/camera/start")

    frame_resp = test_client.get("/api/camera/frame")
    assert frame_resp.status_code == 200
    assert frame_resp.headers["content-type"] == "image/jpeg"

    # Verify standard JPEG header (SOI marker 0xFFD8)
    content = frame_resp.content
    assert len(content) > 10
    assert content[:2] == b"\xff\xd8"
    assert content[-2:] == b"\xff\xd9"  # EOI marker


def test_camera_stop(test_client):
    """POST /api/camera/stop releases camera hardware lock."""
    test_client.post("/api/camera/start")
    assert test_client.get("/api/camera/status").json()["active"] is True

    stop_resp = test_client.post("/api/camera/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["active"] is False

    # Status reflects inactive
    assert test_client.get("/api/camera/status").json()["active"] is False

    # Subsequent frame request is blocked
    frame_resp = test_client.get("/api/camera/frame")
    assert frame_resp.status_code == 409


def test_repeated_start_and_stop_safety(test_client):
    """Repeated calls to /api/camera/start and /api/camera/stop must not crash or leak resources."""
    # First start
    r1 = test_client.post("/api/camera/start")
    assert r1.status_code == 200
    assert r1.json()["status"] == "started"

    # Second redundant start: should return already_running gracefully
    r2 = test_client.post("/api/camera/start")
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_running"

    # First stop
    s1 = test_client.post("/api/camera/stop")
    assert s1.status_code == 200

    # Second redundant stop: must be idempotent and succeed
    s2 = test_client.post("/api/camera/stop")
    assert s2.status_code == 200
    assert s2.json()["status"] == "stopped"


def test_camera_initialization_failure():
    """Service returns 503 Service Unavailable with clear message when hardware fails to open."""
    from fastapi.testclient import TestClient
    faulty_adapter = FakeCameraAdapter(should_fail_init=True)
    app = create_app(adapter=faulty_adapter)

    with TestClient(app) as client:
        resp = client.post("/api/camera/start")
        assert resp.status_code == 503
        data = resp.json()
        assert "detail" in data
        assert "Simulated camera hardware initialization failure" in data["detail"]


def test_camera_capture_failure():
    """Service returns 500 Internal Server Error when frame reading stalls."""
    from fastapi.testclient import TestClient
    broken_capture_adapter = FakeCameraAdapter(should_fail_capture=True)
    app = create_app(adapter=broken_capture_adapter)

    with TestClient(app) as client:
        client.post("/api/camera/start")
        resp = client.get("/api/camera/frame")
        assert resp.status_code == 500
