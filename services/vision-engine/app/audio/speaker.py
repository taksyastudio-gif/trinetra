"""
Trinetra Non-Blocking Speech Service
Prioritized, asynchronous speech announcement engine with deduplication,
cooldown suppression, and instant interruption support.
"""

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trinetra.audio")


class SpeechPriority(IntEnum):
    """
    Priority rankings for audio announcements.
    Lower numerical values represent higher urgency.
    """
    CRITICAL_HAZARD = 1      # Immediate preemption (e.g. collision hazard, drop-off)
    SPATIAL_NAVIGATION = 2   # Directional obstacles and spatial orientation
    INFORMATIONAL = 3        # State updates (e.g. camera started, mode changed)


@dataclass(order=True)
class SpeechItem:
    """Prioritized queue item representing an announcement."""
    priority: int
    timestamp: float
    text: str = field(compare=False)
    message_key: str = field(compare=False)
    interrupt: bool = field(default=False, compare=False)
    language: str = field(default="ne", compare=False)


class SpeechBackend(ABC):
    """Abstract contract for platform-specific speech engines."""

    @abstractmethod
    def speak(self, text: str, interrupt: bool = False, language: Optional[str] = None) -> bool:
        """Synthesizes and speaks text. Returns True on success."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Immediately halts any currently speaking audio."""
        pass

    @abstractmethod
    def get_available_voices(self) -> List[Dict[str, Any]]:
        """Returns installed voices on the system."""
        pass

    @abstractmethod
    def has_voice_for_language(self, lang: str) -> bool:
        """Returns True if a voice for the specified language code is available."""
        pass

    @property
    def speech_rate(self) -> float:
        return getattr(self, "_speech_rate", 1.0)

    @speech_rate.setter
    def speech_rate(self, value: float) -> None:
        self._speech_rate = max(0.5, min(2.5, float(value)))

    def shutdown(self) -> None:
        """Cleans up any long-lived resources or worker processes."""
        pass


PS_SPEECH_WORKER = """
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$asTaskMethod = $asTaskGeneric.MakeGenericMethod([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
[Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media, ContentType = WindowsRuntime] | Out-Null
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$player = New-Object System.Media.SoundPlayer

[Console]::Out.WriteLine("READY:winrt")
[Console]::Out.Flush()

while ($line = [Console]::In.ReadLine()) {
    if ($null -eq $line -or $line -eq '__QUIT__') { break }
    if ($line -eq 'STOP') {
        $player.Stop()
        [Console]::Out.WriteLine("STOPPED")
        [Console]::Out.Flush()
    }
    elseif ($line.StartsWith('SPEAK:')) {
        $text = $line.Substring(6).Trim()
        $t0 = [System.Diagnostics.Stopwatch]::StartNew()
        $op = $synth.SynthesizeTextToStreamAsync($text)
        $task = $asTaskMethod.Invoke($null, @($op))
        $stream = $task.GetAwaiter().GetResult()
        $netStream = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream)
        
        $durSec = [Math]::Max(0.2, [Math]::Round([double]$stream.Size / 32000.0, 2))
        $player.Stream = $netStream
        $player.Play()
        $t0.Stop()
        [Console]::Out.WriteLine("STARTED:" + $durSec + ":" + $t0.ElapsedMilliseconds)
        [Console]::Out.Flush()
    }
}
"""


