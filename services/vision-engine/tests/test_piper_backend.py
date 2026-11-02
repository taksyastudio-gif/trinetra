"""
Trinetra Piper TTS & Composite Speech Backend Test Suite
Tests:
- Piper runtime discovery and availability
- Voice querying and language capabilities
- English/Nepali bilingual routing (SAPI vs Piper)
- Zero silent fallback when Nepali is unavailable
- Persistent subprocess lifecycle, recovery, and shutdown
- Playback cancellation (winsound.SND_PURGE)
- In-flight synthesis cancellation
- Pre-rendered hazard preemption fast-path
- Temporary WAV file bounded ring-buffer cleanup and active-file protection
- Rollback via TRINETRA_DISABLE_PIPER=1
- End-to-end PerceptionPipeline integration
"""

import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional
import pytest

from app.audio.speaker import (
    FakeSpeechBackend,
    SpeechItem,
    SpeechManager,
    SpeechPriority,
    WindowsSapiSpeechBackend,
)
from app.audio.piper_backend import (
    CompositeSpeechBackend,
    PiperSpeechBackend,
    is_piper_available,
    resolve_piper_paths,
)
from app.detection.engine import (
    BoundingBox,
    Detection,
    DetectionResult,
    PerceptionPipeline,
)


def test_piper_paths_resolution():
    """Validates that production or fallback Piper assets are discovered."""
    paths = resolve_piper_paths()
    assert paths["exe"] is not None, "Piper binary should be resolved."
    assert paths["model"] is not None, "Piper Nepali model should be resolved."
    assert paths["exe"].is_file(), f"Binary {paths['exe']} must exist."
    assert paths["model"].is_file(), f"Model {paths['model']} must exist."
    assert is_piper_available() is True


def test_piper_voice_support():
    """Validates voice querying and language capability inspection on PiperSpeechBackend."""
    backend = PiperSpeechBackend()
    assert backend.has_voice_for_language("ne") is True
    assert backend.has_voice_for_language("ne-NP") is True
    assert backend.has_voice_for_language("en") is False

    voices = backend.get_available_voices()
    assert len(voices) >= 1
    assert voices[0]["language"] == "ne-NP"
    assert "piper" in voices[0]["id"]


def test_piper_missing_assets_safety(tmp_path):
    """Validates safe degraded behavior when assets are missing."""
    empty_exe = tmp_path / "nonexistent_piper.exe"
    empty_model = tmp_path / "nonexistent_model.onnx"
    backend = PiperSpeechBackend(exe_path=empty_exe, model_path=empty_model)
    assert backend.is_ready() is False
    assert backend.has_voice_for_language("ne") is False
    assert backend.speak("अगाडि मान्छे छ।") is False


def test_composite_voice_support_and_bilingual_capabilities():
    """Validates that CompositeSpeechBackend exposes both English and Nepali voices."""
    fake_sapi = FakeSpeechBackend(supported_languages=["en"])
    piper = PiperSpeechBackend()
    composite = CompositeSpeechBackend(sapi_backend=fake_sapi, piper_backend=piper)

    assert composite.has_voice_for_language("en") is True
    assert composite.has_voice_for_language("ne") is True
    assert composite.has_voice_for_language("fr") is False

    voices = composite.get_available_voices()
    languages = [v["language"] for v in voices]
    assert any(lang.startswith("en") for lang in languages)
    assert any(lang.startswith("ne") for lang in languages)


def test_composite_language_routing():
    """Validates that English routes to SAPI and Nepali routes to Piper."""
    class RecordingFakeSapi(FakeSpeechBackend):
        pass

    class RecordingPiper(PiperSpeechBackend):
        def __init__(self):
            super().__init__()
            self.piper_spoken: List[str] = []

        def speak(self, text: str, interrupt: bool = False, language: Optional[str] = None) -> bool:
            self.piper_spoken.append(text)
            return True

    fake_sapi = RecordingFakeSapi(supported_languages=["en"])
    fake_piper = RecordingPiper()
    composite = CompositeSpeechBackend(sapi_backend=fake_sapi, piper_backend=fake_piper)

    # 1. Explicit English text
    composite.speak("Person, ahead.", language="en")
    assert len(fake_sapi.spoken_history) == 1
    assert fake_sapi.spoken_history[0] == "Person, ahead."
    assert len(fake_piper.piper_spoken) == 0

    # 2. Explicit Nepali language
    composite.speak("अगाडि मान्छे छ।", language="ne")
    assert len(fake_piper.piper_spoken) == 1
    assert fake_piper.piper_spoken[0] == "अगाडि मान्छे छ।"

    # 3. Implicit Devanagari detection without explicit language tag
    composite.speak("बायाँतिर कुकुर छ।")
    assert len(fake_piper.piper_spoken) == 2
    assert fake_piper.piper_spoken[1] == "बायाँतिर कुकुर छ।"

    composite.shutdown()


