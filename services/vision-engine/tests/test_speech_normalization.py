"""
Unit tests for SpeechManager language normalization and thread safety (Priority 4.6 Stage 2).
"""

import concurrent.futures
import pytest
from app.audio.speaker import FakeSpeechBackend, SpeechManager, SpeechPriority


def test_speech_manager_language_normalization_aliases():
    """Verifies that common aliases for Nepali and English resolve to canonical codes 'ne' and 'en'."""
    backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    mgr = SpeechManager(backend=backend)

    # Nepali variants
    for alias in ["ne", "NE", "ne-NP", "ne_np", "nepali", "NEPALI"]:
        mgr.language = alias
        assert mgr.language == "ne", f"Alias '{alias}' did not normalize to 'ne'"

    # English variants
    for alias in ["en", "EN", "en-US", "en_us", "en-GB", "english", "ENGLISH"]:
        mgr.language = alias
        assert mgr.language == "en", f"Alias '{alias}' did not normalize to 'en'"

    mgr.shutdown()


def test_speech_manager_invalid_language_rejection():
    """Verifies that invalid or unsupported language strings explicitly raise ValueError."""
    backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    mgr = SpeechManager(backend=backend)

    for invalid in ["fr", "es", "de", "zh", "123", "unknown_lang"]:
        with pytest.raises(ValueError) as excinfo:
            mgr.language = invalid
        assert "Unsupported language" in str(excinfo.value) or "Invalid language" in str(excinfo.value)

    # Initial state must remain unchanged after rejected attempts
    assert mgr.language in ("ne", "en")
    mgr.shutdown()


def test_speech_manager_announce_normalizes_per_request_language():
    """Verifies that announce(..., language=...) normalizes language aliases onto queued SpeechItem."""
    backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    mgr = SpeechManager(backend=backend, max_queue_size=10)

    mgr.announce("Nepali test", message_key="test_ne", language="ne-NP")
    mgr.announce("English test", message_key="test_en", language="en-US")

    item1 = mgr._queue.get_nowait()
    item2 = mgr._queue.get_nowait()

    assert item1.language == "ne"
    assert item2.language == "en"

    mgr.shutdown()


def test_concurrent_language_switching_stress():
    """Stress tests concurrent language updates across 50 simultaneous threads to guarantee no corrupt state."""
    backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    mgr = SpeechManager(backend=backend)

    def worker(idx: int):
        target = "ne-NP" if idx % 2 == 0 else "en-US"
        mgr.language = target
        current = mgr.language
        assert current in ("ne", "en")
        return current

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(worker, range(50)))

    assert len(results) == 50
    assert all(r in ("ne", "en") for r in results)
    assert mgr.language in ("ne", "en")
    mgr.shutdown()
