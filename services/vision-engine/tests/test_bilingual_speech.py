"""
Trinetra Bilingual Nepali/English Speech & Language Switching Tests
Validates:
1. Nepali ('ne') as default system language across PerceptionPipeline, SceneDecisionEngine,
   SpeechManager, and IncidentRecorder, with English ('en') fully supported.
2. In-place immediate language switching without restarting camera, engine, or pipeline.
3. GET /api/speech/language and POST /api/speech/language API endpoints with strict validation.
4. Thread-safe concurrent language switching.
5. Consistent language dispatch across SceneDecisionEngine (hazards, crowds, obstacles, paths).
6. Manual incident announcements following selected language.
"""

from concurrent.futures import ThreadPoolExecutor
import time
from typing import Any, Dict, List
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager, SpeechPriority
from app.camera.adapter import FakeCameraAdapter
from app.detection.decision import SceneDecisionEngine
from app.detection.engine import PerceptionPipeline
from app.detection.scene import CollisionRisk, SceneAnalyzer
from app.detection.tracking import MovementDirection, TrackState, TrackedObject
from app.detection.types import BoundingBox, Detection, DetectionResult
from app.incident.recorder import IncidentRecorder
from app.localization import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    SupportedLanguage,
    is_supported_language,
    normalize_language,
)
from app.main import create_app
try:
    from socket_free_client import SocketFreeTestClient as TestClient
except ImportError:
    from tests.socket_free_client import SocketFreeTestClient as TestClient


def test_localization_layer_language_normalization():
    """Validates language code canonical normalization and rejection of invalid codes."""
    assert DEFAULT_LANGUAGE == "ne"
    assert "ne" in SUPPORTED_LANGUAGES and "en" in SUPPORTED_LANGUAGES

    # Valid normalization
    assert normalize_language("ne") == "ne"
    assert normalize_language("NE") == "ne"
    assert normalize_language("ne-NP") == "ne"
    assert normalize_language("nepali") == "ne"
    assert normalize_language("en") == "en"
    assert normalize_language("EN") == "en"
    assert normalize_language("en-US") == "en"
    assert normalize_language("english") == "en"
    assert normalize_language(None) == "ne"

    # Invalid codes raise ValueError
    for bad_code in ["fr", "es", "hindi", "zh", "123", "unknown"]:
        with pytest.raises(ValueError):
            normalize_language(bad_code)


def test_default_language_across_components():
    """Validates that all core modules initialize to Nepali ('ne') by default."""
    fake_backend = FakeSpeechBackend()
    speech_mgr = SpeechManager(backend=fake_backend)
    decision = SceneDecisionEngine(speech_manager=speech_mgr)
    pipeline = PerceptionPipeline(speech_manager=speech_mgr)
    incident_rec = IncidentRecorder(speech_manager=speech_mgr)

    assert speech_mgr.language == "ne"
    assert decision.language == "ne"
    assert pipeline.language == "ne"
    assert incident_rec.default_language == "ne"

    status = speech_mgr.get_status()
    assert status["language"] == "ne"

    speech_mgr.shutdown()


