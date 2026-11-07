"""
TRINETRA Plugin and Extension Architecture
Defines base interfaces and data structures for external hardware sensors
and pluggable navigation/obstacle-avoidance rules.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.spatial import Zone


@dataclass
class SensorReading:
    """Standardized telemetry reading from a hardware or virtual sensor."""
    sensor_id: str
    sensor_type: str                   # 'ultrasonic', 'lidar', 'imu', etc.
    timestamp: float
    distance_cm: Optional[float] = None
    target_zone: Optional[Zone] = None # Spatial zone associated with sensor mount
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NavigationAlert:
    """Standardized navigation alert emitted by navigation rules or fusion logic."""
    message: str
    priority: int                      # 1 (Urgent Emergency) to 5 (Informational)
    source: str                        # Rule or sensor name emitting alert
    cooldown_key: str                  # Unique key for rate-limiting
    visual_marker: Optional[Dict[str, Any]] = None


@dataclass
class EngineContext:
    """Runtime context passed to navigation rules during each frame evaluation."""
    timestamp: float
    frame_width: int
    frame_height: int
    fps: float
    detections: List[Any]              # List of Detection objects
    sensor_readings: Dict[str, SensorReading]
    audio_is_speaking: bool


class BaseSensorPlugin(ABC):
    """
    Abstract base class for hardware and virtual sensor integrations.
    Supports asynchronous or polled hardware communication (e.g. Serial, GPIO, I2C, ROS).
    """

    def __init__(self, sensor_id: str):
        self.sensor_id = sensor_id
        self._is_active = False

    @property
    def is_active(self) -> bool:
        return self._is_active

    @abstractmethod
    def initialize(self) -> bool:
        """Initializes hardware connection/bus. Returns True if successful."""
        pass

    @abstractmethod
    def read_data(self) -> Optional[SensorReading]:
        """Polls the latest reading from the sensor."""
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Checks if sensor communication is healthy."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Gracefully closes hardware ports and releases resources."""
        pass


class BaseNavigationRule(ABC):
    """
    Abstract base class for custom navigation rules and obstacle avoidance logic.
    Allows developers to implement domain-specific guidance (e.g. drop-off detection,
    path clearance recommendation, blind-spot checks) without modifying the core loop.
    """

    def __init__(self, rule_name: str, enabled: bool = True):
        self.rule_name = rule_name
        self.enabled = enabled

    @abstractmethod
    def evaluate(self, context: EngineContext) -> List[NavigationAlert]:
        """
        Evaluates current vision detections and sensor readings to produce navigation guidance alerts.
        """
        pass

    def reset(self) -> None:
        """Resets internal rule state between runs."""
        pass
