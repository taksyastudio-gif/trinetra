"""
Trinetra Vision Engine API & Camera Adapter Automated Tests
Validates health checks, camera lifecycle, frame encoding, monotonic frame sequencing,
session identification, and error boundaries using the FakeCameraAdapter.
"""

import os
import sys
import threading
import time
from typing import Any, Dict
import pytest

# Ensure services/vision-engine is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.camera.adapter import (
    CameraInitializationError,
    CameraNotActiveError,
    FakeCameraAdapter,
)
from app.audio.speaker import FakeSpeechBackend, SpeechPriority, SpeechManager
from app.detection.engine import (
    BoundingBox,
    Detection,
    DetectionEngine,
    DetectionResult,
    FakeDetectionEngine,
    classify_sector,
)
from socket_free_client import SocketFreeTestClient as TestClient
from app.main import create_app, camera_manager


@pytest.fixture
def fake_adapter():
    """Provides a fresh, clean FakeCameraAdapter."""
    adapter = FakeCameraAdapter(width=320, height=240)
    yield adapter
    if adapter.is_active():
        adapter.stop()


@pytest.fixture
def test_client(fake_adapter):
    """Provides a FastAPI TestClient configured with the fake adapter."""
    from socket_free_client import SocketFreeTestClient as TestClient
    app = create_app(adapter=fake_adapter)
    with TestClient(app) as client:
        yield client
    if fake_adapter.is_active():
        fake_adapter.stop()


def test_health_endpoint(test_client):
    """GET /api/health returns 200 OK and service identifiers."""
    response = test_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "trinetra-vision-engine"
    assert "version" in data


def test_camera_status_inactive(test_client):
    """GET /api/camera/status correctly reflects inactive camera state."""
    response = test_client.get("/api/camera/status")
    assert response.status_code == 200
    data = response.json()
    assert data["active"] is False
    assert data["frames_captured"] == 0
    assert data["adapter"] == "FakeCameraAdapter"
    assert data["session_id"] is None
    assert "perception_health" in data
    health = data["perception_health"]
    assert health is not None
    assert health["state"] == "VALID_OBSERVATION"
    assert health["status"] == "NORMAL"
    assert health["is_degraded"] is False
    assert "not safety certified" in health["disclaimer"].lower()


def test_camera_frame_when_inactive_returns_409(test_client):
    """GET /api/camera/frame returns 409 Conflict when camera is not started."""
    response = test_client.get("/api/camera/frame")
    assert response.status_code == 409
    data = response.json()
    assert "detail" in data
    assert "not active" in data["detail"].lower()


def test_camera_start_and_status(test_client):
    """POST /api/camera/start successfully transitions camera to active with session ID."""
    start_resp = test_client.post("/api/camera/start")
    assert start_resp.status_code == 200
    data = start_resp.json()
    assert data["active"] is True
    assert data["status"] == "started"
    assert data["session_id"] is not None
    assert len(data["session_id"]) > 10

    status_resp = test_client.get("/api/camera/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["active"] is True
    assert status_data["session_id"] == data["session_id"]


def test_camera_frame_retrieval_and_headers(test_client):
    """GET /api/camera/frame returns genuine JPEG binary bytes and monotonic telemetry headers."""
    start_resp = test_client.post("/api/camera/start")
    session_id = start_resp.json()["session_id"]

    # First frame
    frame_resp1 = test_client.get("/api/camera/frame")
    assert frame_resp1.status_code == 200
    assert frame_resp1.headers["content-type"] == "image/jpeg"
    assert frame_resp1.headers["x-frame-id"] == "1"
    assert "x-captured-at" in frame_resp1.headers
    assert frame_resp1.headers["x-session-id"] == session_id

    # Verify standard JPEG header (SOI marker 0xFFD8)
    content = frame_resp1.content
    assert len(content) > 10
    assert content[:2] == b"\xff\xd8"
    assert content[-2:] == b"\xff\xd9"  # EOI marker

    # Second frame: verifies monotonically increasing frame ID
    frame_resp2 = test_client.get("/api/camera/frame")
    assert frame_resp2.status_code == 200
    assert frame_resp2.headers["x-frame-id"] == "2"


def test_camera_stop_and_session_clearing(test_client):
    """POST /api/camera/stop releases camera hardware lock and clears session ID."""
    test_client.post("/api/camera/start")
    assert test_client.get("/api/camera/status").json()["active"] is True

    stop_resp = test_client.post("/api/camera/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["active"] is False
    assert stop_resp.json()["session_id"] is None

    # Status reflects inactive
    status_data = test_client.get("/api/camera/status").json()
    assert status_data["active"] is False
    assert status_data["session_id"] is None

    # Subsequent frame request is blocked
    frame_resp = test_client.get("/api/camera/frame")
    assert frame_resp.status_code == 409


def test_repeated_start_and_stop_safety(test_client):
    """Repeated calls to /api/camera/start and /api/camera/stop must not crash or leak resources."""
    # First start
    r1 = test_client.post("/api/camera/start")
    assert r1.status_code == 200
    assert r1.json()["status"] == "started"

    # Second redundant start: should return already_running gracefully
    r2 = test_client.post("/api/camera/start")
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_running"

    # First stop
    s1 = test_client.post("/api/camera/stop")
    assert s1.status_code == 200

    # Second redundant stop: must be idempotent and succeed
    s2 = test_client.post("/api/camera/stop")
    assert s2.status_code == 200
    assert s2.json()["status"] == "stopped"


def test_camera_initialization_failure():
    """Service returns 503 Service Unavailable with clear message when hardware fails to open."""
    from socket_free_client import SocketFreeTestClient as TestClient
    faulty_adapter = FakeCameraAdapter(should_fail_init=True)
    app = create_app(adapter=faulty_adapter)

    with TestClient(app) as client:
        resp = client.post("/api/camera/start")
        assert resp.status_code == 503
        data = resp.json()
        assert "detail" in data
        assert "Simulated camera hardware initialization failure" in data["detail"]


def test_camera_capture_failure():
    """Service returns 500 Internal Server Error when frame reading stalls."""
    from socket_free_client import SocketFreeTestClient as TestClient
    broken_capture_adapter = FakeCameraAdapter(should_fail_capture=True)
    app = create_app(adapter=broken_capture_adapter)

    with TestClient(app) as client:
        client.post("/api/camera/start")
        resp = client.get("/api/camera/frame")
        assert resp.status_code == 500


def test_concurrent_start_requests(fake_adapter):
    """Concurrent calls to start_camera from multiple threads are safely serialized."""
    import concurrent.futures
    from socket_free_client import SocketFreeTestClient as TestClient
    app = create_app(adapter=fake_adapter)

    with TestClient(app) as client:
        def invoke_start():
            return client.post("/api/camera/start")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(invoke_start) for _ in range(8)]
            responses = [f.result() for f in futures]

        # All responses should return 200 OK
        assert all(r.status_code == 200 for r in responses)

        # Exactly one call should be 'started', the rest 'already_running'
        statuses = [r.json()["status"] for r in responses]
        assert statuses.count("started") == 1
        assert statuses.count("already_running") == 7

        # All responses should share the exact same session_id
        session_ids = {r.json()["session_id"] for r in responses}
        assert len(session_ids) == 1
        assert None not in session_ids


def test_concurrent_stop_requests(fake_adapter):
    """Concurrent calls to stop_camera from multiple threads execute idempotently without errors."""
    import concurrent.futures
    from socket_free_client import SocketFreeTestClient as TestClient
    app = create_app(adapter=fake_adapter)

    with TestClient(app) as client:
        client.post("/api/camera/start")
        assert client.get("/api/camera/status").json()["active"] is True

        def invoke_stop():
            return client.post("/api/camera/stop")

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(invoke_stop) for _ in range(8)]
            responses = [f.result() for f in futures]

        assert all(r.status_code == 200 for r in responses)
        assert all(r.json()["status"] == "stopped" for r in responses)
        assert client.get("/api/camera/status").json()["active"] is False


