"""
Unit tests for Caretaker Safety Protocol: 10-second pre-alert countdown and cancellation.
"""
import time
from pathlib import Path
import pytest
from app.camera.adapter import FramePacket
from app.incident.recorder import IncidentRecorder


def test_prealert_trigger_status_and_cancel(tmp_path: Path):
    rec = IncidentRecorder(storage_dir=tmp_path, speech_manager=None)
    packet = FramePacket(
        frame_id=10,
        captured_at=time.time(),
        jpeg_bytes=b"\xff\xd8\xff\xe0test_jpeg",
        width=640,
        height=480,
        source_id="test_cam",
        session_id="sess_test"
    )

    res = rec.trigger_prealert(packet, countdown_seconds=10, language="ne")
    assert res["status"] == "prealert_started"
    assert res["countdown_seconds"] == 10

    status = rec.get_prealert_status()
    assert status["active"] is True
    assert status["remaining_seconds"] > 0

    cancel_res = rec.cancel_prealert()
    assert cancel_res["status"] == "cancelled"

    status_after = rec.get_prealert_status()
    assert status_after["active"] is False


def test_prealert_expiration_confirms_incident(tmp_path: Path):
    rec = IncidentRecorder(storage_dir=tmp_path, speech_manager=None)
    packet = FramePacket(
        frame_id=20,
        captured_at=time.time(),
        jpeg_bytes=b"\xff\xd8\xff\xe0test_jpeg",
        width=640,
        height=480,
        source_id="test_cam",
        session_id="sess_test"
    )

    # Trigger with 0.1s timer to test auto-expiration
    res = rec.trigger_prealert(packet, countdown_seconds=0.1, language="ne")
    assert res["status"] == "prealert_started"

    # Wait for timer to expire
    time.sleep(0.3)

    # Check incident was captured
    incidents = rec.list_incidents()
    assert len(incidents) == 1
    assert "CONFIRMED_AFTER_COUNTDOWN" in incidents[0]["notes"]
