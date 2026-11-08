"""
Trinetra Speech Engine & Localization Integration Tests
Validates:
- Persistent WinRT/SAPI worker initialization, audio onset, and preemption
- Voice discovery and language capability detection
- Deterministic suppression of Nepali announcements when no verified voice is installed (no silent English fallback)
- Successful Nepali announcement dispatch when a verified Nepali voice is available
- PerceptionPipeline end-to-end integration with localized formatting
"""

import sys
import time
import pytest
from app.audio.speaker import (
    FakeSpeechBackend,
    SpeechManager,
    SpeechPriority,
    WindowsSapiSpeechBackend,
)
from app.detection.engine import (
    BoundingBox,
    Detection,
    DetectionResult,
    PerceptionPipeline,
)
from app.localization import SupportedLanguage, format_announcement, get_announcement_key


@pytest.mark.skipif(sys.platform != "win32", reason="Windows SAPI / WinRT requires Windows")
def test_windows_sapi_backend_stop_preemption_contract():
    """Validates that WindowsSapiSpeechBackend.stop() handles proc termination safely without lock deadlock."""
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
    backend.shutdown()


def test_fake_speech_backend_voice_support():
    """Validates voice querying and language capability inspection on FakeSpeechBackend."""
    backend_en = FakeSpeechBackend(supported_languages=["en"])
    assert backend_en.has_voice_for_language("en") is True
    assert backend_en.has_voice_for_language("ne") is False
    voices_en = backend_en.get_available_voices()
    assert len(voices_en) == 1
    assert voices_en[0]["language"] == "en-US"

    backend_ne = FakeSpeechBackend(supported_languages=["en", "ne"])
    assert backend_ne.has_voice_for_language("en") is True
    assert backend_ne.has_voice_for_language("ne") is True
    voices_ne = backend_ne.get_available_voices()
    assert len(voices_ne) == 2


def test_nepali_speech_suppressed_when_no_voice_available():
    """
    STRICT REQUIREMENT: When Nepali is requested but no Nepali voice is installed,
    speech MUST be suppressed and must NOT silently fall back to English speech.
    """
    backend = FakeSpeechBackend(supported_languages=["en"])  # No Nepali voice
    mgr = SpeechManager(backend=backend)

    # Attempt to announce Nepali phrase
    enqueued = mgr.announce(
        text="बायाँतिर कुकुर छ।",
        priority=SpeechPriority.SPATIAL_NAVIGATION,
        language="ne"
    )
    assert enqueued is False
    time.sleep(0.05)
    # Spoken history must remain completely empty (no silent English fallback!)
    assert len(backend.spoken_history) == 0
    mgr.shutdown()


def test_nepali_speech_enqueued_when_voice_available():
    """When a verified Nepali voice is available, announcement is enqueued and spoken."""
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])  # Nepali voice present
    mgr = SpeechManager(backend=backend)

    enqueued = mgr.announce(
        text="बायाँतिर कुकुर छ।",
        priority=SpeechPriority.SPATIAL_NAVIGATION,
        language="ne"
    )
    assert enqueued is True
    time.sleep(0.1)
    assert len(backend.spoken_history) == 1
    assert backend.spoken_history[0] == "बायाँतिर कुकुर छ।"
    mgr.shutdown()


def test_perception_pipeline_localized_announcements_english():
    """Validates PerceptionPipeline dispatches English announcements by default."""
    backend = FakeSpeechBackend(supported_languages=["en"])
    mgr = SpeechManager(backend=backend)
    pipeline = PerceptionPipeline(speech_manager=mgr, language="en")

    det = Detection(
        class_name="dog",
        confidence=0.92,
        box=BoundingBox(0.1, 0.2, 0.3, 0.4),
        sector="left"
    )
    res = DetectionResult(
        frame_id=1,
        timestamp=time.time(),
        detections=[det],
        inference_time_ms=15.0,
        model_name="test-model"
    )

    pipeline._announce_detections(res)
    time.sleep(0.1)
    assert len(backend.spoken_history) == 1
    assert backend.spoken_history[0] == "Dog, left."
    mgr.shutdown()


def test_perception_pipeline_localized_announcements_nepali_with_voice():
    """Validates PerceptionPipeline dispatches Nepali announcement when Nepali voice is configured."""
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    mgr = SpeechManager(backend=backend)
    pipeline = PerceptionPipeline(speech_manager=mgr, language="ne")

    det = Detection(
        class_name="person",
        confidence=0.88,
        box=BoundingBox(0.4, 0.2, 0.6, 0.8),
        sector="center"
    )
    res = DetectionResult(
        frame_id=1,
        timestamp=time.time(),
        detections=[det],
        inference_time_ms=15.0,
        model_name="test-model"
    )

    pipeline._announce_detections(res)
    time.sleep(0.1)
    assert len(backend.spoken_history) == 1
    assert backend.spoken_history[0] == "अगाडि मान्छे छ।"
    mgr.shutdown()


def test_perception_pipeline_localized_announcements_nepali_without_voice():
    """Validates PerceptionPipeline suppresses Nepali announcement without falling back to English when no voice is installed."""
    backend = FakeSpeechBackend(supported_languages=["en"])  # No Nepali voice
    mgr = SpeechManager(backend=backend)
    pipeline = PerceptionPipeline(speech_manager=mgr, language="ne")

    det = Detection(
        class_name="car",
        confidence=0.85,
        box=BoundingBox(0.7, 0.2, 0.9, 0.8),
        sector="right"
    )
    res = DetectionResult(
        frame_id=1,
        timestamp=time.time(),
        detections=[det],
        inference_time_ms=15.0,
        model_name="test-model"
    )

    pipeline._announce_detections(res)
    time.sleep(0.1)
    assert len(backend.spoken_history) == 0
    mgr.shutdown()


def test_speech_status_reporting():
    """Validates SpeechManager.get_status reporting of available voices and nepali readiness."""
    backend = FakeSpeechBackend(supported_languages=["en"])
    mgr = SpeechManager(backend=backend)
    status = mgr.get_status()
    assert status["muted"] is False
    assert status["paused"] is False
    assert status["nepali_voice_available"] is False
    assert len(status["available_voices"]) == 1
    mgr.shutdown()
