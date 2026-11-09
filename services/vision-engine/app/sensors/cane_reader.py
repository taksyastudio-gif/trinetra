"""
Trinetra White Cane Sensor Ingestion Worker
==========================================
Connects via USB-Serial or Bluetooth SPP/BLE to the smart cane microcontroller
(ESP32 / RP2040 / Arduino Nano with JSN-SR04T ultrasonic + VL53L1X ToF + MPU6050 IMU).
Parses real-time telemetry and feeds into the ConservativeSensorFusionEngine.
"""

from __future__ import annotations
import json
import logging
import threading
import time
from typing import Callable, Optional

from app.sensors.range_fusion import CaneRangingTelemetry, ConservativeSensorFusionEngine

logger = logging.getLogger("trinetra.sensors.cane_reader")


class CaneSensorReader:
    """
    Background worker that ingests serial or BLE ASCII lines from the smart cane.
    Supports JSON packets or delimited strings:
      JSON: {"f_dist": 65.0, "g_dist": 85.0, "pitch": -2.1, "roll": 0.5, "tap": true}
      CSV:  CANE,65.0,85.0,-2.1,0.5,1
    """

    def __init__(
        self,
        fusion_engine: ConservativeSensorFusionEngine,
        port: Optional[str] = None,
        baudrate: int = 115200,
        timeout: float = 1.0,
        on_packet_callback: Optional[Callable[[CaneRangingTelemetry], None]] = None,
    ):
        self.fusion_engine = fusion_engine
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.on_packet_callback = on_packet_callback

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._last_packet_time: float = 0.0
        self._packets_received: int = 0
        self._parse_errors: int = 0
        self._serial = None

    def parse_line(self, raw_line: str) -> Optional[CaneRangingTelemetry]:
        """Parses a single line of raw telemetry into a typed CaneRangingTelemetry object."""
        line = raw_line.strip()
        if not line:
            return None

        now = time.time()
        try:
            # Format 1: JSON payload
            if line.startswith("{") and line.endswith("}"):
                data = json.loads(line)
                return CaneRangingTelemetry(
                    timestamp=now,
                    forward_dist_cm=float(data["f_dist"]) if "f_dist" in data and data["f_dist"] is not None else None,
                    ground_dist_cm=float(data["g_dist"]) if "g_dist" in data and data["g_dist"] is not None else None,
                    nominal_ground_cm=float(data.get("nom_g", 85.0)),
                    pitch_deg=float(data.get("pitch", 0.0)),
                    roll_deg=float(data.get("roll", 0.0)),
                    cane_tapping=bool(data.get("tap", True)),
                )

            # Format 2: Compact CSV: CANE,forward_cm,ground_cm,pitch,roll,tapping
            if line.startswith("CANE,"):
                parts = line.split(",")
                if len(parts) >= 3:
                    f_dist = float(parts[1]) if parts[1] != "" else None
                    g_dist = float(parts[2]) if parts[2] != "" else None
                    pitch = float(parts[3]) if len(parts) > 3 and parts[3] != "" else 0.0
                    roll = float(parts[4]) if len(parts) > 4 and parts[4] != "" else 0.0
                    tap = bool(int(parts[5])) if len(parts) > 5 and parts[5] != "" else True
                    return CaneRangingTelemetry(
                        timestamp=now,
                        forward_dist_cm=f_dist,
                        ground_dist_cm=g_dist,
                        pitch_deg=pitch,
                        roll_deg=roll,
                        cane_tapping=tap,
                    )
        except Exception as exc:
            self._parse_errors += 1
            logger.debug(f"Failed to parse cane telemetry line '{line}': {exc}")

        return None

    def ingest_line(self, raw_line: str) -> Optional[CaneRangingTelemetry]:
        """Directly ingests a line (used by serial reader loop or synthetic test feeds)."""
        packet = self.parse_line(raw_line)
        if packet:
            with self._lock:
                self._last_packet_time = packet.timestamp
                self._packets_received += 1
            self.fusion_engine.ingest_ranging_telemetry(packet)
            if self.on_packet_callback:
                try:
                    self.on_packet_callback(packet)
                except Exception as exc:
                    logger.error(f"Error in on_packet_callback: {exc}")
        return packet

    def is_connected(self, max_staleness_seconds: float = 1.0) -> bool:
        """Returns True if valid telemetry arrived within the staleness window."""
        with self._lock:
            if self._last_packet_time == 0.0:
                return False
            return (time.time() - self._last_packet_time) < max_staleness_seconds

    def get_status(self) -> dict:
        """Returns reader health and packet statistics."""
        with self._lock:
            return {
                "running": self._running,
                "port": self.port,
                "connected": self.is_connected(),
                "packets_received": self._packets_received,
                "parse_errors": self._parse_errors,
                "last_packet_at": self._last_packet_time,
            }

    def start(self) -> None:
        """Starts background reader thread if a serial port is configured."""
        if not self.port:
            logger.info("CaneSensorReader: No port specified; operating in manual/synthetic ingestion mode")
            return
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_serial_loop, daemon=True, name="TrinetraCaneReader")
        self._thread.start()

    def stop(self) -> None:
        """Stops the reader thread and closes the serial connection."""
        self._running = False
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _run_serial_loop(self) -> None:
        """Continuously reads lines from the serial port with reconnect logic."""
        while self._running:
            try:
                import serial
                if self._serial is None:
                    self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                    logger.info(f"Connected to smart cane on {self.port}")

                line = self._serial.readline().decode("utf-8", errors="replace")
                if line:
                    self.ingest_line(line)
            except Exception as exc:
                if self._running:
                    logger.warning(f"Cane serial error on {self.port}: {exc}. Retrying in 2s...")
                    if self._serial:
                        try:
                            self._serial.close()
                        except Exception:
                            pass
                        self._serial = None
                    time.sleep(2.0)