class WindowsSapiSpeechBackend(SpeechBackend):
    """
    High-performance Windows speech backend using persistent WinRT SpeechSynthesizer worker.
    Zero cloud dependencies, zero external pip packages.
    Maintains a single background worker process to eliminate cold CLR startup latency (~5600ms -> ~80ms).
    """

    def __init__(self):
        self._current_proc: Optional[subprocess.Popen] = None
        self._worker_proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._worker_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cached_voices: Optional[List[Dict[str, Any]]] = None

    def _ensure_worker(self) -> bool:
        with self._worker_lock:
            if self._worker_proc is not None and self._worker_proc.poll() is None:
                return True
            try:
                encoded = base64.b64encode(PS_SPEECH_WORKER.encode("utf-16le")).decode("ascii")
                proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    encoding="utf-8"
                )
                ready_line = proc.stdout.readline().strip()
                if not ready_line.startswith("READY:"):
                    logger.warning(f"Speech worker unexpected ready handshake: {ready_line}")
                    proc.terminate()
                    return False
                self._worker_proc = proc
                return True
            except Exception as exc:
                logger.warning(f"Failed to spawn persistent speech worker: {exc}")
                return False

    def speak(self, text: str, interrupt: bool = False, language: Optional[str] = None) -> bool:
        if interrupt:
            self.stop()

        # Sanitize text to avoid formatting anomalies while preserving Unicode Devanagari characters
        clean_text = "".join(c for c in text if c.isalnum() or ("\u0900" <= c <= "\u097f") or c in " ,.!?'-_।").strip()
        if not clean_text:
            return False

        if not self._ensure_worker():
            return False

        self._stop_event.clear()
        with self._worker_lock:
            try:
                self._worker_proc.stdin.write(f"SPEAK:{clean_text}\n")
                self._worker_proc.stdin.flush()
                resp = self._worker_proc.stdout.readline().strip()
                if not resp.startswith("STARTED:"):
                    logger.warning(f"Speech worker error response: {resp}")
                    return False
                parts = resp.split(":")
                dur_sec = float(parts[1])
            except Exception as exc:
                logger.warning(f"Error communicating with speech worker: {exc}")
                return False

        # Wait for audio to play or until preempted/stopped
        self._stop_event.wait(timeout=dur_sec)
        return True

    def _stop_worker_audio(self) -> None:
        with self._worker_lock:
            if self._worker_proc and self._worker_proc.poll() is None:
                try:
                    self._worker_proc.stdin.write("STOP\n")
                    self._worker_proc.stdin.flush()
                    _ = self._worker_proc.stdout.readline()
                except Exception:
                    pass

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            proc = self._current_proc
            self._current_proc = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        self._stop_worker_audio()

    def get_available_voices(self) -> List[Dict[str, Any]]:
        if self._cached_voices is not None:
            return self._cached_voices
        try:
            ps_query = """
            [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media, ContentType = WindowsRuntime] | Out-Null
            [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Select-Object Id, DisplayName, Language, Gender | ConvertTo-Json
            """
            encoded = base64.b64encode(ps_query.encode("utf-16le")).decode("ascii")
            p = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True,
                text=True,
                timeout=5.0
            )
            data = json.loads(p.stdout)
            if isinstance(data, dict):
                data = [data]
            voices = [
                {
                    "id": v.get("Id", ""),
                    "name": v.get("DisplayName", ""),
                    "language": v.get("Language", ""),
                    "gender": "female" if v.get("Gender") == 1 else "male"
                }
                for v in data
            ]
            self._cached_voices = voices
            return voices
        except Exception as exc:
            logger.warning(f"Failed to query available voices: {exc}")
            return []

    def has_voice_for_language(self, lang: str) -> bool:
        norm = lang.strip().lower()
        for v in self.get_available_voices():
            v_lang = v.get("language", "").lower()
            if v_lang == norm or v_lang.startswith(f"{norm}-"):
                return True
        return False

    def shutdown(self) -> None:
        self.stop()
        with self._worker_lock:
            if self._worker_proc and self._worker_proc.poll() is None:
                try:
                    self._worker_proc.stdin.write("__QUIT__\n")
                    self._worker_proc.stdin.flush()
                    self._worker_proc.wait(timeout=2.0)
                except Exception:
                    try:
                        self._worker_proc.kill()
                    except Exception:
                        pass
            self._worker_proc = None


