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
