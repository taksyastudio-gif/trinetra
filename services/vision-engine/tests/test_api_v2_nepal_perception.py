"""
API tests for TRINETRA v2 Nepal Perception endpoints:
- POST /api/ocr/bus-route
- POST /api/qr/identify
"""

import os
import sys
import pytest

# Ensure services/vision-engine is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import create_app
from app.camera.adapter import FakeCameraAdapter
from app.audio.speaker import FakeSpeechBackend


@pytest.fixture
def client():
    app = create_app(
        adapter=FakeCameraAdapter(),
        speech_backend=FakeSpeechBackend()
    )
    return TestClient(app)


def test_ocr_bus_route_api(client):
    # Direct text query
    res = client.post("/api/ocr/bus-route", json={
        "text": "साझा यातायात रत्नपार्क लगनखेल नम्बर १५",
        "speak": False
    })
    assert res.status_code == 200
    data = res.json()
    assert data["matched"] is True
    assert data["destination"] == "रत्नपार्क"
    assert data["operator"] == "साझा यातायात"
    assert data["route_number"] == "15"


def test_qr_identify_api(client):
    # 1. Without active camera -> 409 Conflict
    res_conflict = client.post("/api/qr/identify", json={"speak": False})
    assert res_conflict.status_code == 409

    # 2. With active camera -> 200 OK
    client.post("/api/camera/start")
    res = client.post("/api/qr/identify", json={"speak": False})
    assert res.status_code == 200
    data = res.json()
    assert "detected" in data
    assert "scheme" in data
    assert "merchant_name" in data
