"""
Audio In/Out Hardware Abstraction Layer (HAL) Interfaces.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional
from trinetra_core.events.schema import EventPriority


class AudioInAdapterInterface(ABC):
    """
    Abstract interface for microphone input and acoustic stream ingestion.
    """

    @abstractmethod
    def start_listening(self, chunk_callback: Callable[[bytes], None], sample_rate: int = 16000) -> bool:
        """Start capturing audio stream in 16kHz mono chunks."""
        pass

    @abstractmethod
    def stop_listening(self) -> None:
        """Stop capturing audio stream."""
        pass

    @abstractmethod
    def is_listening(self) -> bool:
        """Return True if microphone stream is actively recording."""
        pass


class AudioOutAdapterInterface(ABC):
    """
    Abstract interface for speech synthesis and audible chimes.
    Supported backends:
    - Piper Neural TTS (Local CPU)
    - Windows SAPI5 / WinRT fallback
    - Android native TextToSpeech
    - MockAudioOutAdapter (Testing)
    """

    @abstractmethod
    def speak(
        self,
        text: str,
        priority: EventPriority = EventPriority.NORMAL,
        language: str = "ne",
        interrupt: bool = False,
    ) -> bool:
        """
        Synthesize and emit spoken audio.
        If priority == CRITICAL_HAZARD or interrupt == True, immediately
        preempt any currently playing audio.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Abort currently playing audio immediately."""
        pass

    @abstractmethod
    def is_speaking(self) -> bool:
        """Return True if an audio phrase is currently outputting to speaker."""
        pass

    @abstractmethod
    def set_speech_rate(self, rate: float) -> None:
        """Set relative speech rate (1.0 = normal, 1.5 = fast)."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Return queue length, active language, and backend health."""
        pass
