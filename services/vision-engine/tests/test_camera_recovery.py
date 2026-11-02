"""
Test Camera Disconnection and Recovery (Priority 4.7 Phase 1).
Validates camera connection states, bounded automatic reconnection with exponential backoff,
HTTP 503 Retry-After behavior, status reporting, and exhaustion handling.
"""

import time
import pytest

from app.camera.adapter import (
    CameraConnectionState,
    CameraConnectionExhaustedError,
    CameraNotActiveError,
    CameraReconnectingError,
    FakeCameraAdapter,
)
from app.main import create_app, camera_manager
try:
    from socket_free_client import SocketFreeTestClient
except ImportError:
    from tests.socket_free_client import SocketFreeTestClient


def test_camera_connection_initial_states():
    """Validates initial connection state transitions from DISCONNECTED to CONNECTED on start()."""
    adapter = FakeCameraAdapter()
    assert adapter._connection_state == CameraConnectionState.DISCONNECTED

    adapter.start()
    assert adapter.is_active() is True
    assert adapter._connection_state == CameraConnectionState.CONNECTED
    assert adapter._reconnect_attempts == 0
    assert adapter._last_error is None

    status = adapter.get_status()
    assert status["connection_state"] == "connected"
    assert status["reconnect_attempts"] == 0
    assert status["max_reconnect_attempts"] == 5

    adapter.stop()
    assert adapter._connection_state == CameraConnectionState.DISCONNECTED


def test_transient_disconnection_and_reconnection_backoff():
    """
    Validates simulated transient disconnection:
    First capture raises CameraReconnectingError with attempt=1 and backoff,
    subsequent attempts track exponential backoff, and eventually recovers to CONNECTED.
    """
    adapter = FakeCameraAdapter()
    adapter.initial_backoff = 0.1
    adapter.backoff_multiplier = 2.0
    adapter.max_backoff = 1.0
    adapter.start()

    # Inject transient disconnection with 1 recovery failure before recovery
    adapter.simulate_transient_disconnection(failure_count=1)
    assert adapter._connection_state == CameraConnectionState.RECONNECTING

    # Attempt 1 (before timer expires): immediate query gets ReconnectingError
    with pytest.raises(CameraReconnectingError) as exc_info:
        adapter.capture_packet()
    assert exc_info.value.attempt == 1
    assert exc_info.value.max_attempts == 5
    assert exc_info.value.retry_after > 0

    # Wait for backoff 1 timer to elapse (~0.1s)
    time.sleep(0.12)

    # Attempt 2: timer elapsed, recovery cycle 1 fails (0 remaining failure)
    with pytest.raises(CameraReconnectingError) as exc_info2:
        adapter.capture_packet()
    assert exc_info2.value.attempt == 2
    assert round(exc_info2.value.retry_after, 2) >= 0.1

    # Wait for backoff 2 timer to elapse (~0.2s)
    time.sleep(0.22)

    # Attempt 3: timer elapsed, recovery cycle 2 succeeds!
    packet = adapter.capture_packet()
    assert packet is not None
    assert packet.frame_id > 0
    assert adapter._connection_state == CameraConnectionState.CONNECTED
    assert adapter._reconnect_attempts == 0

    adapter.stop()


def test_permanent_disconnection_exhaustion():
    """
    Validates that permanent disconnection eventually exhausts all max_reconnect_attempts
    and transitions to ERROR state with CameraConnectionExhaustedError.
    """
    adapter = FakeCameraAdapter()
    adapter.max_reconnect_attempts = 3
    adapter.initial_backoff = 0.05
    adapter.backoff_multiplier = 1.0
    adapter.start()

    adapter.simulate_permanent_disconnection()
    assert adapter._connection_state == CameraConnectionState.RECONNECTING

    # Immediate capture gives attempt 1
    with pytest.raises(CameraReconnectingError) as e1:
        adapter.capture_packet()
    assert e1.value.attempt == 1

    time.sleep(0.08)
    with pytest.raises(CameraReconnectingError) as e2:
        adapter.capture_packet()
    assert e2.value.attempt == 2

    time.sleep(0.08)
    with pytest.raises(CameraReconnectingError) as e3:
        adapter.capture_packet()
    assert e3.value.attempt == 3

    time.sleep(0.08)
    # Attempt 4 exceeds max_reconnect_attempts (3), raising CameraConnectionExhaustedError!
    with pytest.raises(CameraConnectionExhaustedError) as exh_err:
        adapter.capture_packet()
    assert exh_err.value.total_attempts == 3
    assert adapter._connection_state == CameraConnectionState.ERROR

    adapter.stop()


