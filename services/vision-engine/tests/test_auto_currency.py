"""
Tests for Trinetra Autonomous & Semi-Autonomous In-Hand Banknote Currency Recognition.
Validates:
1. CurrencyService status and model readiness
2. Automatic identification on live banknote crop (Rs. 100 emerald green, Rs. 20 orange)
3. Rate-limiting & anti-spam debouncing (does not repeat speech continuously for same note)
4. De-bounce reset on note removal/change
5. REST endpoint toggling: GET/POST /api/currency/auto-mode
"""
import os
import sys
import time
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.capabilities import CurrencyService
from app.audio.speaker import FakeSpeechBackend, SpeechPriority
from app.detection.engine import PerceptionPipeline, FramePacket
from app.detection.native_engine import NativeVisionEngine
from app.main import create_app


def make_synthetic_note(denom: int) -> bytes:
    """Generates synthetic colored banknote frame matching Trinetra's color signatures."""
    frame = np.full((480, 640, 3), 120, dtype=np.uint8)
    if denom == 100:
        # Emerald Green (BGR: 40, 130, 60 -> HSV H around 60)
        cv2.rectangle(frame, (180, 140), (460, 340), (45, 135, 55), -1)
    elif denom == 20:
        # Bright Orange (BGR: 30, 100, 220 -> HSV H around 15)
        cv2.rectangle(frame, (180, 140), (460, 340), (30, 100, 220), -1)
    elif denom == 1000:
        # Silver / Cerulean Blue (BGR: 190, 140, 50 -> HSV H around 105)
        cv2.rectangle(frame, (180, 140), (460, 340), (190, 140, 50), -1)
    elif denom == 500:
        # Chestnut Brown (BGR: 30, 50, 120 -> HSV H around 8)
        cv2.rectangle(frame, (180, 140), (460, 340), (30, 50, 120), -1)
    
    _, jpg = cv2.imencode(".jpg", frame)
    return jpg.tobytes()


def test_currency_service_direct_identification():
    service = CurrencyService()
    assert service.status()["available"] is True

    # Test Rs. 100 green note
    jpg_100 = make_synthetic_note(100)
    res_100 = service.identify(jpg_100)
    assert res_100["status"] == "identified"
    assert res_100["denomination"] == 100
    assert "एक सय" in res_100["spoken_text"]

    # Test Rs. 20 orange note
    jpg_20 = make_synthetic_note(20)
    res_20 = service.identify(jpg_20)
    assert res_20["status"] == "identified"
    assert res_20["denomination"] == 20


def test_auto_currency_pipeline_speech_and_debouncing():
    speech_backend = FakeSpeechBackend()
    from app.audio.speaker import SpeechManager
    speech_mgr = SpeechManager(backend=speech_backend)
    speech_mgr.start()

    service = CurrencyService()
    pipeline = PerceptionPipeline(
        engine=NativeVisionEngine(),
        speech_manager=speech_mgr,
        currency_service=service,
        auto_currency_enabled=True,
    )

    jpg_100 = make_synthetic_note(100)
    packet_1 = FramePacket(
        frame_id=1,
        captured_at=time.time(),
        jpeg_bytes=jpg_100,
        width=640,
        height=480,
        source_id="test",
        session_id="test"
    )

    # First frame with Rs 100 note
    res1 = pipeline.process_frame(packet_1)
    assert res1.auto_currency is not None
    assert res1.auto_currency["denomination"] == 100

    # Verify announcement was triggered
    time.sleep(0.05)
    history = list(speech_backend.spoken_history)
    assert len(history) >= 1
    assert any("एक सय" in h or "100" in h for h in history)

    # Second consecutive frame within cooldown period should NOT spam speech
    count_before = len(speech_backend.spoken_history)
    packet_2 = FramePacket(
        frame_id=2,
        captured_at=time.time(),
        jpeg_bytes=jpg_100,
        width=640,
        height=480,
        source_id="test",
        session_id="test"
    )
    pipeline._last_auto_currency_time = 0.0  # simulate tick after 0.7s
    res2 = pipeline.process_frame(packet_2)
    assert res2.auto_currency is not None
    count_after = len(speech_backend.spoken_history)
    assert count_after == count_before  # No duplicate announcement!

    # Now present Rs 20 note -> should announce immediately because denomination changed
    jpg_20 = make_synthetic_note(20)
    packet_3 = FramePacket(
        frame_id=3,
        captured_at=time.time() + 1.0,
        jpeg_bytes=jpg_20,
        width=640,
        height=480,
        source_id="test",
        session_id="test"
    )
    pipeline._last_auto_currency_time = 0.0  # simulate next interval
    res3 = pipeline.process_frame(packet_3)
    assert res3.auto_currency is not None
    assert res3.auto_currency["denomination"] == 20

    time.sleep(0.05)
    history_after = list(speech_backend.spoken_history)
    assert len(history_after) > count_after
    assert any("बीस" in h or "20" in h for h in history_after)


def test_auto_currency_rest_endpoints():
    app = create_app()
    with TestClient(app) as client:
        # Check auto mode status
        r = client.get("/api/currency/auto-mode")
        assert r.status_code == 200
        assert "enabled" in r.json()
        assert r.json()["model_ready"] is True

        # Toggle auto mode off
        r_off = client.post("/api/currency/auto-mode", json={"enabled": False})
        assert r_off.status_code == 200
        assert r_off.json()["enabled"] is False

        # Toggle auto mode back on
        r_on = client.post("/api/currency/auto-mode", json={"enabled": True})
        assert r_on.status_code == 200
        assert r_on.json()["enabled"] is True