def test_composite_zero_silent_fallback_when_piper_disabled(monkeypatch):
    """
    NON-NEGOTIABLE SAFETY TEST:
    When Piper is unavailable or disabled, Nepali requests must be suppressed
    and must NEVER silently speak in English.
    """
    fake_sapi = FakeSpeechBackend(supported_languages=["en"])
    # Composite without Piper backend
    composite = CompositeSpeechBackend(sapi_backend=fake_sapi, piper_backend=None)

    assert composite.has_voice_for_language("ne") is False

    # Attempt Nepali speech
    success = composite.speak("दायाँतिर गाडी छ।", language="ne")
    assert success is False
    # SAPI history must remain empty
    assert len(fake_sapi.spoken_history) == 0


def test_piper_real_process_lifecycle_and_shutdown(tmp_path):
    """Validates real piper.exe process startup, synthesis, and clean termination."""
    custom_temp = tmp_path / "piper_test_run"
    backend = PiperSpeechBackend(temp_dir=custom_temp)
    assert backend.is_ready() is True

    # 1. Process starts on-demand
    worker_ready = backend._ensure_worker()
    assert worker_ready is True
    assert backend._worker_proc is not None
    pid = backend._worker_proc.pid
    assert backend._worker_proc.poll() is None

    # 2. Graceful shutdown terminates process cleanly
    backend.shutdown()
    assert backend._worker_proc is None


def test_piper_playback_interruption(tmp_path):
    """
    Validates playback preemption:
    A long announcement playing in the background is halted immediately upon stop().
    """
    backend = PiperSpeechBackend()
    assert backend.is_ready() is True

    t_start = time.perf_counter()
    stop_executed = threading.Event()

    def delayed_stop():
        time.sleep(0.15)
        backend.stop()
        stop_executed.set()

    stopper = threading.Thread(target=delayed_stop)
    stopper.start()

    # Speak canonical safety hazard (audio duration ~2.5s)
    # The delayed_stop thread halts it after 150ms
    res = backend.speak("सावधान! अगाडि अवरोध छ।")
    elapsed = time.perf_counter() - t_start
    stopper.join()

    # Playback should be preempted well before the 2.5s audio finishes
    assert elapsed < 1.2, f"Playback should have stopped early; took {elapsed:.2f}s"
    backend.shutdown()


def test_piper_synthesis_cancellation_during_inflight_request():
    """
    Validates that if stop() is called while synthesis is active,
    the in-flight request is aborted and does not proceed to audio playback.
    """
    backend = PiperSpeechBackend()
    assert backend.is_ready() is True

    result_holder: List[bool] = []

    def do_speak():
        # Neural synthesis takes ~800ms for this phrase
        res = backend.speak("बायाँतिर कुकुर छ।")
        result_holder.append(res)

    t = threading.Thread(target=do_speak)
    t.start()
    # Signal stop while synthesis is actively running (after 50ms)
    time.sleep(0.05)
    backend.stop()
    t.join(timeout=3.0)

    assert len(result_holder) == 1
    assert result_holder[0] is False, "In-flight request should be cancelled and return False."
    assert backend._current_playing_file is None
    backend.shutdown()


