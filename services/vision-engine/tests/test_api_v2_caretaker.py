"""
API tests for TRINETRA v2 Caretaker & Autonomy endpoints:
- /api/caretaker/autonomy
- /api/caretaker/medications
- /api/caretaker/contacts
- /api/caretaker/emergency/trigger, /cancel, /status
- /api/caretaker/audit
"""

import os
import sys
import pytest

# Ensure services/vision-engine is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import create_app, context_memory


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_caretaker_autonomy_api(client):
    res = client.get("/api/caretaker/autonomy")
    assert res.status_code == 200
    data = res.json()
    assert "autonomy_level" in data
    assert "autonomy_name" in data

    # Update to L3 Routine Auto
    update_res = client.post("/api/caretaker/autonomy", json={"level": 3})
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["autonomy"]["autonomy_level"] == 3
    assert updated["autonomy"]["autonomy_name"] == "L3_ROUTINE_AUTO"


def test_caretaker_medications_and_taken_api(client):
    # Add medication
    add_res = client.post("/api/caretaker/medications", json={
        "medicine_name": "एमलोडिपिन",
        "dosage": "५ मि.ग्रा., १ चक्की",
        "timing_type": "before_meal",
        "time_of_day": "07:30",
        "notes": "रक्तचापको लागि"
    })
    assert add_res.status_code == 200
    med_id = add_res.json()["medication_id"]

    # List medications
    list_res = client.get("/api/caretaker/medications")
    assert list_res.status_code == 200
    meds = list_res.json()
    assert any(m["id"] == med_id and m["medicine_name"] == "एमलोडिपिन" for m in meds)

    # Check due medications endpoint
    due_res = client.get("/api/caretaker/medications/due")
    assert due_res.status_code == 200

    # Mark as taken
    take_res = client.post(f"/api/caretaker/medications/{med_id}/take")
    assert take_res.status_code == 200
    assert take_res.json()["status"] == "acknowledged"


def test_caretaker_contacts_api(client):
    add_res = client.post("/api/caretaker/contacts", json={
        "name": "दिपेश",
        "relationship": "भाइ",
        "phone_number": "+9779812345678",
        "is_primary_emergency": True
    })
    assert add_res.status_code == 200
    contact_id = add_res.json()["contact_id"]

    list_res = client.get("/api/caretaker/contacts")
    assert list_res.status_code == 200
    contacts = list_res.json()
    assert any(c["id"] == contact_id and c["name"] == "दिपेश" for c in contacts)


def test_caretaker_emergency_countdown_api(client):
    # Trigger emergency countdown
    trigger_res = client.post("/api/caretaker/emergency/trigger", json={
        "incident_type": "fall_detected",
        "duration_seconds": 10.0
    })
    assert trigger_res.status_code == 200
    assert trigger_res.json()["status"] == "countdown_started"

    # Status check
    status_res = client.get("/api/caretaker/emergency/status")
    assert status_res.status_code == 200
    assert status_res.json()["emergency_active"] is True
    assert status_res.json()["remaining_seconds"] > 0

    # User cancels countdown
    cancel_res = client.post("/api/caretaker/emergency/cancel", json={"reason": "user_ok"})
    assert cancel_res.status_code == 200
    assert cancel_res.json()["success"] is True

    # Audit trail verification
    audit_res = client.get("/api/caretaker/audit?limit=5")
    assert audit_res.status_code == 200
    trail = audit_res.json()
    assert len(trail) > 0
    assert any("emergency" in r["event_type"] for r in trail)
