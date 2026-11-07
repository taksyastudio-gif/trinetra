"""
Communications Hardware Abstraction Layer (HAL) Interface.
Focuses on SMS-first offline emergency caregiver transmission.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class CommsAdapterInterface(ABC):
    """
    Abstract interface for zero-internet communication channels.
    Supports:
    - Serial GSM modem (SIM800L / A7670C via AT commands)
    - Android native SMS intent / telephony manager
    - MockCommsAdapter (Testing & development logging)
    """

    @abstractmethod
    def send_sms(self, recipient_phone: str, text_message: str) -> bool:
        """
        Transmit an SMS text message over cellular network.
        Returns True if handed off successfully to baseband/OS queue.
        """
        pass

    @abstractmethod
    def is_cellular_available(self) -> bool:
        """Return True if cellular modem or mobile telephony service is registered."""
        pass

    @abstractmethod
    def get_signal_quality(self) -> Dict[str, Any]:
        """Return signal strength (CSQ / bars), SIM state, and operator name."""
        pass