def test_latest_frame_overwrite_and_dropped_frame_accounting(fake_adapter):
    """
    Capacity-1 buffer correctly overwrites unconsumed frames and increments dropped_frames count.
    """
    fake_adapter.start()

    # Push 3 frames consecutively without consuming
    p1 = fake_adapter.push_frame()
    assert p1.frame_id == 1
    assert p1.dropped_frames == 0

    p2 = fake_adapter.push_frame()
    assert p2.frame_id == 2
    assert p2.dropped_frames == 1  # 1 frame was overwritten/dropped

    p3 = fake_adapter.push_frame()
    assert p3.frame_id == 3
    assert p3.dropped_frames == 2  # 2 frames overwritten/dropped

    # Client now consumes the latest frame: should receive p3 (capacity-1)
    consumed = fake_adapter.capture_packet()
    assert consumed.frame_id == 3
    assert consumed.dropped_frames == 2

    # Status reflects the dropped frames
    status = fake_adapter.get_status()
    assert status["frames_captured"] == 3
    assert status["dropped_frames"] == 2


def test_frame_id_and_monotonic_timestamp_progression(fake_adapter):
    """Monotonic sequence and timestamps progress forward across successive frames."""
    fake_adapter.start()
    f1 = fake_adapter.capture_packet()
    f2 = fake_adapter.capture_packet()
    f3 = fake_adapter.capture_packet()

    assert f1.frame_id == 1
    assert f2.frame_id == 2
    assert f3.frame_id == 3
    assert f1.captured_at <= f2.captured_at <= f3.captured_at


def test_authentication_disabled_by_default(fake_adapter):
    """When no session token is configured, requests succeed without authorization headers."""
    from socket_free_client import SocketFreeTestClient as TestClient
    app = create_app(adapter=fake_adapter, session_token=None)

    with TestClient(app) as client:
        # Health check is public
        assert client.get("/api/health").status_code == 200

        # Camera endpoints pass without token
        status_resp = client.get("/api/camera/status")
        assert status_resp.status_code == 200

        start_resp = client.post("/api/camera/start")
        assert start_resp.status_code == 200

        frame_resp = client.get("/api/camera/frame")
        assert frame_resp.status_code == 200

        stop_resp = client.post("/api/camera/stop")
        assert stop_resp.status_code == 200


def test_authentication_enabled_enforces_token(fake_adapter):
    """When session token is enabled, protected endpoints reject missing or invalid tokens."""
    from socket_free_client import SocketFreeTestClient as TestClient
    configured_token = "trinetra-test-auth-token-123"
    app = create_app(adapter=fake_adapter, session_token=configured_token)

    with TestClient(app) as client:
        # Public health check remains accessible without token
        assert client.get("/api/health").status_code == 200

        # Protected endpoints reject missing token
        assert client.get("/api/camera/status").status_code == 401
        assert client.post("/api/camera/start").status_code == 401
        assert client.post("/api/camera/stop").status_code == 401
        assert client.get("/api/camera/frame").status_code == 401

        # Protected endpoints reject invalid token
        wrong_headers = {"X-Trinetra-Session-Token": "invalid-token"}
        assert client.get("/api/camera/status", headers=wrong_headers).status_code == 401
        assert client.post("/api/camera/start", headers=wrong_headers).status_code == 401

        # Protected endpoints accept valid token
        valid_headers = {"X-Trinetra-Session-Token": configured_token}
        status_resp = client.get("/api/camera/status", headers=valid_headers)
        assert status_resp.status_code == 200

        start_resp = client.post("/api/camera/start", headers=valid_headers)
        assert start_resp.status_code == 200

        frame_resp = client.get("/api/camera/frame", headers=valid_headers)
        assert frame_resp.status_code == 200
        assert frame_resp.headers["x-frame-id"] == "1"

        stop_resp = client.post("/api/camera/stop", headers=valid_headers)
        assert stop_resp.status_code == 200


