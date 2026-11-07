"""
Phase 4 Unit Tests: Culture, Bikram Sambat Calendar, Traffic Noise Filtering, and Voice Capabilities.
"""
import os
import sys
from datetime import date
import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.culture import BikramSambatConverter, NepaliPhrasing, BSDatetime
from app.audio.noise_filter import TrafficNoiseFilter
from app.audio.speaker import SpeechManager, SpeechPriority
from app.assistant import AssistantDialogueManager, CodeSwitchingInterpreter


def test_bikram_sambat_converter_calibration():
    # 2026-11-07 Gregorian calibrated anchor
    anchor_ad = date(2026, 11, 7)
    bs_y, bs_m, bs_d = BikramSambatConverter.from_gregorian(anchor_ad)
    assert bs_y == 2083
    assert bs_m == 7
    assert bs_d == 22


def test_bikram_sambat_current_bs_spoken():
    anchor_ad = date(2026, 11, 7)
    import datetime
    dt = datetime.datetime(2026, 11, 7, 12, 0, 0)
    bs = BikramSambatConverter.get_current_bs(dt.timestamp())
    assert bs.year == 2083
    assert bs.month == 7
    assert bs.month_name_ne == "कात्तिक"
    assert "२०८३" in bs.formatted_ne or "2083" in bs.formatted_ne
    assert len(bs.spoken_phrase_ne) > 0
    assert bs.weekday_name_ne == "शनिबार"


def test_bikram_sambat_festival_recognition():
    # New Year Baishakh 1
    festival = BikramSambatConverter.FIXED_FESTIVALS.get((1, 1))
    assert festival is not None
    assert "नयाँ वर्ष" in festival

    # Dashain / Vijaya Dashami
    dashain = BikramSambatConverter.SEASONAL_FESTIVALS.get((6, 25))
    assert dashain is not None
    assert "दशैँ" in dashain


def test_nepali_phrasing_spatial():
    phrase_center = NepaliPhrasing.format_spatial_directive("पानीको खाल्डो", "center", distance_m=2.0)
    assert "सिधा अगाडि" in phrase_center
    assert "पानीको खाल्डो" in phrase_center
    assert "२ मिटरमा" in phrase_center or "2 मिटरमा" in phrase_center

    phrase_left = NepaliPhrasing.format_spatial_directive("मोटरसाइकल", "left")
    assert "बायाँतिर" in phrase_left
    assert "मोटरसाइकल" in phrase_left

    hazard_alert = NepaliPhrasing.format_hazard_alert("खुल्ला नाली", "दायाँ सर्किनुहोस्")
    assert "होसियार" in hazard_alert
    assert "खुल्ला नाली" in hazard_alert


def test_traffic_noise_filter_high_pass():
    filter_engine = TrafficNoiseFilter(sample_rate=16000, low_cutoff_hz=200.0)
    t = np.linspace(0, 0.5, 8000, endpoint=False)
    # 50 Hz heavy diesel engine rumble
    rumble = 0.8 * np.sin(2 * np.pi * 50 * t).astype(np.float32)
    # 1000 Hz human voice harmonic
    voice = 0.5 * np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    composite = rumble + voice

    filtered = filter_engine.high_pass_iir(composite, cutoff_hz=200.0)

    # 50 Hz power should be significantly attenuated
    power_orig_50 = np.mean(rumble**2)
    power_filt_50 = np.mean((filtered - voice)**2)
    assert power_filt_50 < power_orig_50 * 0.35


def test_traffic_noise_filter_pcm16_pipeline():
    filter_engine = TrafficNoiseFilter(sample_rate=16000)
    # 1 second of noise + signal
    t = np.linspace(0, 1.0, 16000, endpoint=False)
    synthetic = (0.5 * np.sin(2 * np.pi * 800 * t) * 32767).astype(np.int16)
    raw_bytes = synthetic.tobytes()

    cleaned_bytes = filter_engine.filter_pcm16(raw_bytes)
    assert len(cleaned_bytes) == len(raw_bytes)
    assert isinstance(cleaned_bytes, bytes)


def test_code_switching_interpreter():
    # Romanized mixed
    assert CodeSwitchingInterpreter.detect_intent("aaja ko date k ho?") == "date_festival"
    assert CodeSwitchingInterpreter.detect_intent("paisa kati ho") == "currency"
    assert CodeSwitchingInterpreter.detect_intent("haraye ma ta") == "lost_guidance"
    assert CodeSwitchingInterpreter.detect_intent("aushadhi khane bela vayo") == "medication"

    # English
    assert CodeSwitchingInterpreter.detect_intent("what is the date today") == "date_festival"
    assert CodeSwitchingInterpreter.detect_intent("any medicine reminder") == "medication"
    assert CodeSwitchingInterpreter.detect_intent("emergency help me") == "emergency"
    assert CodeSwitchingInterpreter.detect_intent("repeat that again") == "repeat"

    # Devanagari
    assert CodeSwitchingInterpreter.detect_intent("आज कति गते हो?") == "date_festival"
    assert CodeSwitchingInterpreter.detect_intent("औषधिको समय") == "medication"
    assert CodeSwitchingInterpreter.detect_intent("म कहाँ छु?") == "lost_guidance"
    assert CodeSwitchingInterpreter.detect_intent("नेपाल प्रहरी बोलाउ आपतकालीन") == "emergency"


def test_speech_rate_control():
    manager = SpeechManager()
    assert manager.speech_rate == 1.0

    manager.speech_rate = 1.5
    assert manager.speech_rate == 1.5

    # Bounds clamping test [0.5, 2.5]
    manager.speech_rate = 0.1
    assert manager.speech_rate == 0.5

    manager.speech_rate = 5.0
    assert manager.speech_rate == 2.5
    manager.shutdown()