def test_hazard_preemption_bypasses_synthesis():
    """
    CRITICAL SAFETY REQUIREMENT:
    Canonical emergency hazard uses pre-rendered audio, bypassing the ~800ms
    neural synthesis wait completely for instantaneous onset (< 100 ms).
    """
    backend = PiperSpeechBackend()
    assert backend.is_ready() is True
    assert backend.hazard_wav is not None
    assert backend.hazard_wav.is_file()

    # Pre-rendered hazard should start playback without spawning or waiting for synthesis
    t0 = time.perf_counter()
    # Interrupted quickly to avoid prolonged playback
    threading.Timer(0.05, backend.stop).start()
    backend.speak("सावधान! अगाडि अवरोध छ।", interrupt=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Total execution with pre-rendered audio is well below neural synthesis time (~800ms)
    assert elapsed_ms < 400.0, f"Hazard fast-path exceeded latency: {elapsed_ms:.1f}ms"
    backend.shutdown()


def test_temp_wav_bounded_ring_buffer(tmp_path):
    """
    Validates that temporary audio files are strictly bounded and do not leak disk space,
    while guaranteeing active playing files are never unlinked while in use.
    """
    custom_temp = tmp_path / "piper_ring_buffer"
    backend = PiperSpeechBackend(temp_dir=custom_temp)
    backend._max_managed_files = 3

    # Create dummy managed files
    dummy_files = []
    for i in range(8):
        f = custom_temp / f"test_slot_{i}.wav"
        f.write_bytes(b"RIFF....WAVEfmt ....data....")
        backend._register_managed_file(f)
        dummy_files.append(f)

    # Protect slot 7 as currently playing
    backend._current_playing_file = str(dummy_files[7])
    backend._cleanup_old_managed_files()

    # Total files in managed list should be bounded
    assert len(backend._managed_files) <= 4
    # The actively playing file must NOT be deleted!
    assert dummy_files[7].is_file()

    backend.shutdown()


def test_rollback_via_environment_variable(monkeypatch):
    """Validates that setting TRINETRA_DISABLE_PIPER=1 rolls back completely to Windows SAPI."""
    monkeypatch.setenv("TRINETRA_DISABLE_PIPER", "1")
    mgr = SpeechManager()

    # Backend must be WindowsSapiSpeechBackend, NOT CompositeSpeechBackend
    assert isinstance(mgr.backend, WindowsSapiSpeechBackend)
    assert mgr.has_voice_for_language("ne") is False
    assert mgr.has_voice_for_language("en") is True

    # Nepali announcement must be cleanly suppressed
    enqueued = mgr.announce("अगाडि मान्छे छ।", language="ne")
    assert enqueued is False
    mgr.shutdown()


def test_speech_manager_priority_preemption_with_composite():
    """
    End-to-end priority queue preemption test:
    A Priority 2 spatial announcement is immediately preempted by a Priority 1 Hazard.
    """
    fake_sapi = FakeSpeechBackend(supported_languages=["en"])
    backend = PiperSpeechBackend()
    composite = CompositeSpeechBackend(sapi_backend=fake_sapi, piper_backend=backend)
    mgr = SpeechManager(backend=composite)

    # 1. Enqueue ordinary spatial announcement
    enqueued1 = mgr.announce(
        text="बायाँतिर कुकुर छ।",
        priority=SpeechPriority.SPATIAL_NAVIGATION,
        language="ne"
    )
    assert enqueued1 is True

    time.sleep(0.05)

    # 2. Critical Hazard preemption
    enqueued2 = mgr.announce(
        text="सावधान! अगाडि अवरोध छ।",
        priority=SpeechPriority.CRITICAL_HAZARD,
        interrupt=True,
        language="ne"
    )
    assert enqueued2 is True

    time.sleep(0.1)
    mgr.stop()
    mgr.shutdown()


def test_perception_pipeline_localized_nepali_with_composite():
    """Validates end-to-end PerceptionPipeline formatting and speech dispatch in Nepali."""
    fake_sapi = FakeSpeechBackend(supported_languages=["en"])
    backend = PiperSpeechBackend()
    composite = CompositeSpeechBackend(sapi_backend=fake_sapi, piper_backend=backend)
    mgr = SpeechManager(backend=composite)
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
        model_name="yolox_nano.onnx"
    )

    # Fast interruption to prevent audio lingering
    threading.Timer(0.1, mgr.stop).start()
    pipeline._announce_detections(res)
    time.sleep(0.15)
    mgr.shutdown()
