"""
TRINETRA v2 Device Health, Thermal & Battery Governor.
======================================================
Monitors client and host hardware health metrics:
- Battery status & charging state.
- Thermal temperature and thermal throttling triggers.
- Monotonic frame drop ratio and processing latency.
- Automated graceful degradation to LITE mode with non-intrusive voice announcement.
"""

from __future__ import annotations
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from trinetra_core.capabilities import DeviceTier
from trinetra_core.events import EventBus, Event, EventType, EventCategory, EventPriority
from trinetra_core.lite_mode import LiteModeController

logger = logging.getLogger("trinetra.device_health")


class DeviceHealthSupervisor:
    """
    Supervises system health and enforces automatic performance tier degradation.
    """

    def __init__(
        self,
        lite_controller: Optional[LiteModeController] = None,
        event_bus: Optional[EventBus] = None,
        speech_callback: Optional[Callable[[str], None]] = None,
        battery_critical_threshold: float = 15.0,
        battery_recovery_threshold: float = 25.0,
        thermal_throttle_threshold: float = 75.0,
        thermal_recovery_threshold: float = 65.0,
    ):
        self.lite_controller = lite_controller
        self.event_bus = event_bus
        self.speech_callback = speech_callback
        self.battery_critical_threshold = battery_critical_threshold
        self.battery_recovery_threshold = battery_recovery_threshold
        self.thermal_throttle_threshold = thermal_throttle_threshold
        self.thermal_recovery_threshold = thermal_recovery_threshold

        self._lock = threading.RLock()
        self._battery_pct: Optional[float] = 100.0
        self._is_charging: bool = True
        self._temp_c: Optional[float] = 42.0
        self._frame_drop_ratio: float = 0.0

        self._is_battery_critical = False
        self._is_thermal_throttling = False
        self._previous_tier: DeviceTier = DeviceTier.STANDARD
        self._last_alert_time: float = 0.0
        self._alert_cooldown_s: float = 60.0

    def update_telemetry(
        self,
        battery_pct: Optional[float] = None,
        is_charging: Optional[bool] = None,
        temp_c: Optional[float] = None,
        frame_drop_ratio: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Updates device telemetry readings and evaluates tier governance rules.
        """
        with self._lock:
            if battery_pct is not None:
                self._battery_pct = max(0.0, min(100.0, float(battery_pct)))
            if is_charging is not None:
                self._is_charging = bool(is_charging)
            if temp_c is not None:
                self._temp_c = float(temp_c)
            if frame_drop_ratio is not None:
                self._frame_drop_ratio = max(0.0, min(1.0, float(frame_drop_ratio)))

            self._evaluate_health_rules()
            return self.get_health_report()

    def _evaluate_health_rules(self) -> None:
        now = time.time()
        should_degrade = False
        reason = ""

        # 1. Battery Rule (< 15% and not charging)
        if (
            self._battery_pct is not None
            and self._battery_pct <= self.battery_critical_threshold
            and not self._is_charging
        ):
            should_degrade = True
            self._is_battery_critical = True
            reason = f"Battery critical ({self._battery_pct:.1f}% discharging)"
        elif (
            self._battery_pct is not None
            and (self._battery_pct >= self.battery_recovery_threshold or self._is_charging)
        ):
            self._is_battery_critical = False

        # 2. Thermal Rule (> 75 C or sustained > 40% frame drops)
        if (self._temp_c is not None and self._temp_c >= self.thermal_throttle_threshold) or (
            self._frame_drop_ratio >= 0.40
        ):
            should_degrade = True
            self._is_thermal_throttling = True
            reason = reason or f"Thermal throttling ({self._temp_c:.1f}°C, drops: {self._frame_drop_ratio*100:.0f}%)"
        elif self._temp_c is not None and self._temp_c <= self.thermal_recovery_threshold:
            self._is_thermal_throttling = False

        # 3. Apply Degradation / Recovery
        if should_degrade:
            if self.lite_controller and self.lite_controller.active_tier != DeviceTier.LITE:
                self._previous_tier = self.lite_controller.active_tier
                self.lite_controller.set_tier(DeviceTier.LITE)
                logger.warning(f"Device health degraded to LITE mode: {reason}")

                if self.event_bus:
                    self.event_bus.publish(
                        Event(
                            event_type=EventType.LITE_MODE_TRIGGERED,
                            category=EventCategory.SYSTEM_LIFECYCLE,
                            priority=EventPriority.HIGH,
                            payload={
                                "action": "downgrade",
                                "tier": "lite",
                                "reason": reason,
                                "battery": self._battery_pct,
                                "temp_c": self._temp_c,
                            },
                        )
                    )

                if self.speech_callback and (now - self._last_alert_time) > self._alert_cooldown_s:
                    self._last_alert_time = now
                    self.speech_callback("ब्याट्री वा तापक्रमको कारण त्रिनेत्र लाइट मोडमा चलिरहेको छ।")

        elif not self._is_battery_critical and not self._is_thermal_throttling:
            # Recover back if was degraded
            if self.lite_controller and self.lite_controller.active_tier == DeviceTier.LITE:
                target = self._previous_tier or DeviceTier.STANDARD
                if target != DeviceTier.LITE:
                    self.lite_controller.set_tier(target)
                    logger.info(f"Device health normalized; restored to {target.value} mode")

                    if self.event_bus:
                        self.event_bus.publish(
                            Event(
                                event_type=EventType.TIER_CHANGED,
                                category=EventCategory.SYSTEM_LIFECYCLE,
                                priority=EventPriority.NORMAL,
                                payload={"action": "restore", "tier": target.value},
                            )
                        )

    def get_health_report(self) -> Dict[str, Any]:
        with self._lock:
            active_tier_name = (
                self.lite_controller.active_tier.value if self.lite_controller else "standard"
            )
            recommendations = []
            if self._is_battery_critical:
                recommendations.append("कृपया डिभाइसलाई चार्जरमा जोड्नुहोस्।")
            if self._is_thermal_throttling:
                recommendations.append("डिभाइस तातेको छ; केही समय आराम दिनुहोस्।")
            if not recommendations:
                recommendations.append("प्रणाली सामान्य अवस्थामा छ।")

            return {
                "battery_percentage": self._battery_pct,
                "is_charging": self._is_charging,
                "temperature_celsius": self._temp_c,
                "frame_drop_ratio": round(self._frame_drop_ratio, 3),
                "is_battery_critical": self._is_battery_critical,
                "is_thermal_throttling": self._is_thermal_throttling,
                "active_tier": active_tier_name,
                "recommendation_ne": " ".join(recommendations),
                "timestamp": time.time(),
            }