def test_scene_decision_engine_respects_language_switching_immediately():
    """Validates SceneDecisionEngine immediately uses the newly set language without restart."""
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=fake_backend)
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne")
    analyzer = SceneAnalyzer()
    t0 = 100.0

    # 1. Stationary obstacle in default Nepali
    track = TrackedObject(
        track_id=1,
        class_name="person",
        confidence=0.92,
        box=BoundingBox(0.4, 0.3, 0.6, 0.7),
        sector="center",
        first_seen=t0,
        last_seen=t0,
        state=TrackState.CONFIRMED,
    )
    assessment1 = analyzer.analyze_scene([track], frame_id=1, timestamp=t0)
    decision.process_scene(assessment1)
    time.sleep(0.05)
    assert len(fake_backend.spoken_history) == 1
    assert "अगाडि मान्छे छ।" in fake_backend.spoken_history[0]

    # 2. Switch language to English immediately in-place
    decision.language = "en"
    assert decision.language == "en"

    # Same obstacle in English: cooldown key includes :en so it dispatches in English
    assessment2 = analyzer.analyze_scene([track], frame_id=2, timestamp=t0 + 0.1)
    decision.process_scene(assessment2)
    time.sleep(0.05)
    assert len(fake_backend.spoken_history) == 2
    assert "Person, ahead." in fake_backend.spoken_history[1]

    # 3. Critical hazard in English
    fast_vehicle = TrackedObject(
        track_id=2,
        class_name="car",
        confidence=0.95,
        box=BoundingBox(0.3, 0.2, 0.7, 0.8),
        sector="center",
        first_seen=t0,
        last_seen=t0 + 0.2,
        state=TrackState.CONFIRMED,
        movement=MovementDirection.APPROACHING,
    )
    hazard_assessment_en = analyzer.analyze_scene([fast_vehicle], frame_id=3, timestamp=t0 + 0.2)
    decision.process_scene(hazard_assessment_en)
    time.sleep(0.05)
    assert "approaching" in fake_backend.spoken_history[-1].lower()

    # 4. Switch back to Nepali
    decision.language = "ne"
    hazard_assessment_ne = analyzer.analyze_scene([fast_vehicle], frame_id=4, timestamp=t0 + 0.3)
    decision.process_scene(hazard_assessment_ne)
    time.sleep(0.05)
    assert "नजिकिँदै छ" in fake_backend.spoken_history[-1] or "सावधान" in fake_backend.spoken_history[-1]

    speech_mgr.shutdown()


def test_perception_pipeline_language_propagation():
    """Validates that setting language on PerceptionPipeline propagates to SceneDecisionEngine."""
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=fake_backend)
    pipeline = PerceptionPipeline(speech_manager=speech_mgr)

    # Initial default is Nepali
    assert pipeline.language == "ne"
    assert pipeline.decision_engine.language == "ne"

    # Set to English
    pipeline.language = "en"
    assert pipeline.language == "en"
    assert pipeline.decision_engine.language == "en"

    # Set to Nepali with alias 'ne-NP'
    pipeline.language = "ne-NP"
    assert pipeline.language == "ne"
    assert pipeline.decision_engine.language == "ne"

    speech_mgr.shutdown()


def test_incident_recorder_respects_language_and_updates():
    """Validates IncidentRecorder announcements respect default and explicit languages."""
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=fake_backend)
    recorder = IncidentRecorder(speech_manager=speech_mgr)

    cam = FakeCameraAdapter(320, 240)
    cam.start()
    pkt = cam.capture_packet()

    # Default Nepali feedback
    recorder.capture(packet=pkt, notes="Test 1")
    time.sleep(0.05)
    assert len(fake_backend.spoken_history) == 1
    assert "घटना अभिलेख गरियो।" in fake_backend.spoken_history[0]

    # In-place default language update to English
    recorder.set_default_language("en")
    assert recorder.default_language == "en"
    pkt2 = cam.capture_packet()
    recorder.capture(packet=pkt2, notes="Test 2")
    time.sleep(0.05)
    assert len(fake_backend.spoken_history) == 2
    assert "Incident snapshot recorded." in fake_backend.spoken_history[1]

    # Explicit override: request in Nepali while default is English
    pkt3 = cam.capture_packet()
    recorder.capture(packet=pkt3, notes="Test 3", language="ne")
    time.sleep(0.05)
    assert len(fake_backend.spoken_history) == 3
    assert "घटना अभिलेख गरियो।" in fake_backend.spoken_history[2]

    cam.stop()
    speech_mgr.shutdown()


