import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import create_app, camera_manager
from app.camera.adapter import FakeCameraAdapter, OpenCVCameraAdapter


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_camera_mirror_endpoints(client):
    headers = {"X-Trinetra-Session-Token": "test_token"}

    # Get mirror mode
    resp = client.get("/api/camera/mirror", headers=headers)
    assert resp.status_code == 200
    assert "mirror_mode" in resp.json()

    # Toggle mirror mode to True
    resp = client.post("/api/camera/mirror", json={"mirror_mode": True}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["mirror_mode"] is True

    # Verify state reflects
    resp = client.get("/api/camera/mirror", headers=headers)
    assert resp.json()["mirror_mode"] is True

    # Toggle back to False
    resp = client.post("/api/camera/mirror", json={"mirror_mode": False}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["mirror_mode"] is False