class FakeSpeechBackend(SpeechBackend):
    """
    Predictable mock speech backend for deterministic automated testing.
    Records history, interruption events, and allows simulated speech failures and configurable voices.
    """

    def __init__(self, should_fail: bool = False, supported_languages: Optional[List[str]] = None):
        self.should_fail = should_fail
        self.supported_languages = supported_languages or ["ne", "en"]
        self.spoken_history: List[str] = []
        self.interrupted_count: int = 0
        self.is_stopped = False
        self._lock = threading.Lock()

    def speak(self, text: str, interrupt: bool = False, language: Optional[str] = None) -> bool:
        with self._lock:
            if self.should_fail:
                return False
            if interrupt:
                self.interrupted_count += 1
            self.spoken_history.append(text)
            self.is_stopped = False
            return True

    def stop(self) -> None:
        with self._lock:
            self.is_stopped = True

    def get_available_voices(self) -> List[Dict[str, Any]]:
        voices = []
        if "en" in self.supported_languages:
            voices.append({"id": "fake-en", "name": "Fake English", "language": "en-US", "gender": "male"})
        if "ne" in self.supported_languages:
            voices.append({"id": "fake-ne", "name": "Fake Nepali", "language": "ne-NP", "gender": "female"})
        return voices

    def has_voice_for_language(self, lang: str) -> bool:
        norm = lang.strip().lower()
        return any(norm == l or norm.startswith(f"{l}-") or l.startswith(f"{norm}-") for l in self.supported_languages)


