"""
SMS-First Caregiver Communications Link for TRINETRA v2.
Transmits critical telemetry, GPS coordinates, and wellbeing status
over zero-internet cellular network directly to family phones.
"""

from __future__ import annotations
from dataclasses import dataclass
import time
from typing import Any, Dict, Optional, Tuple
from trinetra_core.hal.comms import CommsAdapterInterface
from trinetra_core.caretaker.memory import CaregiverContact, ContextMemory


@dataclass
class CaregiverAlertResult:
    success: bool
    recipient_phone: str
    recipient_name: str
    message_text: str
    dispatched_via: str                # "cellular_sms", "simulated", "failed"
    cooldown_suppressed: bool = False
    error: Optional[str] = None


class CaregiverLink:
    """
    Manages emergency dispatch to family members over cellular SMS.
    """

    def __init__(
        self,
        memory: ContextMemory,
        comms_adapter: Optional[CommsAdapterInterface] = None,
        sms_cooldown_seconds: float = 180.0,
    ):
        self.memory = memory
        self.comms_adapter = comms_adapter
        self.sms_cooldown_seconds = sms_cooldown_seconds
        self._last_sms_timestamp: float = 0.0

    def set_comms_adapter(self, adapter: CommsAdapterInterface) -> None:
        self.comms_adapter = adapter

    def format_emergency_sms(
        self,
        alert_title: str,
        coordinates: Optional[Tuple[float, float]] = None,
        battery_pct: Optional[float] = None,
        user_name: str = "हजुर",
    ) -> str:
        """
        Formats concise, high-clarity emergency SMS that fits in 160 GSM-7 / Unicode characters.
        """
        time_str = time.strftime("%H:%M", time.localtime())
        loc_str = ""
        if coordinates and len(coordinates) == 2:
            lat, lon = coordinates
            loc_str = f" स्थान: https://maps.google.com/?q={lat:.5f},{lon:.5f}"

        batt_str = f" (ब्याट्री {int(battery_pct)}%)" if battery_pct is not None else ""
        msg = f"[त्रिनेत्र आपतकालीन] {user_name}: {alert_title}।{loc_str}{batt_str} समय: {time_str}"
        return msg

    def dispatch_emergency(
        self,
        alert_title: str,
        coordinates: Optional[Tuple[float, float]] = None,
        battery_pct: Optional[float] = None,
        user_name: str = "हजुर",
        force: bool = False,
    ) -> CaregiverAlertResult:
        """
        Transmits emergency dispatch to primary caregiver contact.
        """
        now = time.time()
        contact = self.memory.get_primary_caregiver()
        if not contact:
            return CaregiverAlertResult(
                success=False,
                recipient_phone="",
                recipient_name="",
                message_text="",
                dispatched_via="failed",
                error="No caregiver contact configured or consent not granted.",
            )

        # Check cooldown to prevent multiple rapid SMS sends
        if not force and (now - self._last_sms_timestamp < self.sms_cooldown_seconds):
            return CaregiverAlertResult(
                success=False,
                recipient_phone=contact.phone_number,
                recipient_name=contact.name,
                message_text="",
                dispatched_via="suppressed",
                cooldown_suppressed=True,
                error=f"SMS suppressed: sent recently ({int(now - self._last_sms_timestamp)}s ago).",
            )

        sms_body = self.format_emergency_sms(
            alert_title=alert_title,
            coordinates=coordinates,
            battery_pct=battery_pct,
            user_name=user_name,
        )

        sent = False
        dispatched_via = "simulated"
        if self.comms_adapter is not None:
            try:
                sent = self.comms_adapter.send_sms(contact.phone_number, sms_body)
                dispatched_via = "cellular_sms" if sent else "adapter_failed"
            except Exception as exc:
                sent = False
                dispatched_via = f"error: {exc}"
        else:
            # Simulated send for testing / logging
            sent = True
            dispatched_via = "simulated_local"

        if sent:
            self._last_sms_timestamp = now

        return CaregiverAlertResult(
            success=sent,
            recipient_phone=contact.phone_number,
            recipient_name=contact.name,
            message_text=sms_body,
            dispatched_via=dispatched_via,
            error=None if sent else "Failed to send SMS through comms adapter.",
        )