def test_speech_language_endpoints_lifecycle():
    """Validates GET and POST /api/speech/language endpoints with validation and status reflection."""
    fake_adapter = FakeCameraAdapter(320, 240)
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    app = create_app(adapter=fake_adapter, speech_backend=fake_backend)

    with TestClient(app) as client:
        # 1. GET returns default Nepali
        res = client.get("/api/speech/language")
        assert res.status_code == 200
        body = res.json()
        assert body["language"] == "ne"
        assert body["default_language"] == "ne"
        assert "ne" in body["supported_languages"]
        assert "en" in body["supported_languages"]

        # 2. Check /api/speech/status reflects active language
        status_res = client.get("/api/speech/status")
        assert status_res.status_code == 200
        assert status_res.json().get("language") == "ne"

        # 3. POST switches language to English immediately
        switch_res = client.post("/api/speech/language", json={"language": "en"})
        assert switch_res.status_code == 200
        switch_body = switch_res.json()
        assert switch_body["status"] == "ok"
        assert switch_body["language"] == "en"
        assert switch_body["previous_language"] == "ne"

        # 4. Verify GET reflects English
        get_res_en = client.get("/api/speech/language")
        assert get_res_en.status_code == 200
        assert get_res_en.json()["language"] == "en"

        status_res_en = client.get("/api/speech/status")
        assert status_res_en.json().get("language") == "en"

        # 5. POST switches back to Nepali with alias 'ne-NP'
        switch_res_ne = client.post("/api/speech/language", json={"language": "ne-NP"})
        assert switch_res_ne.status_code == 200
        assert switch_res_ne.json()["language"] == "ne"
        assert switch_res_ne.json()["previous_language"] == "en"

        # 6. POST with invalid language returns 400 Bad Request
        bad_res = client.post("/api/speech/language", json={"language": "fr"})
        assert bad_res.status_code == 400
        assert "Unsupported language 'fr'" in bad_res.json()["detail"]

        # 7. POST with empty/whitespace language returns 400 Bad Request
        empty_res = client.post("/api/speech/language", json={"language": "   "})
        assert empty_res.status_code == 400


def test_concurrent_language_updates_thread_safety():
    """Validates that rapid concurrent language switch requests maintain state consistency."""
    fake_adapter = FakeCameraAdapter(320, 240)
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    app = create_app(adapter=fake_adapter, speech_backend=fake_backend)

    with TestClient(app) as client:
        def switch_worker(target_lang: str):
            r = client.post("/api/speech/language", json={"language": target_lang})
            return r.status_code, r.json().get("language")

        languages = ["ne", "en", "ne", "en", "ne", "en", "ne", "en"] * 3
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(switch_worker, languages))

        for status_code, lang in results:
            assert status_code == 200
            assert lang in ("ne", "en")

        # System state must be valid
        final_res = client.get("/api/speech/language")
        assert final_res.status_code == 200
        assert final_res.json()["language"] in ("ne", "en")


def test_camera_stream_remains_active_during_language_switch():
    """
    STRICT REQUIREMENT: Language switching must happen immediately
    without restarting the backend or camera pipeline.
    """
    fake_adapter = FakeCameraAdapter(320, 240)
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    app = create_app(adapter=fake_adapter, speech_backend=fake_backend)

    with TestClient(app) as client:
        # Start camera
        start_res = client.post("/api/camera/start")
        assert start_res.status_code == 200
        initial_session = start_res.json()["session_id"]
        assert initial_session is not None

        # Fetch first frame
        f1 = client.get("/api/camera/frame")
        assert f1.status_code == 200
        assert f1.headers["X-Session-Id"] == initial_session

        # Switch language while camera is streaming
        switch_res = client.post("/api/speech/language", json={"language": "en"})
        assert switch_res.status_code == 200

        # Camera status must remain active and retain the SAME session_id (NO camera restart!)
        status_res = client.get("/api/camera/status")
        assert status_res.status_code == 200
        assert status_res.json()["active"] is True
        assert status_res.json()["session_id"] == initial_session

        # Next frame continues uninterrupted with same session
        f2 = client.get("/api/camera/frame")
        assert f2.status_code == 200
        assert f2.headers["X-Session-Id"] == initial_session
        assert int(f2.headers["X-Frame-Id"]) >= int(f1.headers["X-Frame-Id"])

        # Stop camera
        client.post("/api/camera/stop")
