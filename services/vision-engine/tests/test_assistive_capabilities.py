"""Regression coverage for explicit on-demand assistive capability behaviour."""
from fastapi.testclient import TestClient

from app.audio.speaker import FakeSpeechBackend
from app.camera.adapter import FakeCameraAdapter
from app.detection.engine import BoundingBox, Detection, FakeDetectionEngine
from app.main import create_app


def make_client():
    engine = FakeDetectionEngine(mock_detections=[Detection(
        class_name="person", confidence=.9,
        box=BoundingBox(.2, .2, .6, .8), sector="center"
    )])
    return TestClient(create_app(adapter=FakeCameraAdapter(), detection_engine=engine,
                                 speech_backend=FakeSpeechBackend()))


def test_capabilities_require_explicit_active_camera():
    with make_client() as client:
        response = client.post("/api/scene/query", json={"question": "के छ?"})
        assert response.status_code == 409


def test_scene_is_grounded_in_current_canonical_frame():
    with make_client() as client:
        assert client.post("/api/camera/start").status_code == 200
        response = client.post("/api/scene/query", json={"question": "के छ?"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "observed"
        assert "मान्छे" in body["text"]
        assert "सुरक्षित" in body["safety_note"]


def test_unavailable_models_do_not_invent_currency_or_identity():
    with make_client() as client:
        client.post("/api/camera/start")
        currency = client.post("/api/currency/identify", json={}).json()
        face = client.post("/api/faces/recognize", json={}).json()
        assert currency["status"] in ("unavailable", "uncertain") and currency["denomination"] is None
        assert face["status"] == "unavailable" and face["identity"] is None


def test_capability_status_is_truthful_about_optional_models():
    with make_client() as client:
        response = client.get("/api/capabilities/status")
        assert response.status_code == 200
        data = response.json()
        assert data["currency"]["available"] in (True, False)
        assert data["ocr"]["available"] in (True, False)


def test_ocr_read_with_nepali_frame_dispatches_speech():
    from pathlib import Path
    from app.main import speech_manager
    speech_manager.unmute()
    with speech_manager._cooldown_lock:
        speech_manager._cooldowns.clear()

    sample_path = Path("d:/trinetra/datasets/ocr/raw/sample_01.jpg")
    if sample_path.is_file():
        custom_jpeg = sample_path.read_bytes()
        adapter = FakeCameraAdapter(custom_jpeg=custom_jpeg)
    else:
        adapter = FakeCameraAdapter()

    speech = FakeSpeechBackend()
    engine = FakeDetectionEngine()
    client = TestClient(create_app(adapter=adapter, detection_engine=engine, speech_backend=speech))

    with client:
        assert client.post("/api/camera/start").status_code == 200
        res = client.post("/api/ocr/read", json={"speak": True})
        assert res.status_code == 200
        body = res.json()
        assert body["status"] in ("ok", "uncertain", "unavailable")
        if sample_path.is_file():
            assert body["status"] == "ok"
            assert len(body["text"]) > 0
            # Verify speech dispatch was called with Nepali
            import time
            for _ in range(25):
                with speech._lock:
                    if speech.spoken_history:
                        break
                time.sleep(0.1)
            with speech._lock:
                spoken_items = list(speech.spoken_history)
            assert len(spoken_items) > 0
            assert any(body["text"] in item or "नमस्ते" in item for item in spoken_items)
