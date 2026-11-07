"""
Autonomy Policy Supervisor and Emergency Protocol Engine for TRINETRA v2.
Enforces L0 to L4 governance, 10-second audible pre-alert countdown,
and tamper-evident audit logging.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from trinetra_core.types import AutonomyLevel
from trinetra_core.caretaker.memory import ContextMemory
from trinetra_core.caretaker.caregiver import CaregiverLink, CaregiverAlertResult
from trinetra_core.events.bus import EventBus
from trinetra_core.events.schema import Event, EventCategory, EventPriority, EventType


@dataclass
class EmergencyCountdownState:
    is_active: bool = False
    started_at_utc: float = 0.0
    duration_seconds: float = 10.0
    incident_type: str = ""
    reason: str = ""
    coordinates: Optional[Tuple[float, float]] = None
    battery_pct: Optional[float] = None
    is_cancelled: bool = False
    is_dispatched: bool = False
    dispatch_result: Optional[CaregiverAlertResult] = None

    @property
    def remaining_seconds(self) -> float:
        if not self.is_active or self.is_cancelled or self.is_dispatched:
            return 0.0
        elapsed = time.time() - self.started_at_utc
        return max(0.0, self.duration_seconds - elapsed)


class AutonomySupervisor:
    """
    Central governance engine regulating autonomous actions and emergency escalations.
    """

    def __init__(
        self,
        memory: ContextMemory,
        caregiver_link: CaregiverLink,
        event_bus: Optional[EventBus] = None,
        speech_callback: Optional[Callable[[str, bool], None]] = None,
    ):
        self.memory = memory
        self.caregiver_link = caregiver_link
        self.event_bus = event_bus
        self.speech_callback = speech_callback
        
        self._lock = threading.RLock()
        self._emergency_state = EmergencyCountdownState()

    def get_autonomy_level(self) -> AutonomyLevel:
        return self.memory.get_autonomy_level()

    def set_autonomy_level(self, level: AutonomyLevel) -> None:
        self.memory.set_autonomy_level(level)
        self.memory.log_action(
            autonomy_level=level,
            event_type="autonomy.level_changed",
            reason="User or system configured autonomy level",
            inputs={"new_level": int(level), "new_level_name": level.name},
            outcome="Updated successfully",
        )

    def can_execute_routine_automatically(self) -> bool:
        """Returns True if current autonomy level allows pre-approved routine execution (L3+)."""
        return self.get_autonomy_level() >= AutonomyLevel.L3_ROUTINE_AUTO

    # --- L4 Emergency Countdown Protocol ---

    def trigger_emergency_countdown(
        self,
        incident_type: str = "fall_detected",
        reason: str = "Sudden high-impact fall suspected",
        coordinates: Optional[Tuple[float, float]] = None,
        battery_pct: Optional[float] = None,
        duration_seconds: float = 10.0,
    ) -> EmergencyCountdownState:
        """
        Initiates 10-second audible pre-alert countdown before dispatching caregiver SMS.
        """
        with self._lock:
            now = time.time()
            self._emergency_state = EmergencyCountdownState(
                is_active=True,
                started_at_utc=now,
                duration_seconds=duration_seconds,
                incident_type=incident_type,
                reason=reason,
                coordinates=coordinates,
                battery_pct=battery_pct,
                is_cancelled=False,
                is_dispatched=False,
            )

            # Audit record
            self.memory.log_action(
                autonomy_level=AutonomyLevel.L4_EMERGENCY,
                event_type="emergency.prealert_started",
                reason=reason,
                inputs={"incident_type": incident_type, "duration": duration_seconds, "coords": coordinates},
                outcome="10-second countdown active",
            )

            # Publish event
            if self.event_bus:
                self.event_bus.publish(Event(
                    event_type=EventType.EMERGENCY_PREALERT,
                    category=EventCategory.CARETAKER,
                    priority=EventPriority.CRITICAL_HAZARD,
                    payload={
                        "incident_type": incident_type,
                        "duration_seconds": duration_seconds,
                        "remaining_seconds": duration_seconds,
                        "reason": reason,
                    }
                ))

            # Audible warning
            prompt_ne = "चेतावनी: आपतकालीन सूचना १० सेकेन्डमा पठाइनेछ। रद्द गर्न स्क्रिन छुनुहोस् वा 'म ठीक छु' भन्नुहोस्।"
            if self.speech_callback:
                try:
                    self.speech_callback(prompt_ne, True)
                except Exception:
                    pass

            return self._emergency_state

    def cancel_emergency(self, cancel_reason: str = "user_ok") -> bool:
        """
        Cancels active countdown before SMS is dispatched.
        """
        with self._lock:
            if not self._emergency_state.is_active or self._emergency_state.is_dispatched:
                return False

            self._emergency_state.is_active = False
            self._emergency_state.is_cancelled = True

            # Audit record
            self.memory.log_action(
                autonomy_level=AutonomyLevel.L4_EMERGENCY,
                event_type="emergency.cancelled",
                reason=cancel_reason,
                inputs={"incident_type": self._emergency_state.incident_type},
                outcome="Cancelled by user confirmation",
            )

            if self.event_bus:
                self.event_bus.publish(Event(
                    event_type=EventType.EMERGENCY_CANCELLED,
                    category=EventCategory.CARETAKER,
                    priority=EventPriority.HIGH,
                    payload={"cancel_reason": cancel_reason}
                ))

            if self.speech_callback:
                try:
                    self.speech_callback("आपतकालीन सूचना रद्द गरियो। तपाईं सुरक्षित हुनुहुन्छ।", False)
                except Exception:
                    pass

            return True

    def tick_emergency_countdown(self) -> Tuple[bool, EmergencyCountdownState]:
        """
        Evaluates remaining time on active countdown.
        If timer expires (0s), automatically fires caregiver SMS dispatch.
        Returns: (dispatched_now, current_state)
        """
        with self._lock:
            state = self._emergency_state
            if not state.is_active or state.is_cancelled or state.is_dispatched:
                return False, state

            if state.remaining_seconds <= 0.0:
                # Timer expired! Dispatch emergency SMS!
                state.is_active = False
                state.is_dispatched = True

                result = self.caregiver_link.dispatch_emergency(
                    alert_title="आकस्मिक सूचना (लड्नुभएको शंका)",
                    coordinates=state.coordinates,
                    battery_pct=state.battery_pct,
                )
                state.dispatch_result = result

                # Audit record
                self.memory.log_action(
                    autonomy_level=AutonomyLevel.L4_EMERGENCY,
                    event_type="emergency.dispatched",
                    reason=state.reason,
                    inputs={
                        "incident_type": state.incident_type,
                        "recipient": result.recipient_phone,
                        "sms_text": result.message_text,
                    },
                    outcome="SMS dispatched to caregiver" if result.success else f"Dispatch failed: {result.error}",
                )

                if self.event_bus:
                    self.event_bus.publish(Event(
                        event_type=EventType.EMERGENCY_DISPATCH,
                        category=EventCategory.CARETAKER,
                        priority=EventPriority.CRITICAL_HAZARD,
                        payload={
                            "success": result.success,
                            "recipient": result.recipient_phone,
                            "message": result.message_text,
                        }
                    ))

                if self.speech_callback:
                    try:
                        self.speech_callback("आपतकालीन सन्देश तपाईंको परिवारलाई पठाइयो।", True)
                    except Exception:
                        pass

                return True, state

            return False, state

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            state = self._emergency_state
            return {
                "autonomy_level": int(self.get_autonomy_level()),
                "autonomy_name": self.get_autonomy_level().name,
                "emergency_active": state.is_active,
                "remaining_seconds": round(state.remaining_seconds, 1),
                "is_cancelled": state.is_cancelled,
                "is_dispatched": state.is_dispatched,
                "incident_type": state.incident_type,
            }
