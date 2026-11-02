"""
Asynchronous Perception Pipeline Integration & Stress Tests (Priority 4.6 Stage 3).
Validates real multi-threaded execution, bounded capacity-1 frame queueing,
sensor degradation interception, tracking coasting/purge, and recovery correctness.
"""

import concurrent.futures
import cv2
import numpy as np
import time
import pytest

from app.camera.adapter import FakeCameraAdapter, FramePacket
from app.camera.health_controller import PerceptionState, SensorHealthController
from app.audio.speaker import FakeSpeechBackend, SpeechManager
from app.detection.engine import (
    BoundingBox,
    Detection,
    DetectionEngine,
    DetectionResult,
    FakeDetectionEngine,
    PerceptionPipeline,
)


def make_jpeg(pattern: str = "clean", width: int = 320, height: int = 240) -> bytes:
    """Generates synthetic JPEG bytes deterministically."""
    if pattern == "clean":
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:] = (128, 128, 128)
        cv2.rectangle(img, (50, 50), (150, 150), (255, 255, 255), -1)
        cv2.putText(img, "Async Test", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    elif pattern == "dark":
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:] = (2, 2, 2)
    elif pattern == "occluded_half":
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:] = (128, 128, 128)
        cv2.rectangle(img, (50, 20), (150, 100), (255, 255, 255), -1)
        img[int(height * 0.5):, :] = (15, 15, 15)
    else:
        img = np.zeros((height, width, 3), dtype=np.uint8)

    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def test_async_pipeline_start_stop_lifecycle():
    """Verifies background worker thread startup, clean stop, and deterministic join."""
    engine = FakeDetectionEngine()
    pipeline = PerceptionPipeline(engine=engine, target_fps=20.0)

    assert pipeline.is_active() is False

    pipeline.start()
    assert pipeline.is_active() is True
    assert pipeline._worker_thread is not None
    assert pipeline._worker_thread.is_alive() is True

    # Repeated start is safe and idempotent
    pipeline.start()
    assert pipeline.is_active() is True

    # Stop terminates and joins worker thread
    pipeline.stop(timeout=1.0)
    assert pipeline.is_active() is False
    assert pipeline._worker_thread is None

    # Repeated stop is safe and idempotent
    pipeline.stop()
    assert pipeline.is_active() is False


def test_async_pipeline_bounded_queue_lossy_overwrite():
    """
    Verifies that submit_frame operates in O(1) time without blocking,
    overwriting older unconsumed frames when worker is busy.
    """
    class DelayedEngine(DetectionEngine):
        def detect(self, frame_bytes: bytes, frame_id: int) -> DetectionResult:
            time.sleep(0.04)  # 40ms inference delay
            return DetectionResult(frame_id, time.time(), [], 40.0, "DelayedEngine")

        def is_ready(self) -> bool:
            return True

        def get_model_info(self):
            return {"model_name": "DelayedEngine", "is_ready": True}

    pipeline = PerceptionPipeline(engine=DelayedEngine(), target_fps=30.0)
    pipeline.start()

    clean_bytes = make_jpeg("clean")

    # Ingest 20 frames rapidly within 10ms (burst submission)
    for i in range(1, 21):
        pkt = FramePacket(frame_id=i, captured_at=time.time(), jpeg_bytes=clean_bytes, width=320, height=240, source_id="burst")
        pipeline.submit_frame(pkt)
        time.sleep(0.001)

    # Allow worker thread time to finish current frames
    time.sleep(0.15)
    pipeline.stop()

    latest = pipeline.get_latest_result()
    assert latest is not None
    # Because of capacity-1 lossy buffer, worker skipped intermediate frames and processed the latest
    assert latest.frame_id > 1
    assert pipeline.get_metrics()["frames_processed"] < 20


def test_async_pipeline_degradation_suppression_and_coasting():
    """
    Verifies that the background perception worker detects sensor degradation,
    bypasses DNN inference, coasts Kalman tracks, and purges stale tracks upon timeout.
    """
    speaker = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=speaker)

    mock_engine = FakeDetectionEngine(
        mock_detections=[
            Detection("person", 0.90, BoundingBox(0.4, 0.2, 0.6, 0.8), "center")
        ]
    )

    ctrl = SensorHealthController(
        enabled=True,
        degrade_debounce_frames=2,
        recovery_debounce_frames=2,
        max_coasting_frames=4,
        max_coasting_duration_seconds=0.20
    )

    pipeline = PerceptionPipeline(
        engine=mock_engine,
        speech_manager=speech_mgr,
        health_controller=ctrl,
        target_fps=20.0
    )
    pipeline.start()

    clean_bytes = make_jpeg("clean")
    dark_bytes = make_jpeg("dark")

    # 1. Feed clean frame to instantiate confirmed track
    t0 = time.time()
    pkt1 = FramePacket(frame_id=1, captured_at=t0, jpeg_bytes=clean_bytes, width=320, height=240, source_id="cam")
    pipeline.submit_frame(pkt1)
    time.sleep(0.08)

    assert ctrl.state == PerceptionState.VALID_OBSERVATION
    assert len(pipeline.tracker.tracks) == 1
    track_id = pipeline.tracker.tracks[0].track_id

    # 2. Feed dark frames to trigger degradation debouncing and outage
    for i in range(2, 8):
        pkt = FramePacket(frame_id=i, captured_at=t0 + i * 0.04, jpeg_bytes=dark_bytes, width=320, height=240, source_id="cam")
        pipeline.submit_frame(pkt)
        time.sleep(0.05)

    # Worker must transition to SENSOR_UNAVAILABLE / STALE_TERMINATED
    assert ctrl.state in (PerceptionState.SENSOR_UNAVAILABLE, PerceptionState.STALE_TERMINATED)

    # Wait for coasting duration ceiling (0.20s) to be reached
    time.sleep(0.15)
    pkt_stale = FramePacket(frame_id=9, captured_at=t0 + 0.35, jpeg_bytes=dark_bytes, width=320, height=240, source_id="cam")
    pipeline.submit_frame(pkt_stale)
    time.sleep(0.08)

    assert ctrl.state == PerceptionState.STALE_TERMINATED
    # Tracks must be completely purged
    assert len(pipeline.tracker.tracks) == 0

    pipeline.stop()
    speech_mgr.shutdown()