def test_empty_or_whitespace_session_token_disables_auth(fake_adapter):
    """Empty or whitespace-only token configuration is normalized to disabled."""
    from socket_free_client import SocketFreeTestClient as TestClient
    app = create_app(adapter=fake_adapter, session_token="   ")

    with TestClient(app) as client:
        assert client.get("/api/camera/status").status_code == 200


def test_camera_devices_enumeration(fake_adapter):
    """GET /api/camera/devices lists available camera devices with status."""
    from socket_free_client import SocketFreeTestClient as TestClient
    app = create_app(adapter=fake_adapter)

    with TestClient(app) as client:
        resp = client.get("/api/camera/devices")
        assert resp.status_code == 200
        devices = resp.json()
        assert isinstance(devices, list)
        assert len(devices) >= 1
        assert devices[0]["index"] == 0
        assert devices[0]["is_available"] is True
        assert devices[0]["status"] == "available"


def test_start_camera_with_specific_device(fake_adapter):
    """POST /api/camera/start with camera_index starts the requested device."""
    from socket_free_client import SocketFreeTestClient as TestClient
    app = create_app(adapter=fake_adapter)

    with TestClient(app) as client:
        start_resp = client.post("/api/camera/start", json={"camera_index": 0})
        assert start_resp.status_code == 200
        assert start_resp.json()["active"] is True
        assert start_resp.json()["status"] == "started"

        status_resp = client.get("/api/camera/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["active"] is True


def test_speech_announce_enqueues_and_cooldown_suppresses(fake_adapter):
    """Speech announcements enqueue properly, with rapid duplicate phrases suppressed by cooldown."""
    from socket_free_client import SocketFreeTestClient as TestClient
    fake_speech = FakeSpeechBackend()
    app = create_app(adapter=fake_adapter, speech_backend=fake_speech)

    with TestClient(app) as client:
        # First announcement: should enqueue
        r1 = client.post("/api/speech/announce", json={"text": "Chair ahead", "priority": "spatial_navigation"})
        assert r1.status_code == 200
        assert r1.json()["enqueued"] is True

        # Immediate duplicate announcement: should be suppressed by cooldown
        r2 = client.post("/api/speech/announce", json={"text": "Chair ahead", "priority": "spatial_navigation"})
        assert r2.status_code == 200
        assert r2.json()["enqueued"] is False

        # Urgent hazard interruption: should bypass cooldown
        r3 = client.post("/api/speech/announce", json={"text": "Chair ahead", "priority": "critical_hazard", "interrupt": True})
        assert r3.status_code == 200
        assert r3.json()["enqueued"] is True


def test_speech_mute_and_stop_controls(fake_adapter):
    """Mute and stop endpoints correctly update speech manager state."""
    from socket_free_client import SocketFreeTestClient as TestClient
    fake_speech = FakeSpeechBackend()
    app = create_app(adapter=fake_adapter, speech_backend=fake_speech)

    with TestClient(app) as client:
        # Mute speech
        mute_resp = client.post("/api/speech/mute", json={"muted": True})
        assert mute_resp.status_code == 200
        assert mute_resp.json()["muted"] is True

        # Announcements should be suppressed when muted
        r = client.post("/api/speech/announce", json={"text": "Doorway ahead"})
        assert r.status_code == 200
        assert r.json()["enqueued"] is False

        # Unmute
        unmute_resp = client.post("/api/speech/mute", json={"muted": False})
        assert unmute_resp.status_code == 200
        assert unmute_resp.json()["muted"] is False

        # Status reflects unmuted
        status = client.get("/api/speech/status").json()
        assert status["muted"] is False

        # Stop speech
        stop_resp = client.post("/api/speech/stop")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "stopped"


def test_spatial_sector_partitioning():
    """Sector classifier maps horizontal bounding-box centers accurately."""
    # Left sector (cx < 0.33)
    b_left = BoundingBox(x_min=0.10, y_min=0.20, x_max=0.30, y_max=0.80)
    assert classify_sector(b_left) == "left"

    # Center sector (0.33 <= cx <= 0.66)
    b_center = BoundingBox(x_min=0.40, y_min=0.20, x_max=0.60, y_max=0.80)
    assert classify_sector(b_center) == "center"

    # Right sector (cx > 0.66)
    b_right = BoundingBox(x_min=0.70, y_min=0.20, x_max=0.90, y_max=0.80)
    assert classify_sector(b_right) == "right"


def test_detection_engine_lifecycle_and_latest(fake_adapter):
    """Detection pipeline starts, processes frames, and returns formatted detection results."""
    from socket_free_client import SocketFreeTestClient as TestClient
    mock_engine = FakeDetectionEngine(
        mock_detections=[
            Detection(
                class_name="person",
                confidence=0.92,
                box=BoundingBox(x_min=0.35, y_min=0.15, x_max=0.65, y_max=0.85),
                sector="center"
            )
        ]
    )
    fake_speech = FakeSpeechBackend()
    app = create_app(
        adapter=fake_adapter,
        speech_backend=fake_speech,
        detection_engine=mock_engine
    )

    with TestClient(app) as client:
        # Check initial detection status
        status_resp = client.get("/api/detection/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["active"] is False
        assert status_resp.json()["is_ready"] is True

        # Start detection pipeline
        start_det = client.post("/api/detection/start")
        assert start_det.status_code == 200
        assert start_det.json()["active"] is True

        # Start camera and fetch a frame (triggers detection processing)
        client.post("/api/camera/start")
        frame_resp = client.get("/api/camera/frame")
        assert frame_resp.status_code == 200

        # Allow background worker time to process frame
        data = None
        for _ in range(10):
            time.sleep(0.05)
            latest_resp = client.get("/api/detection/latest")
            assert latest_resp.status_code == 200
            data = latest_resp.json()
            if data is not None:
                break
        assert data is not None
        assert len(data["detections"]) == 1
        assert data["detections"][0]["class_name"] == "person"
        assert data["detections"][0]["sector"] == "center"
        assert data["detections"][0]["confidence"] == 0.92

        # Stop detection
        stop_det = client.post("/api/detection/stop")
        assert stop_det.status_code == 200
        assert stop_det.json()["active"] is False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows SAPI / WinRT requires Windows")
def test_windows_sapi_backend_stop_preemption():
    """Validates that WindowsSapiSpeechBackend.stop() safely handles proc termination without lock deadlocks."""
    from app.audio.speaker import WindowsSapiSpeechBackend
    backend = WindowsSapiSpeechBackend()
    backend.stop()

    class DummyProc:
        def __init__(self):
            self.terminated = False
        def poll(self):
            return None if not self.terminated else 0
        def terminate(self):
            self.terminated = True

    proc = DummyProc()
    backend._current_proc = proc
    backend.stop()
    assert proc.terminated is True
    assert backend._current_proc is None


def test_perception_pipeline_resilience_to_speech_failure(fake_adapter):
    """Verifies that failures in the speech system do not crash frame delivery or perception."""
    mock_engine = FakeDetectionEngine(
        mock_detections=[
            Detection(
                class_name="door",
                confidence=0.85,
                box=BoundingBox(x_min=0.1, y_min=0.1, x_max=0.3, y_max=0.9),
                sector="left"
            )
        ]
    )
    failing_speech = FakeSpeechBackend(should_fail=True)
    app = create_app(
        adapter=fake_adapter,
        speech_backend=failing_speech,
        detection_engine=mock_engine
    )

    with TestClient(app) as client:
        client.post("/api/camera/start")
        client.post("/api/detection/start")
        frame_resp = client.get("/api/camera/frame")
        assert frame_resp.status_code == 200
        assert frame_resp.headers["X-Frame-Id"] == "1"

        # Allow background perception worker to finish inference tick
        import time
        time.sleep(0.15)

        latest = client.get("/api/detection/latest")
        assert latest.status_code == 200
        assert latest.json()["detections"][0]["class_name"] == "door"


def test_decoupled_perception_worker_with_slow_inference(fake_adapter):
    """
    Verifies that slow model inference does NOT block HTTP frame delivery.
    Frame requests must complete in milliseconds while inference takes 200ms in background.
    """
    import time

    class SlowDetectionEngine(DetectionEngine):
        def __init__(self, latency: float = 0.2):
            self.latency = latency
            self.call_count = 0
            self._lock = threading.Lock()

        def detect(self, jpeg_bytes: bytes, frame_id: int) -> DetectionResult:
            with self._lock:
                self.call_count += 1
            time.sleep(self.latency)
            return DetectionResult(
                frame_id=frame_id,
                timestamp=time.time(),
                detections=[
                    Detection(
                        class_name="chair",
                        confidence=0.88,
                        box=BoundingBox(x_min=0.4, y_min=0.3, x_max=0.6, y_max=0.7),
                        sector="center"
                    )
                ],
                inference_time_ms=self.latency * 1000.0,
                model_name="SlowMockEngine"
            )

        def is_ready(self) -> bool:
            return True

        def get_model_info(self) -> Dict[str, Any]:
            return {"model_name": "SlowMockEngine", "is_ready": True}

    slow_engine = SlowDetectionEngine(latency=0.15)
    app = create_app(
        adapter=fake_adapter,
        speech_backend=FakeSpeechBackend(),
        detection_engine=slow_engine
    )

    with TestClient(app) as client:
        client.post("/api/camera/start")
        client.post("/api/detection/start")

        # Measure duration of frame request
        t_start = time.time()
        resp1 = client.get("/api/camera/frame")
        duration1 = time.time() - t_start

        # Should be fast (< 50ms) and NOT blocked by the 150ms inference
        assert resp1.status_code == 200
        assert duration1 < 0.10, f"Frame retrieval was blocked by inference! Took {duration1:.3f}s"

        # Rapidly fetch second frame
        t_start2 = time.time()
        resp2 = client.get("/api/camera/frame")
        duration2 = time.time() - t_start2
        assert resp2.status_code == 200
        assert duration2 < 0.10, f"Second frame retrieval was blocked! Took {duration2:.3f}s"

        # Allow background worker to finish the tick
        time.sleep(0.3)
        latest = client.get("/api/detection/latest")
        assert latest.status_code == 200
        assert latest.json()["detections"][0]["class_name"] == "chair"

        # Stop detection and verify clean shutdown
        client.post("/api/detection/stop")


def test_decoupled_worker_skips_stale_and_processes_latest():
    """
    Verifies that the background worker does not build an unbounded queue
    and processes only the latest available frame.
    """
    import time
    from app.detection.engine import PerceptionPipeline
    from app.camera.adapter import FramePacket

    processed_ids = []

    class TrackingEngine(DetectionEngine):
        def detect(self, jpeg_bytes: bytes, frame_id: int) -> DetectionResult:
            time.sleep(0.05)
            processed_ids.append(frame_id)
            return DetectionResult(
                frame_id=frame_id,
                timestamp=time.time(),
                detections=[],
                inference_time_ms=50.0,
                model_name="Tracker"
            )

        def is_ready(self) -> bool:
            return True

        def get_model_info(self) -> Dict[str, Any]:
            return {"model_name": "Tracker", "is_ready": True}

    pipeline = PerceptionPipeline(engine=TrackingEngine(), target_fps=20.0)
    pipeline.start()

    try:
        # Submit 4 frames in rapid succession
        for fid in range(1, 5):
            packet = FramePacket(
                frame_id=fid,
                captured_at=time.time(),
                jpeg_bytes=b"dummy",
                width=100,
                height=100,
                source_id="test",
                dropped_frames=0
            )
            pipeline.submit_frame(packet)

        # Allow worker time to process
        time.sleep(0.15)

        # Worker should have processed frame 1, and skipped directly to frame 4
        assert len(processed_ids) >= 1
        assert processed_ids[-1] == 4, f"Expected latest frame 4, got history: {processed_ids}"
    finally:
        pipeline.stop(timeout=1.0)
        assert pipeline.is_active() is False


def test_worker_safe_camera_switching_and_shutdown(fake_adapter):
    """Verifies that camera switching and stopping works cleanly with background worker running."""
    app = create_app(
        adapter=fake_adapter,
        speech_backend=FakeSpeechBackend(),
        detection_engine=FakeDetectionEngine()
    )

    with TestClient(app) as client:
        client.post("/api/camera/start", json={"camera_index": 0})
        client.post("/api/detection/start")

        # Frame 1 from camera 0
        resp1 = client.get("/api/camera/frame")
        assert resp1.status_code == 200

        # Switch camera to index 1 while worker is active
        switch_resp = client.post("/api/camera/start", json={"camera_index": 1})
        assert switch_resp.status_code == 200

        # Frame from camera 1
        resp2 = client.get("/api/camera/frame")
        assert resp2.status_code == 200

        # Stop camera and detection cleanly
        stop_cam = client.post("/api/camera/stop")
        assert stop_cam.status_code == 200
        stop_det = client.post("/api/detection/stop")
        assert stop_det.status_code == 200


def test_onnx_engine_missing_file_raises_explicit_error():
    """Verifies that OnnxDetectionEngine raises explicit ModelNotFoundError when weights are missing."""
    from app.detection import OnnxDetectionEngine, ModelNotFoundError

    with pytest.raises(ModelNotFoundError) as exc_info:
        OnnxDetectionEngine(model_path="non_existent_weights.onnx")

    assert "not found" in str(exc_info.value).lower()


def test_model_hash_verification(tmp_path):
    """Verifies that cryptographic SHA-256 verification detects authentic and tampered files."""
    import hashlib
    from app.detection import verify_model_hash

    # Create dummy model file
    dummy_file = tmp_path / "model.onnx"
    dummy_content = b"ONNX_MOCK_WEIGHTS_FOR_INTEGRITY_CHECK_12345"
    dummy_file.write_bytes(dummy_content)

    correct_sha256 = hashlib.sha256(dummy_content).hexdigest()
    wrong_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

    assert verify_model_hash(str(dummy_file), correct_sha256) is True
    assert verify_model_hash(str(dummy_file), correct_sha256.upper()) is True
    assert verify_model_hash(str(dummy_file), wrong_sha256) is False
    assert verify_model_hash("nonexistent_path", correct_sha256) is False


def test_model_integrity_error_on_hash_mismatch(tmp_path):
    """Verifies that OnnxDetectionEngine aborts with ModelIntegrityError on tampered weights."""
    from app.detection import OnnxDetectionEngine, ModelIntegrityError

    dummy_file = tmp_path / "corrupt_model.onnx"
    dummy_file.write_bytes(b"TAMPERED_OR_CORRUPTED_BYTES")

    with pytest.raises(ModelIntegrityError):
        OnnxDetectionEngine(
            model_path=str(dummy_file),
            expected_sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        )


def test_validate_bounding_box_safety():
    """Verifies that validate_bounding_box rejects NaN, Inf, and degenerate boxes, and clamps coordinates."""
    import math
    from app.detection import validate_bounding_box

    # Valid normal box
    box = validate_bounding_box(0.1, 0.2, 0.5, 0.8)
    assert box is not None
    assert box.x_min == 0.1
    assert box.x_max == 0.5
    assert box.center_x == 0.3

    # Clamping out-of-bounds
    clamped = validate_bounding_box(-0.2, -0.1, 1.2, 1.5)
    assert clamped is not None
    assert clamped.x_min == 0.0
    assert clamped.x_max == 1.0

    # Non-finite inputs (NaN, Inf)
    assert validate_bounding_box(float("nan"), 0.1, 0.5, 0.8) is None
    assert validate_bounding_box(0.1, float("inf"), 0.5, 0.8) is None
    assert validate_bounding_box(0.1, 0.1, float("-inf"), 0.8) is None

    # Degenerate boxes (min >= max)
    assert validate_bounding_box(0.5, 0.2, 0.5, 0.8) is None  # Zero width
    assert validate_bounding_box(0.6, 0.2, 0.4, 0.8) is None  # Inverted X
    assert validate_bounding_box(0.1, 0.8, 0.5, 0.2) is None  # Inverted Y


def test_perception_worker_resumes_after_camera_restart(fake_adapter):
    """
    REGRESSION TEST: Verifies that after a camera session stops and restarts,
    new frames starting from frame_id=1 are processed immediately by the perception worker
    and not blocked by the previous session's higher frame sequence ID.
    """
    import time
    from app.detection.engine import FakeDetectionEngine
    from app.audio.speaker import FakeSpeechBackend

    app = create_app(
        adapter=fake_adapter,
        speech_backend=FakeSpeechBackend(),
        detection_engine=FakeDetectionEngine()
    )

    with TestClient(app) as client:
        # 1. Start camera and detection
        client.post("/api/camera/start")
        client.post("/api/detection/start")

        # Ingest 5 frames in session 1
        for _ in range(5):
            res = client.get("/api/camera/frame")
            assert res.status_code == 200

        # Allow worker to process session 1
        time.sleep(0.1)
        latest_s1 = client.get("/api/detection/latest")
        assert latest_s1.status_code == 200
        assert latest_s1.json()["frame_id"] == 5

        # 2. Stop camera session
        client.post("/api/camera/stop")

        # 3. Restart camera (frame_id sequence resets to 1)
        client.post("/api/camera/start")

        # Request frame 1 of session 2
        res_s2 = client.get("/api/camera/frame")
        assert res_s2.status_code == 200
        assert res_s2.headers["X-Frame-Id"] == "1"

        # Allow worker time to process frame 1
        time.sleep(0.1)
        latest_s2 = client.get("/api/detection/latest")
        assert latest_s2.status_code == 200
        assert latest_s2.json() is not None
        assert latest_s2.json()["frame_id"] == 1, (
            f"Expected frame_id 1 to be processed in session 2, but got: {latest_s2.json()['frame_id']}"
        )


def test_perception_worker_repeated_restarts(fake_adapter):
    """
    Verifies that multiple repeated start/stop/restart cycles consistently
    process frames from each new session starting at frame_id 1.
    """
    import time
    from app.detection.engine import FakeDetectionEngine
    from app.audio.speaker import FakeSpeechBackend

    app = create_app(
        adapter=fake_adapter,
        speech_backend=FakeSpeechBackend(),
        detection_engine=FakeDetectionEngine()
    )

    with TestClient(app) as client:
        client.post("/api/detection/start")

        for cycle in range(1, 4):
            # Start camera session
            client.post("/api/camera/start")

            # Push 3 frames
            for expected_fid in range(1, 4):
                res = client.get("/api/camera/frame")
                assert res.status_code == 200
                assert res.headers["X-Frame-Id"] == str(expected_fid)

            time.sleep(0.08)
            latest = client.get("/api/detection/latest")
            assert latest.status_code == 200
            assert latest.json()["frame_id"] == 3

            # Stop camera session
            client.post("/api/camera/stop")


def test_perception_worker_camera_switching_coordinates_session(fake_adapter):
    """
    Verifies that switching between camera indices generates new session generations
    and immediately processes fresh frames from the target camera device.
    """
    import time
    from app.detection.engine import FakeDetectionEngine
    from app.audio.speaker import FakeSpeechBackend

    app = create_app(
        adapter=fake_adapter,
        speech_backend=FakeSpeechBackend(),
        detection_engine=FakeDetectionEngine()
    )

    with TestClient(app) as client:
        client.post("/api/detection/start")

        # 1. Start camera index 0
        client.post("/api/camera/start", json={"camera_index": 0})
        for _ in range(4):
            client.get("/api/camera/frame")

        time.sleep(0.08)
        latest_cam0 = client.get("/api/detection/latest")
        assert latest_cam0.status_code == 200
        assert latest_cam0.json()["frame_id"] == 4

        # 2. Switch camera to index 1
        client.post("/api/camera/start", json={"camera_index": 1})
        res_cam1 = client.get("/api/camera/frame")
        assert res_cam1.status_code == 200
        assert res_cam1.headers["X-Frame-Id"] == "1"

        time.sleep(0.08)
        latest_cam1 = client.get("/api/detection/latest")
        assert latest_cam1.status_code == 200
        assert latest_cam1.json()["frame_id"] == 1


def test_perception_worker_stale_pending_frame_purged_on_restart():
    """
    Verifies that a pending frame submitted during session A is purged when session A
    is stopped, ensuring it is never processed as part of session B.
    """
    import time
    from app.detection.engine import PerceptionPipeline, DetectionEngine, DetectionResult
    from app.camera.adapter import FramePacket

    processed_frames = []

    class MockEngine(DetectionEngine):
        def detect(self, jpeg_bytes: bytes, frame_id: int) -> DetectionResult:
            processed_frames.append(frame_id)
            return DetectionResult(
                frame_id=frame_id,
                timestamp=time.time(),
                detections=[],
                inference_time_ms=10.0,
                model_name="Mock"
            )

        def is_ready(self) -> bool:
            return True

        def get_model_info(self) -> Dict[str, Any]:
            return {"model_name": "Mock", "is_ready": True}

    pipeline = PerceptionPipeline(engine=MockEngine(), target_fps=30.0)
    # Note: Pipeline is NOT started yet so frames accumulate in pending slot

    packet_old = FramePacket(
        frame_id=99,
        captured_at=time.time(),
        jpeg_bytes=b"dummy",
        width=100,
        height=100,
        source_id="cam0",
        session_id="session_A"
    )
    pipeline.submit_frame(packet_old)

    # Session A ends: reset_session() is called by camera lifecycle
    pipeline.reset_session("session_B")

    # Start worker
    pipeline.start()

    # Session B submits frame 1
    packet_new = FramePacket(
        frame_id=1,
        captured_at=time.time(),
        jpeg_bytes=b"dummy",
        width=100,
        height=100,
        source_id="cam1",
        session_id="session_B"
    )
    pipeline.submit_frame(packet_new)

    time.sleep(0.1)
    pipeline.stop()

    # Verify: Frame 99 from session A was purged and NEVER processed!
    assert 99 not in processed_frames
    assert 1 in processed_frames


# =============================================================================
# SPRINT 4 INTEGRATION, RESILIENCE & SECURITY VERIFICATION SUITE
# =============================================================================

def test_end_to_end_latency_accounting(fake_adapter):
    """
    Verifies that the vision engine accurately calculates and exposes both
    on-device model inference latency and end-to-end frame-to-detection latency.
    """
    mock_engine = FakeDetectionEngine(
        mock_detections=[
            Detection(
                class_name="person",
                confidence=0.92,
                box=BoundingBox(x_min=0.35, y_min=0.2, x_max=0.65, y_max=0.8),
                sector="center"
            )
        ],
        simulated_latency_ms=18.5
    )
    app = create_app(adapter=fake_adapter, detection_engine=mock_engine)

    with TestClient(app) as client:
        client.post("/api/camera/start")
        client.post("/api/detection/start")

        # Capture a frame through HTTP endpoint
        frame_res = client.get("/api/camera/frame")
        assert frame_res.status_code == 200

        # Wait briefly for perception worker to complete inference
        time.sleep(0.12)

        det_res = client.get("/api/detection/latest")
        assert det_res.status_code == 200
        data = det_res.json()
        assert data is not None
        assert data["frame_id"] == 1
        assert "inference_time_ms" in data
        assert "e2e_latency_ms" in data
        assert data["inference_time_ms"] == 18.5
        assert data["e2e_latency_ms"] >= 0.0


def test_camera_lifecycle_rapid_churn_resilience(fake_adapter):
    """
    Tests rapid repeated start/stop cycles to verify zero deadlocks,
    zero resource leaks, and robust session coordination.
    """
    app = create_app(adapter=fake_adapter)

    with TestClient(app) as client:
        client.post("/api/detection/start")
        for i in range(5):
            start_resp = client.post("/api/camera/start")
            assert start_resp.status_code == 200
            assert start_resp.json()["active"] is True
            session_id = start_resp.json()["session_id"]
            assert session_id is not None

            frame_resp = client.get("/api/camera/frame")
            assert frame_resp.status_code == 200
            assert frame_resp.headers["X-Session-Id"] == session_id

            stop_resp = client.post("/api/camera/stop")
            assert stop_resp.status_code == 200
            assert stop_resp.json()["active"] is False


def test_camera_switch_during_active_perception(fake_adapter):
    """
    Verifies that changing camera devices while perception pipeline is actively running
    does not throw unhandled exceptions and smoothly coordinates session generation.
    """
    mock_engine = FakeDetectionEngine(simulated_latency_ms=10.0)
    app = create_app(adapter=fake_adapter, detection_engine=mock_engine)

    with TestClient(app) as client:
        # Start camera on device 0 and start perception
        client.post("/api/camera/start", json={"camera_index": 0})
        client.post("/api/detection/start")

        frame1 = client.get("/api/camera/frame")
        assert frame1.status_code == 200
        time.sleep(0.1)

        # Switch to device 1 while detection is still active
        client.post("/api/camera/stop")
        switch_res = client.post("/api/camera/start", json={"camera_index": 1})
        assert switch_res.status_code == 200

        frame2 = client.get("/api/camera/frame")
        assert frame2.status_code == 200
        time.sleep(0.1)

        det = client.get("/api/detection/latest")
        assert det.status_code == 200
        client.post("/api/detection/stop")
        client.post("/api/camera/stop")


def test_authenticated_endpoints_strict_rejection(fake_adapter):
    """
    Security verification:
    Ensures that when a session token is active, every single protected endpoint
    strictly rejects unauthorized requests with 401, while /api/health remains accessible.
    """
    valid_token = "secure_token_test_abc123"
    app = create_app(adapter=fake_adapter, session_token=valid_token)

    protected_endpoints = [
        ("GET", "/api/camera/devices", None),
        ("GET", "/api/camera/status", None),
        ("POST", "/api/camera/start", {}),
        ("POST", "/api/camera/stop", None),
        ("GET", "/api/camera/frame", None),
        ("POST", "/api/speech/announce", {"text": "hello"}),
        ("POST", "/api/speech/stop", None),
        ("POST", "/api/speech/mute", {"muted": True}),
        ("GET", "/api/speech/status", None),
        ("GET", "/api/detection/status", None),
        ("POST", "/api/detection/start", None),
        ("POST", "/api/detection/stop", None),
        ("GET", "/api/detection/latest", None),
    ]

    with TestClient(app) as client:
        # 1. Health is always accessible without auth
        health = client.get("/api/health")
        assert health.status_code == 200

        # 2. Every protected endpoint returns 401 without token
        for method, endpoint, payload in protected_endpoints:
            if method == "GET":
                res = client.get(endpoint)
            else:
                res = client.post(endpoint, json=payload if payload is not None else {})
            assert res.status_code == 401, f"{method} {endpoint} did not reject unauthenticated request"

        # 3. Every protected endpoint returns 401 with WRONG token
        for method, endpoint, payload in protected_endpoints:
            headers = {"X-Trinetra-Session-Token": "wrong_attacker_token"}
            if method == "GET":
                res = client.get(endpoint, headers=headers)
            else:
                res = client.post(endpoint, json=payload if payload is not None else {}, headers=headers)
            assert res.status_code == 401, f"{method} {endpoint} did not reject invalid token"

        # 4. Protected endpoint succeeds with VALID token
        auth_headers = {"X-Trinetra-Session-Token": valid_token}
        status_res = client.get("/api/camera/status", headers=auth_headers)
        assert status_res.status_code == 200


def test_speech_hazard_preemption_and_cooldown():
    """
    Verifies that critical hazard announcements preempt lower-priority speech
    and flush pending queues as designed for blind/low-vision safety.
    """
    fake_speaker = FakeSpeechBackend()
    mgr = SpeechManager(backend=fake_speaker, default_cooldown=2.0)

    # 1. Enqueue informational announcement
    enqueued1 = mgr.announce("Approaching door", priority=SpeechPriority.INFORMATIONAL)
    assert enqueued1 is True

    # 2. Critical hazard announcement with interrupt=True
    enqueued2 = mgr.announce(
        "Warning: Step down detected",
        priority=SpeechPriority.CRITICAL_HAZARD,
        interrupt=True
    )
    assert enqueued2 is True

    time.sleep(0.1)
    # The interrupt must have signaled the backend to stop lower priority speech
    assert fake_speaker.interrupted_count >= 1
    mgr.shutdown()


# =============================================================================
# SPRINT 4.1 RELIABILITY & SECURITY REGRESSION TESTS
# =============================================================================

def test_unavailable_detection_engine_lifecycle(fake_adapter):
    """
    Priority 1: Verifies that an unready/missing detection engine:
    1. Returns is_ready: False with explicit error details on GET /api/detection/status
    2. Strictly rejects POST /api/detection/start with HTTP 503 Service Unavailable
    3. Never emits silent fake detections on GET /api/detection/latest
    """
    from app.detection.engine import UnavailableDetectionEngine

    unavail_engine = UnavailableDetectionEngine(
        error_message="Model weights not found. Run setup_models.py to install.",
        error_type="ModelFileNotFound",
        model_name="yolox_nano.onnx"
    )
    app = create_app(adapter=fake_adapter, detection_engine=unavail_engine)

    with TestClient(app) as client:
        # 1. Status indicates unavailable with actionable error details
        status_res = client.get("/api/detection/status")
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["is_ready"] is False
        assert data["active"] is False
        assert data["error"] == "Model weights not found. Run setup_models.py to install."
        assert data["error_type"] == "ModelFileNotFound"
        assert data["model_name"] == "yolox_nano.onnx"

        # 2. Starting detection fails with 503 Service Unavailable
        start_res = client.post("/api/detection/start")
        assert start_res.status_code == 503
        assert "Cannot start detection" in start_res.json()["detail"]
        assert "setup_models.py" in start_res.json()["detail"]

        # 3. Perception was not started, latest detections is None
        assert client.get("/api/detection/latest").json() is None


def test_get_default_detection_engine_missing_file_returns_unavailable(monkeypatch, tmp_path):
    """
    Verifies that get_default_detection_engine() returns UnavailableDetectionEngine
    instead of FakeDetectionEngine when model is missing or corrupt.
    """
    from app.detection.engine import UnavailableDetectionEngine
    import app.main as app_main

    # Ensure fake env and custom model env are not set
    monkeypatch.delenv("TRINETRA_USE_FAKE_DETECTION", raising=False)
    monkeypatch.delenv("TRINETRA_MODEL_PATH", raising=False)
    # Point default model path to a missing file
    missing_file = tmp_path / "does_not_exist.onnx"
    monkeypatch.setattr(app_main, "DEFAULT_MODEL_PATH", missing_file)

    engine = app_main.get_default_detection_engine()
    assert isinstance(engine, UnavailableDetectionEngine)
    assert engine.is_ready() is False
    assert "does_not_exist.onnx" in engine.error_message


def test_get_default_detection_engine_fake_env_gated(monkeypatch):
    """
    Verifies that FakeDetectionEngine is strictly gated behind TRINETRA_USE_FAKE_DETECTION=1.
    """
    from app.detection.engine import FakeDetectionEngine
    from app.main import get_default_detection_engine

    monkeypatch.setenv("TRINETRA_USE_FAKE_DETECTION", "1")
    engine = get_default_detection_engine()
    assert isinstance(engine, FakeDetectionEngine)
    assert engine.is_ready() is True


def test_api_docs_disabled_by_default(fake_adapter):
    """
    Priority 3: Verifies that FastAPI documentation endpoints
    (/docs, /redoc, /openapi.json) return 404 by default in production.
    """
    app = create_app(adapter=fake_adapter)

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_api_docs_accessible_when_explicitly_enabled(fake_adapter, monkeypatch):
    """
    Priority 3: Verifies that API docs become accessible when enabled
    either programmatically via enable_docs=True or via TRINETRA_ENABLE_DOCS=1.
    """
    # 1. Programmatic enable
    app_explicit = create_app(adapter=fake_adapter, enable_docs=True)
    with TestClient(app_explicit) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200

    # 2. Environment variable enable
    monkeypatch.setenv("TRINETRA_ENABLE_DOCS", "1")
    app_env = create_app(adapter=fake_adapter)
    with TestClient(app_env) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200






