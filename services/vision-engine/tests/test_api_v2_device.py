"""
Integration tests for Phase 5 Device & Wearable REST Endpoints:
- GET /api/device/health
- POST /api/device/telemetry
- GET /api/wearable/status
- POST /api/wearable/haptic
"""
import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_api_device_health(client):
    res = client.get("/api/device/health")
    assert res.status_code == 200
    data = res.json()
    assert "battery_percentage" in data
    assert "temperature_celsius" in data
    assert "active_tier" in data
    assert "is_battery_critical" in data


def test_api_device_telemetry_post(client):
    # Post client battery status
    res = client.post("/api/device/telemetry", json={
        "battery_pct": 92.5,
        "is_charging": True,
        "temp_c": 39.0,
        "frame_drop_ratio": 0.01
    })
    assert res.status_code == 200
    data = res.json()
    assert data["battery_percentage"] == 92.5
    assert data["is_charging"] is True
    assert data["temperature_celsius"] == 39.0


def test_api_wearable_status(client):
    res = client.get("/api/wearable/status")
    assert res.status_code == 200
    data = res.json()
    assert "device_model" in data
    assert "has_camera" in data
    assert data["has_camera"] is True
    assert "stream_url" in data


def test_api_wearable_haptic(client):
    res = client.post("/api/wearable/haptic", json={
        "location": "left_temple",
        "pattern": "urgent_pulse",
        "intensity": 0.8
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["location"] == "left_temple"
    assert data["pattern"] == "urgent_pulse"
