import cv2
import numpy as np
import pytest
from app.detection.ground_hazard import GroundHazardDetector, GroundHazard
from app.detection.engine import PerceptionPipeline, FakeDetectionEngine
from app.camera.adapter import FramePacket
import time


def test_ground_hazard_clear_pavement():
    detector = GroundHazardDetector()
    # Uniform gray road surface
    frame = np.full((480, 640, 3), 130, dtype=np.uint8)
    hazard = detector.analyze(frame)
    assert not hazard.detected
    assert hazard.hazard_type == "none"


def test_ground_hazard_pothole_detection():
    detector = GroundHazardDetector()
    frame = np.full((480, 640, 3), 140, dtype=np.uint8)
    # Inject dark pothole in bottom walking corridor (y: 320..420, x: 260..380)
    cv2.circle(frame, (320, 380), 50, (20, 20, 20), -1)

    hazard = detector.analyze(frame)
    assert hazard.detected
    assert hazard.hazard_type in ("pothole", "open_trench")
    assert "खाल्डो" in hazard.message_ne or "ढल" in hazard.message_ne
    assert hazard.bounding_box is not None


def test_ground_hazard_pipeline_integration():
    pipeline = PerceptionPipeline(engine=FakeDetectionEngine())
    pipeline.start()
    try:
        # Generate frame with pothole
        frame = np.full((480, 640, 3), 140, dtype=np.uint8)
        cv2.circle(frame, (320, 380), 60, (15, 15, 15), -1)
        _, jpeg_bytes = cv2.imencode(".jpg", frame)

        packet = FramePacket(
            frame_id=1,
            captured_at=time.time(),
            jpeg_bytes=jpeg_bytes.tobytes(),
            width=640,
            height=480,
            source_id="test_cam",
            session_id="test_session"
        )
        res = pipeline.process_frame(packet)
        assert res is not None
        assert res.ground_hazard is not None
        assert res.ground_hazard["detected"] is True
        assert "खाल्डो" in res.ground_hazard["message"] or "ढल" in res.ground_hazard["message"]
    finally:
        pipeline.stop()


def test_ground_hazard_uncertainty_in_extreme_darkness():
    """Verifies that pitch dark environments trigger an explicit uncertainty warning rather than claiming 'clear'."""
    detector = GroundHazardDetector()
    frame = np.full((480, 640, 3), 10, dtype=np.uint8)  # Very dark alley
    hazard = detector.analyze(frame)
    assert hazard.detected is True
    assert hazard.hazard_type == "uncertain_terrain"
    assert "अँध्यारो" in hazard.message_ne


def test_ground_hazard_uncertainty_in_extreme_glare():
    """Verifies that blinding direct sun glare triggers an explicit probe advisory."""
    detector = GroundHazardDetector()
    frame = np.full((480, 640, 3), 250, dtype=np.uint8)  # Blinding direct glare
    hazard = detector.analyze(frame)
    assert hazard.detected is True
    assert hazard.hazard_type == "uncertain_terrain"
    assert "चमक" in hazard.message_ne
