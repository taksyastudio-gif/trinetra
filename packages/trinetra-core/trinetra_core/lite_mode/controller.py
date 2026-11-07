"""
Lite Mode and Performance Budget Controller for TRINETRA v2.
Monitors execution latency, thermal throttling, and battery constraints.
"""

from __future__ import annotations
from collections import deque
import time
from typing import Any, Dict, Optional
from trinetra_core.capabilities.device import DeviceCapabilities, DeviceTier
from trinetra_core.capabilities.negotiator import CapabilityNegotiator, NegotiatedProfile
from trinetra_core.events.bus import EventBus
from trinetra_core.events.schema import Event, EventCategory, EventPriority, EventType


class LiteModeController:
    """
    Enforces device execution budgets and throttles perception passes.
    """

    def __init__(
        self,
        capabilities: Optional[DeviceCapabilities] = None,
        event_bus: Optional[EventBus] = None,
        latency_window: int = 30,
        max_latency_budget_ms: float = 120.0,
    ):
        self._capabilities = capabilities or DeviceCapabilities()
        self._event_bus = event_bus
        self._latency_window = latency_window
        self._max_latency_budget_ms = max_latency_budget_ms
        
        self._latencies: deque[float] = deque(maxlen=latency_window)
        self._forced_tier: Optional[DeviceTier] = None
        self._profile: NegotiatedProfile = CapabilityNegotiator.negotiate(self._capabilities)
        self._last_processed_frame_index: int = -1

    @property
    def profile(self) -> NegotiatedProfile:
        return self._profile

    @property
    def active_tier(self) -> DeviceTier:
        return self._profile.active_tier

    @property
    def is_lite_mode(self) -> bool:
        return self._profile.active_tier == DeviceTier.LITE

    def update_telemetry(
        self,
        battery_pct: Optional[float] = None,
        thermal_throttling: Optional[bool] = None,
    ) -> bool:
        """
        Update hardware sensory state. Returns True if operational profile changed.
        """
        changed = False
        if battery_pct is not None and battery_pct != self._capabilities.battery_level_pct:
            self._capabilities.battery_level_pct = battery_pct
            changed = True
            
        if thermal_throttling is not None and thermal_throttling != self._capabilities.thermal_throttling_active:
            self._capabilities.thermal_throttling_active = thermal_throttling
            changed = True

        if changed:
            return self._recalculate_profile()
        return False

    def force_tier(self, tier: Optional[DeviceTier]) -> None:
        """Manually override tier or pass None to return to automatic negotiation."""
        self._forced_tier = tier
        self._recalculate_profile(reason="manual_force_tier")

    def record_inference_latency(self, latency_ms: float) -> None:
        """Record pipeline execution time and auto-throttle if budget exceeded."""
        self._latencies.append(latency_ms)
        
        # Check moving average
        if len(self._latencies) >= 10:
            avg_latency = sum(self._latencies) / len(self._latencies)
            if avg_latency > self._max_latency_budget_ms and self._profile.active_tier == DeviceTier.FULL:
                # Downgrade to STANDARD
                self._capabilities.declared_tier = DeviceTier.STANDARD
                self._recalculate_profile(reason="latency_budget_exceeded")

    def should_process_frame(self, frame_index: int) -> bool:
        """Determines whether current visual frame should run through inference."""
        skip = self._profile.frame_skip_ratio
        if skip <= 1:
            return True
        return (frame_index % skip) == 0

    def should_run_continuous_ocr(self) -> bool:
        """OCR is expensive (~300ms); allowed continuously only on FULL tier."""
        return self._profile.enable_continuous_ocr

    def _recalculate_profile(self, reason: str = "") -> bool:
        old_tier = self._profile.active_tier
        self._profile = CapabilityNegotiator.negotiate(self._capabilities, force_tier=self._forced_tier)

        if self._profile.active_tier != old_tier:
            if self._event_bus:
                evt_type = EventType.LITE_MODE_TRIGGERED if self._profile.active_tier == DeviceTier.LITE else EventType.TIER_CHANGED
                self._event_bus.publish(Event(
                    event_type=evt_type,
                    category=EventCategory.SYSTEM_LIFECYCLE,
                    priority=EventPriority.HIGH,
                    payload={
                        "old_tier": old_tier.value,
                        "new_tier": self._profile.active_tier.value,
                        "target_fps": self._profile.target_vision_fps,
                        "reason": reason,
                    }
                ))
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        avg_latency = (sum(self._latencies) / len(self._latencies)) if self._latencies else 0.0
        return {
            "active_tier": self._profile.active_tier.value,
            "target_vision_fps": self._profile.target_vision_fps,
            "is_lite_mode": self.is_lite_mode,
            "average_latency_ms": round(avg_latency, 2),
            "frame_skip_ratio": self._profile.frame_skip_ratio,
            "degraded_features": self._profile.degraded_features,
            "capabilities": self._capabilities.to_dict(),
        }
