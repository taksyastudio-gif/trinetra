"""
Direct route integration tests for Trinetra Incident Documentation and Offline Location API endpoints.
Validates HTTP handlers, conflict prevention when camera inactive, SHA-256 tamper verification,
and privacy-safe location configuration without requiring loopback network socket transport.
"""

from pathlib import Path
import tempfile
import pytest
from fastapi import HTTPException

from app.audio.speaker import FakeSpeechBackend
from app.camera.adapter import FakeCameraAdapter
from app.detection.engine import FakeDetectionEngine
from app.incident.recorder import IncidentRecorder
from app.location.provider import DisabledLocationProvider, LocationManager
from app.main import (
    IncidentCaptureRequest,
    LocationConfigureRequest,
    camera_manager,
    create_app,
    incident_recorder,
    location_manager,
)


@pytest.fixture
def api_routes():
    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = FakeCameraAdapter(width=320, height=240)
        speech = FakeSpeechBackend(supported_languages=["en", "ne"])
        rec = IncidentRecorder(storage_dir=Path(tmp_dir), max_records=10)
        loc = LocationManager(DisabledLocationProvider())

        app = create_app(
            adapter=adapter,
            speech_backend=speech,
            detection_engine=FakeDetectionEngine(),
            custom_incident_recorder=rec
        )

        routes = {route.name: route.endpoint for route in app.routes if hasattr(route, "endpoint")}
        yield routes, adapter, rec, loc
        if adapter.is_active():
            adapter.stop()


def test_incident_api_capture_without_camera_fails_cleanly(api_routes):
    """Validates that capturing an incident when camera is inactive raises HTTP 409 Conflict."""
    routes, adapter, rec, _ = api_routes
    assert not adapter.is_active()

    capture_fn = routes["incident_capture"]
    with pytest.raises(HTTPException) as exc_info:
        capture_fn(IncidentCaptureRequest(notes="No camera test"))

    assert exc_info.value.status_code == 409
    assert "Camera is not active" in exc_info.value.detail


def test_incident_api_full_lifecycle_and_verification(api_routes):
    """Validates full capture -> list -> get metadata -> get image -> cryptographic verify workflow."""
    routes, adapter, rec, _ = api_routes

    # 1. Start camera session
    start_fn = routes["start_camera"]
    start_resp = start_fn()
    assert start_resp.active is True

    # 2. Capture incident snapshot
    capture_fn = routes["incident_capture"]
    cap_resp = capture_fn(IncidentCaptureRequest(notes="Scene test", language="ne"))
    incident_id = cap_resp["incident_id"]
    assert cap_resp["image_sha256"]
    assert cap_resp["integrity_digest"]
    assert "no facial recognition" in cap_resp["legal_disclaimer"].lower()

    # 3. List incidents
    list_fn = routes["incident_list"]
    summaries = list_fn()
    assert len(summaries) >= 1
    assert any(s["incident_id"] == incident_id for s in summaries)

    # 4. Get incident detail
    get_fn = routes["incident_get"]
    detail = get_fn(incident_id=incident_id)
    assert detail["incident_id"] == incident_id
    assert detail["image_filename"].endswith(".jpg")

    # 5. Fetch raw image bytes
    get_img_fn = routes["incident_get_image"]
    img_resp = get_img_fn(incident_id=incident_id)
    assert img_resp.media_type == "image/jpeg"
    assert len(img_resp.body) > 0

    # 6. Verify integrity endpoint
    verify_fn = routes["incident_verify"]
    v_data = verify_fn(incident_id=incident_id)
    assert v_data["verified"] is True
    assert v_data["image_integrity"] is True
    assert v_data["digest_integrity"] is True


def test_location_api_status_and_offline_configuration(api_routes):
    """Validates privacy default, offline coordinate configuration, and inclusion in incidents."""
    routes, adapter, rec, _ = api_routes

    status_fn = routes["location_status"]
    config_fn = routes["location_configure"]

    # 1. Default status must be disabled
    s_data = status_fn()
    assert s_data.status == "disabled"
    assert s_data.latitude is None
    assert s_data.longitude is None
    assert "local-only" in s_data.privacy_notice.lower()

    # 2. Configure manual offline location (Kathmandu landmark reference)
    c_data = config_fn(LocationConfigureRequest(
        enabled=True,
        provider_type="manual",
        manual_latitude=27.7172,
        manual_longitude=85.3240,
        manual_accuracy_meters=30.0
    ))
    assert c_data["status"] == "cached"
    assert c_data["latitude"] == 27.7172
    assert c_data["longitude"] == 85.3240
    assert c_data["source"] == "manual_offline"

    # 3. Capture incident while location is configured: coordinates must appear in metadata
    start_fn = routes["start_camera"]
    start_fn()

    capture_fn = routes["incident_capture"]
    incident_data = capture_fn(IncidentCaptureRequest(notes="Incident with location"))
    loc = incident_data.get("location")
    assert loc is not None
    assert loc["latitude"] == 27.7172
    assert loc["longitude"] == 85.3240

    # 4. Disable location again
    dis_data = config_fn(LocationConfigureRequest(enabled=False))
    assert dis_data["status"] == "disabled"