class SpeechManager:
    """
    Thread-safe speech orchestrator managing a bounded priority queue,
    cooldown deduplication, mute/pause states, language verification, and worker thread execution.
    """

    def __init__(
        self,
        backend: Optional[SpeechBackend] = None,
        max_queue_size: int = 10,
        default_cooldown: float = 3.0,
        language: str = "ne"
    ):
        if backend is not None:
            self.backend = backend
        elif sys.platform == "win32":
            disable_piper = os.environ.get("TRINETRA_DISABLE_PIPER", "").lower() in ("1", "true", "yes")
            if not disable_piper:
                try:
                    from app.audio.piper_backend import CompositeSpeechBackend, is_piper_available
                    if is_piper_available():
                        self.backend = CompositeSpeechBackend()
                    else:
                        self.backend = WindowsSapiSpeechBackend()
                except Exception as exc:
                    logger.warning(f"CompositeSpeechBackend init error: {exc}. Using WindowsSapiSpeechBackend.")
                    self.backend = WindowsSapiSpeechBackend()
            else:
                self.backend = WindowsSapiSpeechBackend()
        else:
            self.backend = FakeSpeechBackend()
        self.max_queue_size = max_queue_size
        self.default_cooldown = default_cooldown

        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_queue_size)
        self._cooldowns: Dict[str, float] = {}
        self._cooldown_lock = threading.Lock()
        self._state_lock = threading.Lock()

        try:
            from app.localization import normalize_language, is_supported_language
            norm = normalize_language(language) if is_supported_language(language) else language.strip().lower()
        except Exception:
            norm = language.strip().lower()

        self._muted: bool = False
        self._paused: bool = False
        self._running: bool = False
        self._speech_rate: float = 1.0
        self._default_language: str = norm
        self._audio_failure_count: int = 0
        self._last_audio_error: Optional[str] = None
        self._worker_thread: Optional[threading.Thread] = None

        self.start()

    def start(self) -> None:
        """Starts or restarts the speech worker if not running."""
        with self._state_lock:
            self._running = True
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
                self._worker_thread.start()

    @property
    def speech_rate(self) -> float:
        with self._state_lock:
            return self._speech_rate

    @speech_rate.setter
    def speech_rate(self, value: float) -> None:
        clamped = max(0.5, min(2.5, float(value)))
        with self._state_lock:
            self._speech_rate = clamped
            if hasattr(self.backend, "speech_rate"):
                self.backend.speech_rate = clamped

    @property
    def language(self) -> str:
        with self._state_lock:
            return self._default_language

    @language.setter
    def language(self, value: str) -> None:
        try:
            from app.localization import normalize_language
            norm = normalize_language(value)
        except Exception as exc:
            # Explicit ValueError for invalid language codes
            raise ValueError(f"Invalid language '{value}': {exc}") from exc

        with self._state_lock:
            self._default_language = norm

    def announce(
        self,
        text: str,
        priority: SpeechPriority = SpeechPriority.SPATIAL_NAVIGATION,
        message_key: Optional[str] = None,
        interrupt: bool = False,
        cooldown: Optional[float] = None,
        language: Optional[str] = None
    ) -> bool:
        """
        Enqueues an announcement subject to mute, cooldown, language support, and priority checks.
        Returns True if enqueued, False if suppressed or dropped.
        """
        with self._state_lock:
            if self._muted:
                return False
            if not self._running or self._worker_thread is None or not self._worker_thread.is_alive():
                self._running = True
                self._worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
                self._worker_thread.start()

        raw_lang = (language or self.language).strip().lower()
        try:
            from app.localization import normalize_language, is_supported_language
            active_language = normalize_language(raw_lang) if is_supported_language(raw_lang) else raw_lang
        except Exception:
            active_language = raw_lang

        # If Nepali is selected and no Nepali voice is installed, do NOT silently fall back to English!
        # Suppress speech output and log the missing voice.
        if active_language.startswith("ne") and not self.has_voice_for_language("ne"):
            logger.warning(
                "Nepali speech announcement suppressed: No verified Nepali TTS voice installed on system."
            )
            return False

        key = message_key or f"{active_language}:{text.strip().lower()}"
        active_cooldown = cooldown if cooldown is not None else self.default_cooldown

        now = time.time()
        with self._cooldown_lock:
            last_time = self._cooldowns.get(key, 0.0)
            if not interrupt and (now - last_time) < active_cooldown:
                # Suppressed by cooldown deduplication
                return False
            self._cooldowns[key] = now

        item = SpeechItem(
            priority=int(priority),
            timestamp=now,
            text=text,
            message_key=key,
            interrupt=interrupt,
            language=active_language
        )

        if interrupt:
            # Drain lower priority items and halt current audio
            self._drain_queue()
            self.backend.stop()

        try:
            self._queue.put_nowait(item)
            return True
        except queue.Full:
            # Drop item if queue full to prevent stale queue accumulation
            logger.warning(f"Speech queue full. Dropped message: '{text}'")
            return False

    def mute(self) -> None:
        """Mutes all speech output and halts ongoing audio."""
        with self._state_lock:
            self._muted = True
        self.stop()

    def unmute(self) -> None:
        """Resumes speech output."""
        with self._state_lock:
            self._muted = False

    def is_muted(self) -> bool:
        with self._state_lock:
            return self._muted

    def pause(self) -> None:
        """Pauses speech processing."""
        with self._state_lock:
            self._paused = True
        self.backend.stop()

    def resume(self) -> None:
        """Resumes speech processing."""
        with self._state_lock:
            self._paused = False

    def is_paused(self) -> bool:
        with self._state_lock:
            return self._paused

    def stop(self) -> None:
        """Halts current speech and empties pending queue."""
        self._drain_queue()
        self.backend.stop()

    def get_available_voices(self) -> List[Dict[str, Any]]:
        return self.backend.get_available_voices()

    def has_voice_for_language(self, lang: str) -> bool:
        return self.backend.has_voice_for_language(lang)

    def get_status(self) -> Dict[str, Any]:
        with self._state_lock:
            return {
                "muted": self._muted,
                "paused": self._paused,
                "language": self._default_language,
                "queue_size": self._queue.qsize(),
                "backend": self.backend.__class__.__name__,
                "available_voices": self.get_available_voices(),
                "nepali_voice_available": self.has_voice_for_language("ne"),
                "audio_failure_count": self._audio_failure_count,
                "last_audio_error": self._last_audio_error,
            }

    def shutdown(self) -> None:
        """Gracefully shuts down the speech worker."""
        self._running = False
        self.stop()
        self.backend.shutdown()

    def _drain_queue(self) -> None:
        """Discards all pending items in the priority queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def _speech_worker(self) -> None:
        """Background daemon thread pulling items from priority queue."""
        while self._running:
            try:
                item: SpeechItem = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            with self._state_lock:
                if self._muted or self._paused:
                    self._queue.task_done()
                    continue

            try:
                success = self.backend.speak(item.text, interrupt=item.interrupt, language=item.language)
                if not success:
                    with self._state_lock:
                        self._audio_failure_count += 1
                        self._last_audio_error = f"Backend speak failed for: {item.text[:50]}"
                    logger.warning(f"Audio playback failed for: '{item.text}'")
            except Exception as exc:
                with self._state_lock:
                    self._audio_failure_count += 1
                    self._last_audio_error = str(exc)
                logger.warning(f"Error speaking '{item.text}': {exc}")
            finally:
                self._queue.task_done()
