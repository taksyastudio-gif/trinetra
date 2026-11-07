"""
API tests for TRINETRA v2 Core System endpoints:
- GET /api/system/tier
- POST /api/system/tier/set
- GET /api/events/recent
"""

import os
import sys
import pytest

# Ensure services/vision-engine is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import create_app, event_bus, lite_mode_controller
from trinetra_core.events import Event, EventCategory, EventPriority, EventType
from trinetra_core.capabilities import DeviceTier


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_get_system_tier(client):
    response = client.get("/api/system/tier")
    assert response.status_code == 200
    data = response.json()
    assert "active_tier" in data
    assert "target_vision_fps" in data
    assert "is_lite_mode" in data
    assert "frame_skip_ratio" in data


def test_set_system_tier(client):
    # Set to LITE
    res_lite = client.post("/api/system/tier/set", json={"tier": "lite"})
    assert res_lite.status_code == 200
    data_lite = res_lite.json()
    assert data_lite["status"] == "updated"
    assert data_lite["tier_status"]["active_tier"] == "lite"
    assert data_lite["tier_status"]["is_lite_mode"] is True

    # Set to STANDARD
    res_std = client.post("/api/system/tier/set", json={"tier": "standard"})
    assert res_std.status_code == 200
    assert res_std.json()["tier_status"]["active_tier"] == "standard"

    # Reset to auto
    res_auto = client.post("/api/system/tier/set", json={"tier": "auto"})
    assert res_auto.status_code == 200

    # Invalid tier
    res_bad = client.post("/api/system/tier/set", json={"tier": "ultra_mega_tier"})
    assert res_bad.status_code == 400


def test_get_recent_events(client):
    # Publish test event
    event_bus.publish(Event(
        event_type=EventType.SURFACE_HAZARD,
        category=EventCategory.PERCEPTION,
        priority=EventPriority.CRITICAL_HAZARD,
        payload={"hazard": "pothole", "depth": "deep"}
    ))

    response = client.get("/api/events/recent?limit=10")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) >= 1
    
    last_event = events[-1]
    assert last_event["event_type"] == "perception.surface_hazard"
    assert "sha256" in last_event["metadata"]
