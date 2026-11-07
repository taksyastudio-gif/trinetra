"""
Unit tests for Trinetra Offline Speech-to-Text & Voice Command Engine (stt.py).
"""
import io
import os
import struct
import sys
import wave
import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.audio.stt import (
    OfflineSpeechRecognizer,
    TranscriptionResult,
    SUPPORTED_VOICE_COMMANDS,
    COMMAND_TRIGGERS,
    offline_stt_engine,
)


def make_test_wav(
    duration_sec: float = 0.8,
    sample_rate: int = 16000,
    frequency: float = 440.0,
    amplitude: float = 0.5,
    noise_ratio: float = 0.0,
) -> bytes:
    """Generates a synthetic mono 16-bit PCM WAV in memory."""
    num_samples = int(duration_sec * sample_rate)
    t = np.linspace(0, duration_sec, num_samples, endpoint=False)
    signal = amplitude * np.sin(2 * np.pi * frequency * t)

    if noise_ratio > 0.0:
        noise = np.random.uniform(-1, 1, num_samples) * noise_ratio
        signal = signal + noise

    # Clip and convert to int16
    signal = np.clip(signal, -1.0, 1.0)
    int_samples = (signal * 32767.0).astype(np.int16)

    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int_samples.tobytes())

    return bio.getvalue()


def make_silence_wav(duration_sec: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Generates a purely silent WAV in memory."""
    num_samples = int(duration_sec * sample_rate)
    samples = np.zeros(num_samples, dtype=np.int16)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return bio.getvalue()


def test_supported_commands_registry():
    assert "currency" in SUPPORTED_VOICE_COMMANDS
    assert "scene" in SUPPORTED_VOICE_COMMANDS
    assert "ocr" in SUPPORTED_VOICE_COMMANDS
    assert "bookmark" in SUPPORTED_VOICE_COMMANDS
    assert "mute" in SUPPORTED_VOICE_COMMANDS
    assert "help" in SUPPORTED_VOICE_COMMANDS


def test_decode_valid_wav():
    recognizer = OfflineSpeechRecognizer()
    wav_bytes = make_test_wav(duration_sec=0.5, frequency=300.0)
    samples, rate = recognizer.decode_audio_bytes(wav_bytes)
    assert rate == 16000
    assert len(samples) == 8000
    assert np.max(np.abs(samples)) > 0.1


def test_decode_invalid_audio_raises_error():
    recognizer = OfflineSpeechRecognizer()
    with pytest.raises(ValueError):
        recognizer.decode_audio_bytes(b"not_a_valid_wav_header")


def test_resample_audio():
    recognizer = OfflineSpeechRecognizer(target_sample_rate=16000)
    orig_samples = np.sin(np.linspace(0, 10, 44100)).astype(np.float32)
    resampled = recognizer.resample_if_needed(orig_samples, 44100)
    assert len(resampled) == 16000


def test_vad_detects_speech_and_rejects_silence():
    recognizer = OfflineSpeechRecognizer()

    # Active tone
    speech_wav = make_test_wav(duration_sec=0.6, amplitude=0.4)
    samples, _ = recognizer.decode_audio_bytes(speech_wav)
    has_speech, segment = recognizer.compute_vad(samples)
    assert has_speech is True
    assert len(segment) > 0

    # Pure silence
    silence_wav = make_silence_wav(duration_sec=0.5)
    silence_samples, _ = recognizer.decode_audio_bytes(silence_wav)
    has_speech_sil, segment_sil = recognizer.compute_vad(silence_samples)
    assert has_speech_sil is False
    assert len(segment_sil) == 0


def test_match_transcript_nepali_commands():
    recognizer = OfflineSpeechRecognizer()

    # Currency
    res = recognizer.transcribe(text_transcript="यो पैसा हेर त")
    assert res.status == "recognized"
    assert res.command == "currency"

    # Scene
    res = recognizer.transcribe(text_transcript="वरिपरि के छ?")
    assert res.status == "recognized"
    assert res.command == "scene"

    # OCR
    res = recognizer.transcribe(text_transcript="यो अक्षर पढ्नुहोस्")
    assert res.status == "recognized"
    assert res.command == "ocr"

    # Bookmark
    res = recognizer.transcribe(text_transcript="यो ठाउँ याद राख त")
    assert res.status == "recognized"
    assert res.command == "bookmark"

    # Mute
    res = recognizer.transcribe(text_transcript="कृपया चुप लाग")
    assert res.status == "recognized"
    assert res.command == "mute"

    # Help
    res = recognizer.transcribe(text_transcript="मलाई मद्दत गर्नुहोस्")
    assert res.status == "recognized"
    assert res.command == "help"


def test_match_transcript_english_commands():
    recognizer = OfflineSpeechRecognizer()

    assert recognizer.transcribe(text_transcript="check money").command == "currency"
    assert recognizer.transcribe(text_transcript="describe what is ahead").command == "scene"
    assert recognizer.transcribe(text_transcript="read this text").command == "ocr"
    assert recognizer.transcribe(text_transcript="save location").command == "bookmark"
    assert recognizer.transcribe(text_transcript="stop speech").command == "mute"
    assert recognizer.transcribe(text_transcript="help me").command == "help"


def test_transcribe_silence_audio():
    recognizer = OfflineSpeechRecognizer()
    silence_wav = make_silence_wav(0.6)
    res = recognizer.transcribe(audio_bytes=silence_wav)
    assert res.status == "silence"
    assert res.command == "none"
    assert "कुनै आवाज सुनिएन" in res.message


def test_transcribe_empty_audio():
    recognizer = OfflineSpeechRecognizer()
    res = recognizer.transcribe(audio_bytes=b"")
    assert res.status == "invalid_audio"
    assert res.command == "none"


def test_classify_acoustic_mute_profile():
    recognizer = OfflineSpeechRecognizer()
    # "चुप" profile: short burst (0.3s) with sharp decay in coda
    num_samples = int(0.35 * 16000)
    t = np.linspace(0, 0.35, num_samples, endpoint=False)
    # Fast decaying exponential envelope
    decay = np.exp(-15 * t)
    samples = (decay * np.sin(2 * np.pi * 300 * t)).astype(np.float32)

    cmd, trigger, conf = recognizer.classify_acoustic_features(samples)
    assert cmd == "mute"
    assert trigger == "चुप"
    assert conf >= 0.70


def test_api_stt_endpoints():
    import base64
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. GET /api/speech/stt/status
    res = client.get("/api/speech/stt/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["offline"] is True
    assert "currency" in data["supported_commands"]

    # 2. POST /api/speech/transcribe with text transcript
    res2 = client.post("/api/speech/transcribe", json={"transcript": "यो पैसा हेर त"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "recognized"
    assert data2["command"] == "currency"

    # 3. POST /api/speech/transcribe with synthetic WAV audio
    wav_bytes = make_test_wav(0.4, amplitude=0.4)
    b64 = base64.b64encode(wav_bytes).decode("ascii")
    res3 = client.post("/api/speech/transcribe", json={"audio_base64": b64})
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["is_offline"] is True
    assert "status" in data3