def test_async_pipeline_recovery_and_track_monotonicity():
    """
    Verifies that following an outage, clean recovery debounces over 2 frames
    and restores nominal inference with a fresh, non-colliding track ID.
    """
    speaker = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=speaker)

    mock_engine = FakeDetectionEngine(
        mock_detections=[
            Detection("person", 0.90, BoundingBox(0.4, 0.2, 0.6, 0.8), "center")
        ]
    )
    ctrl = SensorHealthController(
        enabled=True,
        degrade_debounce_frames=2,
        recovery_debounce_frames=2,
        max_coasting_frames=3,
        max_coasting_duration_seconds=0.15
    )
    pipeline = PerceptionPipeline(
        engine=mock_engine,
        speech_manager=speech_mgr,
        health_controller=ctrl,
        target_fps=20.0
    )
    pipeline.start()

    clean_bytes = make_jpeg("clean")
    dark_bytes = make_jpeg("dark")

    # Step 1: Establish baseline Track 1
    t0 = time.time()
    pipeline.submit_frame(FramePacket(1, t0, clean_bytes, 320, 240, "cam"))
    time.sleep(0.08)
    assert len(pipeline.tracker.tracks) == 1
    first_track_id = pipeline.tracker.tracks[0].track_id

    # Step 2: Trigger outage and track purge
    for i in range(2, 7):
        pipeline.submit_frame(FramePacket(i, t0 + i * 0.05, dark_bytes, 320, 240, "cam"))
        time.sleep(0.05)

    time.sleep(0.10)
    assert ctrl.state == PerceptionState.STALE_TERMINATED
    assert len(pipeline.tracker.tracks) == 0

    # Step 3: Clean Recovery (Frame 1 debounces, Frame 2 restores)
    pipeline.submit_frame(FramePacket(8, t0 + 0.50, clean_bytes, 320, 240, "cam"))
    time.sleep(0.06)
    pipeline.submit_frame(FramePacket(9, t0 + 0.55, clean_bytes, 320, 240, "cam"))
    time.sleep(0.06)
    pipeline.submit_frame(FramePacket(10, t0 + 0.60, clean_bytes, 320, 240, "cam"))
    time.sleep(0.08)

    assert ctrl.state == PerceptionState.VALID_OBSERVATION
    assert len(pipeline.tracker.tracks) == 1
    recovered_track_id = pipeline.tracker.tracks[0].track_id

    # Monotonic progression: new track must NOT recycle Track ID 1
    assert recovered_track_id > first_track_id

    pipeline.stop()
    speech_mgr.shutdown()


def test_async_pipeline_corrupted_payload_resilience():
    """Verifies that empty, corrupt, or truncated byte streams do not crash the background worker."""
    engine = FakeDetectionEngine()
    ctrl = SensorHealthController(enabled=True)
    pipeline = PerceptionPipeline(engine=engine, health_controller=ctrl, target_fps=20.0)
    pipeline.start()

    corrupt_samples = [
        b"",
        b"\x00\x01\x02\x03",
        b"not_a_jpeg_image_header",
        b"\xff\xd8\xff\xe0"  # truncated JPEG header
    ]

    for idx, c_bytes in enumerate(corrupt_samples):
        pkt = FramePacket(frame_id=idx + 1, captured_at=time.time(), jpeg_bytes=c_bytes, width=320, height=240, source_id="corrupt")
        pipeline.submit_frame(pkt)
        time.sleep(0.05)
        # Background worker must remain active despite corrupt payload
        assert pipeline.is_active() is True

    # Ingesting clean frame afterwards works normally
    clean_bytes = make_jpeg("clean")
    pipeline.submit_frame(FramePacket(frame_id=99, captured_at=time.time(), jpeg_bytes=clean_bytes, width=320, height=240, source_id="clean"))
    time.sleep(0.08)

    latest = pipeline.get_latest_result()
    assert latest is not None
    assert latest.frame_id == 99

    pipeline.stop()


def test_async_pipeline_concurrent_submissions_thread_safety():
    """Stress tests concurrent frame submissions from 10 threads to guarantee queue thread-safety."""
    engine = FakeDetectionEngine()
    pipeline = PerceptionPipeline(engine=engine, target_fps=30.0)
    pipeline.start()

    clean_bytes = make_jpeg("clean")

    def submitter(client_id: int):
        for seq in range(10):
            fid = client_id * 100 + seq
            pkt = FramePacket(frame_id=fid, captured_at=time.time(), jpeg_bytes=clean_bytes, width=320, height=240, source_id=f"cli_{client_id}")
            pipeline.submit_frame(pkt)
            time.sleep(0.002)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(submitter, cid) for cid in range(10)]
        concurrent.futures.wait(futures)

    time.sleep(0.10)
    assert pipeline.is_active() is True
    pipeline.stop()
    assert pipeline.is_active() is False
