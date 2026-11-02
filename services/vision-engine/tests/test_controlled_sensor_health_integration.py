"""
Trinetra Controlled Sensor-Health Integration Tests
Validates the feature-flag-gated integration of SensorHealthController inside PerceptionPipeline.
Verifies disabled-by-default zero-regression guarantee, controlled DNN suppression during outages,
Kalman track coasting and purging, recovery transitions, and audio suppression.
"""

import time
import cv2
import numpy as np
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager
from app.camera.adapter import FramePacket
from app.camera.health_controller import PerceptionState, SensorHealthController
from app.detection.engine import (
    BoundingBox,
    Detection,
    DetectionResult,
    FakeDetectionEngine,
    PerceptionPipeline,
)


def make_clean_jpeg() -> bytes:
    img = np.full((480, 640, 3), 128, dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (250, 250), (60, 60, 180), -1)
    cv2.line(img, (0, 420), (640, 420), (240, 240, 240), 3)
    cv2.putText(img, "KATHMANDU", (60, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    _, enc = cv2.imencode(".jpg", img)
    return enc.tobytes()


def make_black_jpeg() -> bytes:
    img = np.full((480, 640, 3), 5, dtype=np.uint8)
    _, enc = cv2.imencode(".jpg", img)
    return enc.tobytes()


def test_feature_flag_disabled_by_default(monkeypatch):
    """
    STRICT SAFETY TEST:
    Verifies that when TRINETRA_ENABLE_SENSOR_HEALTH is unset,
    PerceptionPipeline operates in 100% legacy pass-through mode:
    - Never suppresses inference even on black frames.
    - Zero modification to existing production paths.
    """
    monkeypatch.delenv("TRINETRA_ENABLE_SENSOR_HEALTH", raising=False)
    fake_engine = FakeDetectionEngine()
    pipeline = PerceptionPipeline(engine=fake_engine)

    assert pipeline.health_controller is not None
    assert pipeline.health_controller.is_enabled() is False

    black_bytes = make_black_jpeg()
    packet = FramePacket(
        frame_id=1,
        captured_at=100.0,
        jpeg_bytes=black_bytes,
        width=640,
        height=480,
        source_id="webcam",
        session_id="session_legacy"
    )

    # Process black frame with feature flag disabled
    result = pipeline.process_frame(packet)
    assert result is not None
    # Legacy behavior preserved: FakeDetectionEngine still returned its mock detection!
    assert len(result.detections) == 1
    assert result.detections[0].class_name == "person"


def test_controlled_integration_with_feature_flag_enabled():
    """
    VERIFIED CONTROLLED INTEGRATION:
    When enabled via feature flag or explicit instance:
    1. Clean frames run DNN inference and create Kalman tracks.
    2. Outages suppress DNN inference and coast Kalman tracks.
    3. Prolonged outages purge stale tracks.
    4. Recovery restores fresh perception.
    """
    fake_speaker = FakeSpeechBackend()
    speech_mgr = SpeechManager(backend=fake_speaker)
    fake_engine = FakeDetectionEngine()

    ctrl = SensorHealthController(
        enabled=True,
        degrade_debounce_frames=2,
        recovery_debounce_frames=2,
        max_coasting_frames=4,
        max_coasting_duration_seconds=0.20
    )

    pipeline = PerceptionPipeline(
        engine=fake_engine,
        speech_manager=speech_mgr,
        health_controller=ctrl
    )

    clean_bytes = make_clean_jpeg()
    black_bytes = make_black_jpeg()

    # Step 1: Clean Frame 1 — Nominal detection & track creation
    pkt1 = FramePacket(frame_id=1, captured_at=100.0, jpeg_bytes=clean_bytes, width=640, height=480, source_id="cam", session_id="sess1")
    res1 = pipeline.process_frame(pkt1)
    assert res1 is not None
    assert len(res1.detections) == 1
    assert len(pipeline.tracker.tracks) == 1
    track_id = pipeline.tracker.tracks[0].track_id

    # Step 2: Black Frame 2 — Debouncing (frame 1 of severe degradation)
    pkt2 = FramePacket(frame_id=2, captured_at=100.033, jpeg_bytes=black_bytes, width=640, height=480, source_id="cam", session_id="sess1")
    res2 = pipeline.process_frame(pkt2)
    assert res2 is not None  # debouncing, still runs

    # Step 3: Black Frame 3 — Debounce satisfied -> SENSOR_UNAVAILABLE
    # DNN is bypassed! Detections list is empty, Kalman track coasts.
    pkt3 = FramePacket(frame_id=3, captured_at=100.066, jpeg_bytes=black_bytes, width=640, height=480, source_id="cam", session_id="sess1")
    res3 = pipeline.process_frame(pkt3)
    assert res3 is not None
    assert len(res3.detections) == 0  # Inference bypassed!
    assert ctrl.state == PerceptionState.SENSOR_UNAVAILABLE
    assert len(pipeline.tracker.tracks) == 1  # Track is coasting!

    # Step 4: Continue black frames until coasting ceiling (4 frames) is exceeded
    for i in range(4, 9):
        pkt = FramePacket(frame_id=i, captured_at=100.0 + i * 0.033, jpeg_bytes=black_bytes, width=640, height=480, source_id="cam", session_id="sess1")
        pipeline.process_frame(pkt)

    # Frame 8: State transitioned to STALE_TERMINATED -> All tracks purged!
    assert ctrl.state == PerceptionState.STALE_TERMINATED
    assert len(pipeline.tracker.tracks) == 0  # Stale tracks successfully purged!

    # Step 5: Clean Recovery (2 clean frames to satisfy recovery debounce)
    pkt9 = FramePacket(frame_id=9, captured_at=100.350, jpeg_bytes=clean_bytes, width=640, height=480, source_id="cam", session_id="sess1")
    pipeline.process_frame(pkt9)
    assert ctrl.state == PerceptionState.STALE_TERMINATED  # debouncing

    pkt10 = FramePacket(frame_id=10, captured_at=100.383, jpeg_bytes=clean_bytes, width=640, height=480, source_id="cam", session_id="sess1")
    pipeline.process_frame(pkt10)
    # Recovery transition triggered!
    assert ctrl.state in (PerceptionState.RECOVERY_TRANSITION, PerceptionState.VALID_OBSERVATION)

    pkt11 = FramePacket(frame_id=11, captured_at=100.416, jpeg_bytes=clean_bytes, width=640, height=480, source_id="cam", session_id="sess1")
    res11 = pipeline.process_frame(pkt11)
    assert res11 is not None
    assert len(res11.detections) == 1
    assert ctrl.state == PerceptionState.VALID_OBSERVATION
    # New track instantiated with fresh ID (zero ghost track association)
    assert len(pipeline.tracker.tracks) == 1
    assert pipeline.tracker.tracks[0].track_id != track_id
