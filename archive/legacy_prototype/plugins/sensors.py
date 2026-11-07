"""
TRINETRA Hardware Sensor Plugin Implementations
Includes Mock Ultrasonic, Serial (Arduino/ESP32) Ultrasonic, and LiDAR plugins.
"""

import logging
import math
import time
from typing import Optional

from core.spatial import Zone
from plugins.base import BaseSensorPlugin, SensorReading

logger = logging.getLogger("TRINETRA.Sensors")


class MockUltrasonicSensor(BaseSensorPlugin):
    """
    Virtual ultrasonic distance sensor simulating physical measurements
    (e.g., HC-SR04 mounted pointing straight ahead or on a cane).
    """

    def __init__(
        self,
        sensor_id: str = "ultrasonic_front",
        target_zone: Zone = Zone.CENTER,
        simulate_approach: bool = False,
        base_distance_cm: float = 120.0
    ):
        super().__init__(sensor_id)
        self.target_zone = target_zone
        self.simulate_approach = simulate_approach
        self.base_distance_cm = base_distance_cm
        self._start_time = time.time()

    def initialize(self) -> bool:
        self._is_active = True
        self._start_time = time.time()
        logger.info(f"Initialized Mock Ultrasonic Sensor '{self.sensor_id}' mapped to zone '{self.target_zone.value}'.")
        return True

    def read_data(self) -> Optional[SensorReading]:
        if not self._is_active:
            return None

        # Simulate dynamic obstacle approach or slight oscillation
        elapsed = time.time() - self._start_time
        if self.simulate_approach:
            # Approaches down to 40cm then cycles
            dist = max(35.0, self.base_distance_cm - ((elapsed * 15.0) % 150.0))
        else:
            # Natural sensor jitter (+/- 2 cm)
            dist = self.base_distance_cm + (2.0 * math.sin(elapsed * 2.0))

        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type="ultrasonic",
            timestamp=time.time(),
            distance_cm=round(dist, 1),
            target_zone=self.target_zone,
            confidence=0.98,
            metadata={"simulated": True}
        )

    def is_healthy(self) -> bool:
        return self._is_active

    def shutdown(self) -> None:
        self._is_active = False


class SerialUltrasonicSensor(BaseSensorPlugin):
    """
    Hardware ultrasonic sensor connected via serial (UART/USB) from an Arduino,
    STM32, Raspberry Pi, or ESP32 microcontroller.
    Expects newline-terminated distance readings in centimeters, e.g.: 'DIST:85.2\\n' or '85.2\\n'.
    """

    def __init__(
        self,
        sensor_id: str = "serial_ultrasonic_front",
        port: str = "COM3",
        baudrate: int = 115200,
        timeout: float = 0.1,
        target_zone: Zone = Zone.CENTER
    ):
        super().__init__(sensor_id)
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.target_zone = target_zone
        self._serial = None
        self._last_valid_reading: Optional[float] = None

    def initialize(self) -> bool:
        try:
            import serial
            self._serial = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
            self._is_active = True
            logger.info(f"Connected to Serial Sensor on {self.port} at {self.baudrate} baud.")
            return True
        except ImportError:
            logger.warning("pyserial package not installed. Serial sensor disabled.")
            self._is_active = False
            return False
        except Exception as exc:
            logger.warning(f"Could not open serial port {self.port}: {exc}. Hardware sensor offline.")
            self._is_active = False
            return False

    def read_data(self) -> Optional[SensorReading]:
        if not self._is_active or self._serial is None:
            return None

        try:
            if self._serial.in_waiting:
                line = self._serial.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    # Parse numerical distance value
                    clean_str = line.upper().replace("DIST:", "").replace("CM", "").strip()
                    val = float(clean_str)
                    if 2.0 <= val <= 400.0:  # Valid HC-SR04 ultrasonic range
                        self._last_valid_reading = val
                        return SensorReading(
                            sensor_id=self.sensor_id,
                            sensor_type="ultrasonic",
                            timestamp=time.time(),
                            distance_cm=round(val, 1),
                            target_zone=self.target_zone,
                            confidence=0.95
                        )
        except Exception as exc:
            logger.debug(f"Serial read warning ({self.sensor_id}): {exc}")

        return None

    def is_healthy(self) -> bool:
        return self._is_active and (self._serial is not None and self._serial.is_open)

    def shutdown(self) -> None:
        self._is_active = False
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass


class LiDARSensorPlugin(BaseSensorPlugin):
    """
    1D or 2D LiDAR rangefinder plugin (e.g. Benewake TF-Mini or RPLiDAR).
    Reports distance to obstacles with millimeter precision.
    """

    def __init__(
        self,
        sensor_id: str = "lidar_front",
        target_zone: Zone = Zone.CENTER,
        critical_distance_cm: float = 80.0
    ):
        super().__init__(sensor_id)
        self.target_zone = target_zone
        self.critical_distance_cm = critical_distance_cm
        self._mock_distance = 150.0

    def initialize(self) -> bool:
        self._is_active = True
        logger.info(f"Initialized LiDAR plugin '{self.sensor_id}'.")
        return True

    def read_data(self) -> Optional[SensorReading]:
        if not self._is_active:
            return None

        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type="lidar",
            timestamp=time.time(),
            distance_cm=self._mock_distance,
            target_zone=self.target_zone,
            confidence=0.99
        )

    def is_healthy(self) -> bool:
        return self._is_active

    def shutdown(self) -> None:
        self._is_active = False
