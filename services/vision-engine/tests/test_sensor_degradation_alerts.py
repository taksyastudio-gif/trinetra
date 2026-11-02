"""
Test Sensor Degradation Audio Alerts (Priority 4.7 Phase 1).
Validates tracing of state_action.audio_chime into SpeechManager,
rate-limited bilingual (Nepali & English) spoken warnings,
and audio playback failure reporting.
"""

import time
from typing import List, Optional
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager, SpeechPriority
from app.camera.adapter import FramePacket
from app.camera.health_controller import SensorHealthController
from app.detection.engine import FakeDetectionEngine, PerceptionPipeline


class MockFailingSpeechBackend(FakeSpeechBackend):
    """Speech backend mock that simulates audio device playback failure."""

    def __init__(self, fail: bool = True):
        super().__init__()
        self.should_fail = fail

    def speak(self, text: str, interrupt: bool = False, language: Optional[str] = None) -> bool:
        if self.should_fail:
            return False
        return super().speak(text, interrupt, language)


class RecordingSpeechManager(SpeechManager):
    """SpeechManager that records calls to announce() for inspection."""

    def __init__(self, backend=None, language="ne"):
        super().__init__(backend=backend or FakeSpeechBackend(), language=language)
        self.announcements: List[dict] = []

    def announce(
        self,
        text: str,
        priority: SpeechPriority = SpeechPriority.SPATIAL_NAVIGATION,
        message_key: Optional[str] = None,
        interrupt: bool = False,
        cooldown: Optional[float] = None,
        language: Optional[str] = None
    ) -> bool:
        enqueued = super().announce(
            text=text,
            priority=priority,
            message_key=message_key,
            interrupt=interrupt,
            cooldown=cooldown,
            language=language
        )
        self.announcements.append({
            "text": text,
            "priority": priority,
            "message_key": message_key,
            "interrupt": interrupt,
            "cooldown": cooldown,
            "language": language,
            "enqueued": enqueued
        })
        return enqueued


def test_sensor_health_alert_nepali_chime_unavailable():
    """Validates that CHIME_UNAVAILABLE triggers Nepali critical hazard warning."""
    speech = RecordingSpeechManager(language="ne")
    pipeline = PerceptionPipeline(
        engine=FakeDetectionEngine(),
        speech_manager=speech,
        language="ne"
    )

    class DummyStateAction:
        audio_chime = "CHIME_UNAVAILABLE"

    pipeline._handle_sensor_health_alert(DummyStateAction())

    assert len(speech.announcements) == 1
    call = speech.announcements[0]
    assert call["text"] == "चेतावनी: क्यामेरा दृश्य अवरुद्ध वा अँध्यारो छ।"
    assert call["priority"] == SpeechPriority.CRITICAL_HAZARD
    assert call["interrupt"] is True
    assert call["language"] == "ne"
    assert call["enqueued"] is True
    pipeline.stop()
    speech.shutdown()


def test_sensor_health_alert_english_chime_unavailable():
    """Validates that CHIME_UNAVAILABLE triggers English critical hazard warning."""
    speech = RecordingSpeechManager(language="en")
    pipeline = PerceptionPipeline(
        engine=FakeDetectionEngine(),
        speech_manager=speech,
        language="en"
    )

    class DummyStateAction:
        audio_chime = "CHIME_UNAVAILABLE"

    pipeline._handle_sensor_health_alert(DummyStateAction())

    assert len(speech.announcements) == 1
    call = speech.announcements[0]
    assert call["text"] == "Warning: camera view obstructed or dark."
    assert call["priority"] == SpeechPriority.CRITICAL_HAZARD
    assert call["interrupt"] is True
    assert call["language"] == "en"
    assert call["enqueued"] is True
    pipeline.stop()
    speech.shutdown()


def test_sensor_health_alert_outage_expired():
    """Validates that CHIME_OUTAGE_EXPIRED announces tracking stopped."""
    speech = RecordingSpeechManager(language="en")
    pipeline = PerceptionPipeline(
        engine=FakeDetectionEngine(),
        speech_manager=speech,
        language="en"
    )

    class DummyStateAction:
        audio_chime = "CHIME_OUTAGE_EXPIRED"

    pipeline._handle_sensor_health_alert(DummyStateAction())

    assert len(speech.announcements) == 1
    call = speech.announcements[0]
    assert call["text"] == "Sensor unavailable: tracking stopped."
    assert call["priority"] == SpeechPriority.CRITICAL_HAZARD
    assert call["interrupt"] is True
    pipeline.stop()
    speech.shutdown()


def test_sensor_health_alert_recovery():
    """Validates that CHIME_RECOVERY triggers recovery announcement with normal priority."""
    speech = RecordingSpeechManager(language="en")
    pipeline = PerceptionPipeline(
        engine=FakeDetectionEngine(),
        speech_manager=speech,
        language="en"
    )

    class DummyStateAction:
        audio_chime = "CHIME_RECOVERY"

    pipeline._handle_sensor_health_alert(DummyStateAction())

    assert len(speech.announcements) == 1
    call = speech.announcements[0]
    assert call["text"] == "Camera view restored."
    assert call["priority"] == SpeechPriority.SPATIAL_NAVIGATION
    assert call["interrupt"] is False
    pipeline.stop()
    speech.shutdown()


def test_sensor_health_alert_rate_limiting():
    """Validates that rapid consecutive alerts with same chime are rate-limited."""
    speech = RecordingSpeechManager(language="en")
    pipeline = PerceptionPipeline(
        engine=FakeDetectionEngine(),
        speech_manager=speech,
        language="en"
    )

    class DummyStateAction:
        audio_chime = "CHIME_UNAVAILABLE"

    first = speech.announce(
        text="Warning: camera view obstructed or dark.",
        priority=SpeechPriority.CRITICAL_HAZARD,
        message_key="sensor_health:CHIME_UNAVAILABLE",
        cooldown=5.0
    )
    assert first is True

    # Immediate second call within 5s cooldown
    second = speech.announce(
        text="Warning: camera view obstructed or dark.",
        priority=SpeechPriority.CRITICAL_HAZARD,
        message_key="sensor_health:CHIME_UNAVAILABLE",
        cooldown=5.0
    )
    assert second is False

    pipeline.stop()
    speech.shutdown()


def test_audio_failure_detection_and_reporting():
    """Validates that audio failures are detected, counted, and reported in get_status()."""
    failing_backend = MockFailingSpeechBackend(fail=True)
    speech = SpeechManager(backend=failing_backend, language="en")

    # Initial status
    status = speech.get_status()
    assert status["audio_failure_count"] == 0
    assert status["last_audio_error"] is None

    # Enqueue announcement
    speech.announce("Testing failure detection", interrupt=True)

    # Wait briefly for worker thread to attempt playback
    time.sleep(0.3)

    status = speech.get_status()
    assert status["audio_failure_count"] >= 1
    assert "Backend speak failed" in str(status["last_audio_error"])

    speech.shutdown()
