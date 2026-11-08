"""Tests for NepalOverheadWireDetector integration into PerceptionPipeline."""
import time
import cv2
import numpy as np
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager
from app.camera.adapter import FramePacket
from app.detection.engine import PerceptionPipeline, FakeDetectionEngine
from app.detection.nepal_hazards import NepalOverheadWireDetector


def create_wire_frame_bytes() -> bytes:
    """Generates synthetic JPEG frame with dark sagging wires in upper 35% clearance zone."""
    frame = np.full((480, 640, 3), 180, dtype=np.uint8)  # Bright sky background
    # Draw multiple prominent sagging horizontal wires across top 150px
    for line_y in (40, 65, 90, 115):
        cv2.line(frame, (10, line_y), (630, line_y + 4), (20, 20, 20), 3)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return buf.tobytes()


def create_clear_frame_bytes() -> bytes:
    """Generates clean frame without overhead wires."""
    frame = np.full((480, 640, 3), 180, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", frame)
    assert ok
    return buf.tobytes()


def test_perception_pipeline_has_wire_detector():
    pipeline = PerceptionPipeline(engine=FakeDetectionEngine())
    assert hasattr(pipeline, "wire_detector")
    assert isinstance(pipeline.wire_detector, NepalOverheadWireDetector)


def test_perception_pipeline_detects_and_announces_wire_hazard():
    fake_speech = FakeSpeechBackend()
    speech_mgr = SpeechManager(backend=fake_speech)
    speech_mgr.start()

    pipeline = PerceptionPipeline(
        engine=FakeDetectionEngine(mock_detections=[]),
        speech_manager=speech_mgr,
        language="ne"
    )
    pipeline.start()

    try:
        wire_jpeg = create_wire_frame_bytes()
        packet = FramePacket(
            frame_id=1,
            captured_at=time.time(),
            jpeg_bytes=wire_jpeg,
            width=640,
            height=480,
            source_id="test_cam",
            session_id="test_sess"
        )

        res = pipeline.process_frame(packet)
        assert res is not None, "process_frame returned None"
        assert res.overhead_wire is not None, "Overhead wire hazard was not detected in result"
        assert res.overhead_wire["detected"] is True
        assert res.overhead_wire["hazard_class"] == "dangling_wire"
        assert "तार" in res.overhead_wire["message"]

        # Verify speech dispatch
        time.sleep(0.1)
        with fake_speech._lock:
            history = list(fake_speech.spoken_history)
        assert len(history) > 0
        assert any("तार" in h or "Caution" in h for h in history)

    finally:
        pipeline.stop()
        speech_mgr.shutdown()


def test_perception_pipeline_ignores_clear_sky():
    fake_speech = FakeSpeechBackend()
    speech_mgr = SpeechManager(backend=fake_speech)
    speech_mgr.start()

    pipeline = PerceptionPipeline(
        engine=FakeDetectionEngine(mock_detections=[]),
        speech_manager=speech_mgr,
        language="ne"
    )
    pipeline.start()

    try:
        clear_jpeg = create_clear_frame_bytes()
        packet = FramePacket(
            frame_id=2,
            captured_at=time.time(),
            jpeg_bytes=clear_jpeg,
            width=640,
            height=480,
            source_id="test_cam",
            session_id="test_sess"
        )

        res = pipeline.process_frame(packet)
        assert res is not None
        assert res.overhead_wire is None

    finally:
        pipeline.stop()
        speech_mgr.shutdown()
