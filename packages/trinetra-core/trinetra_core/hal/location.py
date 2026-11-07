"""
Location Hardware Abstraction Layer (HAL) Interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class LocationAdapterInterface(ABC):
    """
    Abstract interface for offline-first geolocation.
    Supports GPS NMEA streams, Web Geolocation API, and local bookmarks.
    """

    @abstractmethod
    def get_coordinates(self) -> Optional[Tuple[float, float]]:
        """Return (latitude, longitude) if location is available and enabled."""
        pass

    @abstractmethod
    def get_accuracy_meters(self) -> Optional[float]:
        """Return estimated horizontal accuracy radius in meters."""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Return True if user has granted location permission."""
        pass

    @abstractmethod
    def save_bookmark(self, label: str, coords: Optional[Tuple[float, float]] = None) -> Dict[str, Any]:
        """Save a labeled geographic waypoint."""
        pass

    @abstractmethod
    def list_bookmarks(self) -> List[Dict[str, Any]]:
        """Return all saved geographic waypoints."""
        pass
