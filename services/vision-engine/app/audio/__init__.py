"""
Trinetra Audio and Speech Package
"""
from app.audio.speaker import (
    SpeechPriority,
    SpeechItem,
    SpeechBackend,
    WindowsSapiSpeechBackend,
    FakeSpeechBackend,
    SpeechManager,
)
from app.audio.piper_backend import (
    PiperSpeechBackend,
    CompositeSpeechBackend,
    is_piper_available,
)

__all__ = [
    "SpeechPriority",
    "SpeechItem",
    "SpeechBackend",
    "WindowsSapiSpeechBackend",
    "FakeSpeechBackend",
    "SpeechManager",
    "PiperSpeechBackend",
    "CompositeSpeechBackend",
    "is_piper_available",
]
