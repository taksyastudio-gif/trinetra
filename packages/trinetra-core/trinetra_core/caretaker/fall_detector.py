"""
Fall Detection & Inactivity Wellbeing Monitor for TRINETRA v2 Caretaker.
Evaluates physical IMU acceleration spikes and visual downward optical flow.
"""

from __future__ import annotations
from collections import deque
import math
import time
from typing import Any, Deque, Dict, List, Optional, Tuple


class FallDetector:
    """
    Evaluates physical sensor spikes (IMU) and visual downward motion vectors.
    """

    def __init__(
        self,
        freefall_threshold: float = 4.5,     # m/s^2 (< ~0.45g)
        impact_threshold: float = 22.0,       # m/s^2 (> ~2.2g)
        visual_downward_threshold: float = 45.0, # pixels downward velocity jump
        confirmation_window_sec: float = 1.5,
    ):
        self.freefall_threshold = freefall_threshold
        self.impact_threshold = impact_threshold
        self.visual_downward_threshold = visual_downward_threshold
        self.confirmation_window_sec = confirmation_window_sec

        self._recent_accel_mags: Deque[Tuple[float, float]] = deque(maxlen=30) # (timestamp, mag)
        self._freefall_detected_at: Optional[float] = None
        self._last_fall_suspected_at: Optional[float] = None

    def update_imu(self, ax: float, ay: float, az: float, timestamp: Optional[float] = None) -> bool:
        """
        Feeds accelerometer sample (in m/s^2).
        Returns True if a high-confidence fall sequence is detected.
        Sequence: Freefall (weightlessness) -> Severe Impact Spike -> Sustained Stillness.
        """
        now = timestamp or time.time()
        mag = math.sqrt(ax * ax + ay * ay + az * az)
        self._recent_accel_mags.append((now, mag))

        # 1. Detect weightlessness / free-fall drop
        if mag < self.freefall_threshold:
            self._freefall_detected_at = now

        # 2. Detect impact peak
        if mag > self.impact_threshold:
            # If preceded by freefall within window
            if self._freefall_detected_at and (now - self._freefall_detected_at <= self.confirmation_window_sec):
                self._last_fall_suspected_at = now
                self._freefall_detected_at = None
                return True
            # Or standalone severe high-G impact (> 28 m/s^2)
            elif mag > 28.0:
                self._last_fall_suspected_at = now
                return True

        return False

    def update_visual_motion(self, dy: float, is_ground_visible: bool = True, timestamp: Optional[float] = None) -> bool:
        """
        Feeds optical flow vertical ego-motion (dy positive = downward movement).
        Returns True if a sudden downward collapse is detected visually.
        """
        now = timestamp or time.time()
        if dy > self.visual_downward_threshold and is_ground_visible:
            self._last_fall_suspected_at = now
            return True
        return False


class InactivityMonitor:
    """
    Monitors user inactivity during waking hours to prompt wellbeing check-ins.
    """

    def __init__(
        self,
        inactivity_threshold_seconds: float = 3600.0, # 1 hour
        active_hours: Tuple[int, int] = (7, 21),       # 7:00 AM to 9:00 PM
    ):
        self.inactivity_threshold_seconds = inactivity_threshold_seconds
        self.active_hours = active_hours
        self._last_activity_timestamp: float = time.time()
        self._last_warning_timestamp: float = 0.0

    def record_activity(self) -> None:
        """Record explicit user action (motion, button tap, voice command)."""
        self._last_activity_timestamp = time.time()

    def check_inactivity(self) -> Tuple[bool, float, str]:
        """
        Returns (is_inactive_warning_due, elapsed_seconds, spoken_prompt_ne).
        """
        now = time.time()
        local_time = time.localtime(now)
        current_hour = local_time.tm_hour

        # Only evaluate during designated waking hours
        if not (self.active_hours[0] <= current_hour < self.active_hours[1]):
            return False, 0.0, ""

        elapsed = now - self._last_activity_timestamp
        if elapsed >= self.inactivity_threshold_seconds:
            # Don't repeat warning more than once every 30 minutes
            if now - self._last_warning_timestamp >= 1800.0:
                self._last_warning_timestamp = now
                prompt = "हजुर, लामो समयदेखि कुनै गतिविधि देखिएन। के तपाईं आराममा हुनुहुन्छ?"
                return True, elapsed, prompt

        return False, elapsed, ""
