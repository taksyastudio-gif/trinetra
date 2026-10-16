"""
TRINETRA Thread-Safe Text-To-Speech (TTS) Queue System
Manages audio synthesis using pyttsx3 in a dedicated background worker thread,
preventing audio overlapping, thread contention, and alert fatigue via cooldown rate-limiting.
"""

import collections
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

from config import TTSConfig

logger = logging.getLogger("TRINETRA.TTS")


@dataclass(order=True)
class AudioAlert:
    """Prioritized audio alert container for thread-safe priority queue."""
    priority: int                   # 1 (Critical Emergency) to 5 (Informational)
    timestamp: float                # Insertion timestamp for tie-breaking
    message: str                    # Text to synthesize
    alert_key: str                  # Deduplication & cooldown identifier
    source: str = "engine"          # Originating module (e.g., 'vision', 'sensor', 'rule')


class CooldownManager:
    """
    Tracks alert occurrences and manages rate-limiting cooldown timers
    to prevent repeated audio spamming while allowing urgent threats to escalate.
    """

    def __init__(self, config: TTSConfig):
        self.config = config
        self._lock = threading.Lock()
        # Maps alert_key -> (last_spoken_timestamp, last_priority)
        self._history: Dict[str, Tuple[float, int]] = {}

    def should_suppress(self, alert_key: str, priority: int) -> bool:
        """
        Determines whether an alert should be suppressed due to active cooldown.

        Urgency Escalation Rule:
        If a new alert has significantly higher urgency (e.g., priority 1 vs previous 3),
        the cooldown is bypassed to ensure user safety.
        """
        with self._lock:
            now = time.monotonic()
            if alert_key not in self._history:
                return False

            last_time, last_priority = self._history[alert_key]

            # Urgency escalation: if the threat became critical, bypass old cooldown
            if priority < last_priority and (now - last_time) >= 1.0:
                return False

            # Select cooldown window based on urgency
            if priority == 1:
                window = self.config.critical_cooldown_sec
            elif priority == 2:
                window = self.config.approaching_cooldown_sec
            elif priority >= 4:
                window = self.config.distant_cooldown_sec
            else:
                window = self.config.default_cooldown_sec

            return (now - last_time) < window

    def record_spoken(self, alert_key: str, priority: int) -> None:
        """Records that an alert was announced at the current time."""
        with self._lock:
            self._history[alert_key] = (time.monotonic(), priority)

    def clear(self) -> None:
        """Resets all cooldown tracking history."""
        with self._lock:
            self._history.clear()


