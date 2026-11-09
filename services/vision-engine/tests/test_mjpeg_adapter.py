from app.camera import adapter as camera_adapter
from app.camera.adapter import FakeCameraAdapter, MJPEGStreamCameraAdapter


class ChunkedResponse:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0
        self.closed = False

    def read(self, count: int) -> bytes:
        result = self.data[self.offset:self.offset + count]
        self.offset += len(result)
        return result

    def close(self):
        self.closed = True


def test_mjpeg_adapter_emits_valid_canonical_packet(monkeypatch):
    jpeg = FakeCameraAdapter()._generate_test_jpeg()
    response = ChunkedResponse(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
    monkeypatch.setattr(camera_adapter, "urlopen", lambda *_args, **_kwargs: response)
    adapter = MJPEGStreamCameraAdapter("http://127.0.0.1:8080/stream")
    adapter.start()
    packet = adapter.capture_packet()
    assert packet.frame_id == 1
    assert packet.jpeg_bytes == jpeg
    assert packet.width > 0 and packet.height > 0
    assert adapter.get_status()["connection_state"] == "connected"
    adapter.stop()
    assert response.closed is True


def test_mjpeg_adapter_lifecycle_restart(monkeypatch):
    jpeg = FakeCameraAdapter()._generate_test_jpeg()
    response1 = ChunkedResponse(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
    response2 = ChunkedResponse(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
    responses = [response1, response2]
    monkeypatch.setattr(camera_adapter, "urlopen", lambda *_args, **_kwargs: responses.pop(0))

    adapter = MJPEGStreamCameraAdapter("http://127.0.0.1:8080/stream")
    assert not adapter.is_active()

    adapter.start()
    assert adapter.is_active()
    p1 = adapter.capture_packet()
    assert p1.frame_id == 1

    adapter.stop()
    assert not adapter.is_active()

    # Restart
    adapter.start()
    assert adapter.is_active()
    p2 = adapter.capture_packet()
    assert p2.frame_id == 1
    adapter.stop()


def test_mjpeg_adapter_reconnect_on_stream_end(monkeypatch):
    from app.camera.adapter import CameraReconnectingError

    # Empty response triggers OSError("MJPEG stream ended") -> triggers reconnect
    response1 = ChunkedResponse(b"")
    response2 = ChunkedResponse(b"")
    responses = [response1, response2]
    monkeypatch.setattr(camera_adapter, "urlopen", lambda *_args, **_kwargs: responses.pop(0))

    adapter = MJPEGStreamCameraAdapter("http://127.0.0.1:8080/stream")
    adapter.start()
    try:
        adapter.capture_packet()
    except CameraReconnectingError as exc:
        assert exc.attempt >= 1
        assert exc.max_attempts == 5
    finally:
        adapter.stop()


def test_mjpeg_adapter_drops_stale_intermediate_frames(monkeypatch):
    """Verifies that buffered older frames are discarded in favor of the freshest frame."""
    jpeg1 = FakeCameraAdapter()._generate_test_jpeg()
    jpeg2 = FakeCameraAdapter()._generate_test_jpeg()
    # Feed two frames together in a single stream chunk
    payload = (
        b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg1 + b"\r\n"
        b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg2 + b"\r\n"
    )
    response = ChunkedResponse(payload)
    monkeypatch.setattr(camera_adapter, "urlopen", lambda *_args, **_kwargs: response)

    adapter = MJPEGStreamCameraAdapter("http://127.0.0.1:8080/stream")
    adapter.start()
    packet = adapter.capture_packet()

    # Should capture the freshest frame (jpeg2), dropping jpeg1
    assert packet.jpeg_bytes == jpeg2
    assert adapter._dropped_frames == 1
    adapter.stop()


def test_mjpeg_adapter_authenticates_with_token(monkeypatch):
    """Verifies that auth_token is attached to request headers and query string."""
    captured_requests = []
    jpeg = FakeCameraAdapter()._generate_test_jpeg()
    response = ChunkedResponse(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")

    def mock_urlopen(req, timeout=4.0):
        captured_requests.append(req)
        return response

    monkeypatch.setattr(camera_adapter, "urlopen", mock_urlopen)

    adapter = MJPEGStreamCameraAdapter("http://192.168.4.1:81/stream", auth_token="trinetra-secret-token")
    adapter.start()
    packet = adapter.capture_packet()

    assert len(captured_requests) >= 1
    req = captured_requests[0]
    assert req.get_header("X-trinetra-token") == "trinetra-secret-token" or req.headers.get("X-trinetra-token") == "trinetra-secret-token" or req.headers.get("X-Trinetra-Token") == "trinetra-secret-token"
    assert "token=trinetra-secret-token" in req.full_url
    assert packet.frame_id == 1
    adapter.stop()

