"""
Sensors Hardware Abstraction Layer (HAL) Interface.
Provides hardware metrics: battery %, thermal status, and IMU acceleration.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple


class SensorsAdapterInterface(ABC):
    """
    Abstract interface for physical telemetry and motion sensing.
    """

    @abstractmethod
    def get_battery_percentage(self) -> Optional[float]:
        """Return battery level (0.0 to 100.0) or None if wall-powered."""
        pass

    @abstractmethod
    def is_charging(self) -> Optional[bool]:
        """Return True if device is plugged in / charging."""
        pass

    @abstractmethod
    def get_temperature_celsius(self) -> Optional[float]:
        """Return device thermal sensor reading."""
        pass

    @abstractmethod
    def get_acceleration(self) -> Optional[Tuple[float, float, float]]:
        """Return (ax, ay, az) in m/s^2 from IMU accelerometer if present."""
        pass

    @abstractmethod
    def is_thermal_throttling(self) -> bool:
        """Return True if hardware temperature exceeds critical threshold."""
        pass
