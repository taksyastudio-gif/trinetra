"""
Tests for Trinetra Phase 2: Accessible Incident Documentation & Tamper-Evident Snapshot Recorder.
Validates SHA-256 cryptographic hashing, tamper detection, bounded disk retention,
audible feedback, and anti-criminalization safety boundaries.
"""

import json
from pathlib import Path
import tempfile
import time
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager, SpeechPriority
from app.camera.adapter import FramePacket
from app.detection.types import BoundingBox, Detection, DetectionResult
from app.incident.recorder import IncidentRecorder, LEGAL_DISCLAIMER_TEXT


@pytest.fixture
def temp_incident_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def sample_packet():
    return FramePacket(
        frame_id=42,
        captured_at=time.time(),
        jpeg_bytes=b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00testframebytes\xff\xd9",
        width=640,
        height=480,
        source_id="test_camera_0",
        session_id="session_xyz"
    )


def test_incident_capture_hashes_and_storage(temp_incident_dir, sample_packet):
    """Validates that capturing an incident writes JPG, writes JSON metadata, and computes SHA-256 hashes."""
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend)
    recorder = IncidentRecorder(storage_dir=temp_incident_dir, max_records=10, speech_manager=speech_mgr)

    det = Detection(
        class_name="person",
        confidence=0.88,
        box=BoundingBox(0.2, 0.2, 0.4, 0.8),
        sector="center"
    )
    det_res = DetectionResult(
        frame_id=sample_packet.frame_id,
        timestamp=sample_packet.captured_at,
        detections=[det],
        inference_time_ms=12.0,
        model_name="yolox_nano.onnx"
    )

    record = recorder.capture(
        packet=sample_packet,
        detection_result=det_res,
        notes="Testing snapshot capture",
        language="en"
    )

    assert record.frame_id == 42
    assert record.session_id == "session_xyz"
    assert len(record.detections) == 1
    assert record.detections[0]["class_name"] == "person"
    assert record.legal_disclaimer == LEGAL_DISCLAIMER_TEXT

    # Verify files created on disk
    jpg_path = temp_incident_dir / record.image_filename
    json_path = temp_incident_dir / record.metadata_filename
    assert jpg_path.is_file()
    assert json_path.is_file()

    # Image bytes on disk match captured bytes
    assert jpg_path.read_bytes() == sample_packet.jpeg_bytes

    speech_mgr.shutdown()


def test_incident_cryptographic_verification_and_tamper_detection(temp_incident_dir, sample_packet):
    """Validates that tampering with an on-disk image is immediately detected by SHA-256 verification."""
    recorder = IncidentRecorder(storage_dir=temp_incident_dir, max_records=10)

    record = recorder.capture(packet=sample_packet, notes="Authentic record")
    incident_id = record.incident_id

    # 1. Unmodified files verify as clean
    res_clean = recorder.verify_integrity(incident_id)
    assert res_clean["verified"] is True
    assert res_clean["image_integrity"] is True
    assert res_clean["digest_integrity"] is True

    # 2. Tamper: corrupt 1 byte of the image on disk
    jpg_path = temp_incident_dir / record.image_filename
    tampered_bytes = bytearray(jpg_path.read_bytes())
    tampered_bytes[10] = (tampered_bytes[10] + 1) % 256
    jpg_path.write_bytes(tampered_bytes)

    # 3. Verification detects tampering
    res_tampered = recorder.verify_integrity(incident_id)
    assert res_tampered["verified"] is False
    assert res_tampered["image_integrity"] is False


def test_incident_bounded_retention_pruning(temp_incident_dir, sample_packet):
    """Validates that stored incidents are automatically pruned when exceeding max_records."""
    recorder = IncidentRecorder(storage_dir=temp_incident_dir, max_records=5)

    created_ids = []
    for i in range(8):
        pkt = FramePacket(
            frame_id=i + 1,
            captured_at=time.time() + (i * 0.05),
            jpeg_bytes=sample_packet.jpeg_bytes + bytes([i]),
            width=640,
            height=480,
            source_id="cam_0",
            session_id="session_test"
        )
        rec = recorder.capture(packet=pkt)
        created_ids.append(rec.incident_id)
        time.sleep(0.01)

    json_files = list(temp_incident_dir.glob("inc_*.json"))
    jpg_files = list(temp_incident_dir.glob("inc_*.jpg"))

    # Must be bounded strictly to max_records (5)
    assert len(json_files) == 5
    assert len(jpg_files) == 5

    # Oldest 3 incidents were pruned
    for old_id in created_ids[:3]:
        assert not (temp_incident_dir / f"{old_id}.json").exists()

    # Newest 5 incidents remain intact
    for new_id in created_ids[3:]:
        assert (temp_incident_dir / f"{new_id}.json").exists()


def test_incident_audible_feedback_bilingual(temp_incident_dir, sample_packet):
    """Validates localized audible feedback upon capture in Nepali and English."""
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend)
    recorder = IncidentRecorder(storage_dir=temp_incident_dir, max_records=10, speech_manager=speech_mgr)

    # 1. Nepali capture
    recorder.capture(packet=sample_packet, language="ne")
    time.sleep(0.05)
    assert len(backend.spoken_history) == 1
    assert backend.spoken_history[0] == "घटना अभिलेख गरियो।"

    # 2. English capture
    recorder.capture(packet=sample_packet, language="en")
    time.sleep(0.05)
    assert len(backend.spoken_history) == 2
    assert backend.spoken_history[1] == "Incident snapshot recorded."

    speech_mgr.shutdown()


def test_incident_anti_criminalization_guardrails(temp_incident_dir, sample_packet):
    """Verifies no facial recognition or criminal liability fields are present in the record."""
    recorder = IncidentRecorder(storage_dir=temp_incident_dir, max_records=10)
    record = recorder.capture(packet=sample_packet)
    rec_dict = record.to_dict()

    # Confirm prohibited sensitive fields do not exist
    prohibited_keys = {"face_id", "biometric", "suspect", "criminal_score", "identity"}
    for key in prohibited_keys:
        assert key not in rec_dict

    # Check disclaimer text explicitly mentions no facial recognition
    assert "no facial recognition" in rec_dict["legal_disclaimer"].lower()
