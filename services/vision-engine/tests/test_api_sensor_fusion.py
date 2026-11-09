"""
Tests for TRINETRA Sensor Fusion and Cane Telemetry Endpoints
"""

from fastapi.testclient import TestClient
from app.main import app


def test_cane_status_endpoint():
    client = TestClient(app)
    res = client.get("/api/sensors/cane/status", headers={"X-API-Key": "dev-token"})
    assert res.status_code == 200
    data = res.json()
    assert "running" in data
    assert "connected" in data
    assert "packets_received" in data


def test_cane_telemetry_and_fusion_evaluate():
    client = TestClient(app)
    # Post raw CSV line indicating forward obstacle at 50cm
    ingest_res = client.post(
        "/api/sensors/cane/telemetry",
        json={"raw_line": "CANE,50.0,85.0,0.0,0.0,1"},
        headers={"X-API-Key": "dev-token"}
    )
    assert ingest_res.status_code == 200
    assert ingest_res.json()["success"] is True

    # Evaluate fusion with optimistic vision saying "no hazard"
    eval_res = client.post(
        "/api/sensors/fusion/evaluate",
        json={
            "vision_hazard_detected": False,
            "vision_hazard_type": "none",
            "vision_message_ne": "बाटो सफा छ"
        },
        headers={"X-API-Key": "dev-token"}
    )
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["alert_level"] == "CRITICAL_STOP"
    assert eval_data["primary_source"] == "ultrasonic"
    assert eval_data["veto_applied"] is True
    assert "रोकिनुहोस्" in eval_data["hazard_description_ne"]