class TTSQueueManager:
    """
    Thread-safe TTS engine manager. Runs a background worker thread that
    processes prioritized speech requests sequentially with no overlapping audio.
    """

    def __init__(self, config: Optional[TTSConfig] = None):
        self.config = config or TTSConfig()
        self.cooldown = CooldownManager(self.config)
        self._queue: queue.PriorityQueue[AudioAlert] = queue.PriorityQueue(
            maxsize=self.config.max_queue_size
        )

        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._is_speaking = False
        self._lock = threading.Lock()

        # Telemetry / Debug log of spoken messages (last 20)
        self.speech_history: Deque[Tuple[float, str, int]] = collections.deque(maxlen=20)
        self.current_utterance: Optional[str] = None
        self._engine_available = False

    def start(self) -> None:
        """Starts the dedicated background TTS worker thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="TRINETRA-TTSWorker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("TRINETRA TTS worker thread started.")

    def stop(self) -> None:
        """Gracefully terminates the background TTS worker."""
        self._stop_event.set()
        # Push a high-priority sentinel to unblock queue get()
        try:
            self._queue.put_nowait(AudioAlert(priority=0, timestamp=0.0, message="__STOP__", alert_key="__STOP__"))
        except queue.Full:
            pass

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        logger.info("TRINETRA TTS worker thread stopped.")

    def speak(
        self,
        message: str,
        priority: int = 3,
        alert_key: Optional[str] = None,
        source: str = "engine",
        force: bool = False
    ) -> bool:
        """
        Enqueues an audio announcement if not muted or suppressed by cooldown.

        Args:
            message: Text to speak.
            priority: 1 (Urgent) to 5 (Informational).
            alert_key: Deduplication key. If None, derived from message.
            source: Name of component generating the alert.
            force: If True, bypasses cooldown rate-limiting.

        Returns:
            True if queued successfully, False if suppressed or queue full.
        """
        if self.config.mute_audio or not message.strip():
            return False

        key = alert_key or message.strip().lower()

        if not force and self.cooldown.should_suppress(key, priority):
            logger.debug(f"Suppressed alert due to active cooldown: '{message}' (Key: {key})")
            return False

        alert = AudioAlert(
            priority=priority,
            timestamp=time.monotonic(),
            message=message.strip(),
            alert_key=key,
            source=source
        )

        try:
            self._queue.put_nowait(alert)
            return True
        except queue.Full:
            # If queue is full and new alert is urgent (priority 1 or 2), drop lowest priority item
            if priority <= 2:
                try:
                    # Drop one item to make space
                    _ = self._queue.get_nowait()
                    self._queue.put_nowait(alert)
                    return True
                except (queue.Empty, queue.Full):
                    pass
            logger.warning(f"TTS Queue overflow. Dropped alert: '{message}'")
            return False

    def _init_pyttsx3(self):
        """Initializes pyttsx3 within the worker thread to satisfy COM threading model."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", self.config.rate)
            engine.setProperty("volume", self.config.volume)

            # Optional: Select voice if available
            voices = engine.getProperty("voices")
            if voices and 0 <= self.config.voice_index < len(voices):
                engine.setProperty("voice", voices[self.config.voice_index].id)

            self._engine_available = True
            return engine
        except Exception as exc:
            logger.warning(f"pyttsx3 initialization failed ({exc}). Operating in mock audio mode.")
            self._engine_available = False
            return None

    def _worker_loop(self) -> None:
        """Dedicated sequential consumer loop for pyttsx3 audio synthesis."""
        engine = self._init_pyttsx3()

        while not self._stop_event.is_set():
            try:
                alert = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if alert.message == "__STOP__" or self._stop_event.is_set():
                break

            # Check if alert got suppressed while waiting in queue
            if self.cooldown.should_suppress(alert.alert_key, alert.priority):
                self._queue.task_done()
                continue

            with self._lock:
                self._is_speaking = True
                self.current_utterance = alert.message
                self.speech_history.append((time.time(), alert.message, alert.priority))

            # Mark cooldown timestamp right when utterance begins
            self.cooldown.record_spoken(alert.alert_key, alert.priority)

            # Synthesize speech
            try:
                if engine and self._engine_available:
                    engine.say(alert.message)
                    engine.runAndWait()
                else:
                    # Mock speech output: simulate duration based on word count
                    word_count = len(alert.message.split())
                    simulated_duration = min(2.0, max(0.4, word_count * 0.15))
                    time.sleep(simulated_duration)
                    logger.info(f"[AUDIO OUT (P{alert.priority})]: {alert.message}")
            except Exception as exc:
                logger.error(f"Error during audio synthesis: {exc}")
                # Re-attempt reinitializing engine if it crashed
                engine = self._init_pyttsx3()
            finally:
                with self._lock:
                    self._is_speaking = False
                    self.current_utterance = None
                self._queue.task_done()

        # Cleanup engine on exit
        if engine and self._engine_available:
            try:
                engine.stop()
            except Exception:
                pass

    @property
    def is_speaking(self) -> bool:
        """Returns True if audio is actively playing."""
        with self._lock:
            return self._is_speaking

    def get_recent_speech(self) -> list:
        """Returns snapshot of recent spoken announcements."""
        with self._lock:
            return list(self.speech_history)