def test_api_reconnecting_returns_http_503_with_retry_after():
    """
    Validates that GET /api/camera/frame returns HTTP 503 with Retry-After header
    and structured JSON during camera recovery, preventing client 500 retry storms.
    """
    fake = FakeCameraAdapter()
    camera_manager.set_adapter(fake)
    app = create_app()
    with SocketFreeTestClient(app) as client:
        # Start camera
        res_start = client.post("/api/camera/start", headers={"X-Trinetra-Session-Token": "trinetra-dev-local-token"})
        assert res_start.status_code == 200

        # Normal frame
        res_frame = client.get("/api/camera/frame", headers={"X-Trinetra-Session-Token": "trinetra-dev-local-token"})
        assert res_frame.status_code == 200
        assert res_frame.headers.get("Content-Type") == "image/jpeg"

        # Inject transient disconnection into active adapter
        active_adapter = camera_manager.adapter
        assert isinstance(active_adapter, FakeCameraAdapter)
        active_adapter.simulate_transient_disconnection(failure_count=1)

        # GET /api/camera/frame should now return 503 with Retry-After header
        res_rec = client.get("/api/camera/frame", headers={"X-Trinetra-Session-Token": "trinetra-dev-local-token"})
        assert res_rec.status_code == 503
        assert "Retry-After" in res_rec.headers
        data = res_rec.json()
        assert data["status"] == "reconnecting"
        assert data["error_code"] == "camera_reconnecting"
        assert data["attempt"] == 1

        # Check camera status endpoint reports reconnecting state
        res_status = client.get("/api/camera/status", headers={"X-Trinetra-Session-Token": "trinetra-dev-local-token"})
        assert res_status.status_code == 200
        stat_data = res_status.json()
        assert stat_data["connection_state"] == "reconnecting"
        assert stat_data["reconnect_attempts"] >= 1

        # Cleanup
        client.post("/api/camera/stop", headers={"X-Trinetra-Session-Token": "trinetra-dev-local-token"})


def test_api_reconnection_exhausted_returns_http_503():
    """Validates that GET /api/camera/frame returns HTTP 503 with status 'exhausted' when recovery fails."""
    fake = FakeCameraAdapter()
    camera_manager.set_adapter(fake)
    app = create_app()
    with SocketFreeTestClient(app) as client:
        client.post("/api/camera/start", headers={"X-Trinetra-Session-Token": "trinetra-dev-local-token"})

        active_adapter = camera_manager.adapter
        assert isinstance(active_adapter, FakeCameraAdapter)
        active_adapter.max_reconnect_attempts = 1
        active_adapter.initial_backoff = 0.05
        active_adapter.simulate_permanent_disconnection()

        # Burn the 1 attempt
        time.sleep(0.08)
        try:
            active_adapter.capture_packet()
        except Exception:
            pass

        # Next query via API should return 503 exhausted
        time.sleep(0.08)
        res_frame = client.get("/api/camera/frame", headers={"X-Trinetra-Session-Token": "trinetra-dev-local-token"})
        assert res_frame.status_code == 503
        data = res_frame.json()
        assert data["status"] == "exhausted"
        assert data["error_code"] == "camera_reconnection_exhausted"

        client.post("/api/camera/stop", headers={"X-Trinetra-Session-Token": "trinetra-dev-local-token"})
