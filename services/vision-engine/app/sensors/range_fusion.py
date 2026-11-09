"""
Trinetra Dual-Modality Sensor Fusion Engine
============================================
Conservative OR-Logic Ranging & Optical Vision Fusion.
Treats physical ranging sensors (ToF micro-LiDAR + Ultrasonic) as the primary,
high-reliability channel for collision and drop-off prevention, while monocular
RGB vision acts as the semantic classifier (objects, signs, banknotes, QR).

Safety Rule:
Ranging sensor hazard measurements ALWAYS veto optimistic vision clearance claims.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trinetra.sensors.fusion")


class RangingModality(str, Enum):
    TOF_LIDAR = "vl53l1x_tof"
    ULTRASONIC = "jsn_sr04t_ultrasonic"
    IMU = "mpu6050_imu"


@dataclass
class CaneRangingTelemetry:
    """Incoming real-time physical telemetry from white cane microcontroller."""
    timestamp: float
    forward_dist_cm: Optional[float] = None     # Forward/head-height ultrasonic distance
    ground_dist_cm: Optional[float] = None      # 15° downward-angled ToF ground distance
    nominal_ground_cm: float = 85.0             # Normal expected distance to flat ground (cane angle calibrated)
    pitch_deg: float = 0.0                      # Cane tilt angle from IMU
    roll_deg: float = 0.0                       # Cane roll angle from IMU
    cane_tapping: bool = True                   # Detected periodic cane ground contact


@dataclass
class FusedHazardAssessment:
    """Consolidated safety assessment emitted to acoustic/haptic dispatchers."""
    alert_level: str                            # "CRITICAL_STOP", "WARNING", "UNCERTAIN", "CLEAR"
    primary_source: str                         # "ranging_tof", "ultrasonic", "vision", "fused"
    distance_m: Optional[float] = None
    hazard_description_ne: str = ""
    hazard_description_en: str = ""
    veto_applied: bool = False                  # True if physical range sensor vetoed an optimistic vision report
    timestamp: float = field(default_factory=time.time)


class ConservativeSensorFusionEngine:
    """
    Implements deterministic OR-Logic gating:
    Alert = Vision_Hazard OR ToF_DropOff OR Ultrasonic_Proximity
    """

    def __init__(
        self,
        critical_forward_stop_cm: float = 90.0,   # Ultrasonic obstacle < 90cm -> Immediate STOP
        pothole_drop_threshold_cm: float = 12.0,  # Ground distance > nominal + 12cm -> Drop-off / hole
        step_up_threshold_cm: float = 12.0,       # Ground distance < nominal - 12cm -> Curb / raised step
    ):
        self.critical_forward_stop_cm = critical_forward_stop_cm
        self.pothole_drop_threshold_cm = pothole_drop_threshold_cm
        self.step_up_threshold_cm = step_up_threshold_cm
        self.last_ranging_packet: Optional[CaneRangingTelemetry] = None

    def ingest_ranging_telemetry(self, packet: CaneRangingTelemetry) -> None:
        """Buffers fresh serial/BLE ranging telemetry from cane microcontroller."""
        self.last_ranging_packet = packet

    def evaluate_fusion(
        self,
        vision_hazard_detected: bool,
        vision_hazard_type: str,
        vision_message_ne: str,
        current_time: Optional[float] = None
    ) -> FusedHazardAssessment:
        now = current_time or time.time()
        ranging = self.last_ranging_packet

        # Check for physical drop-off or obstacle via ranging first (High Reliability)
        if ranging and (now - ranging.timestamp < 0.350):  # Ranging data fresh within 350ms
            # 1. Forward Ultrasonic Obstacle (Head/Chest Height)
            if ranging.forward_dist_cm is not None and ranging.forward_dist_cm < self.critical_forward_stop_cm:
                return FusedHazardAssessment(
                    alert_level="CRITICAL_STOP",
                    primary_source="ultrasonic",
                    distance_m=round(ranging.forward_dist_cm / 100.0, 2),
                    hazard_description_ne="अगाडि नजिकै अवरोध छ, रोकिनुहोस्!",
                    hazard_description_en="Immediate obstacle ahead, stop!",
                    veto_applied=(not vision_hazard_detected),
                    timestamp=now
                )

            # 2. Downward ToF micro-LiDAR (Negative Obstacle / Pothole / Missing Manhole)
            if ranging.ground_dist_cm is not None:
                ground_delta = ranging.ground_dist_cm - ranging.nominal_ground_cm
                if ground_delta > self.pothole_drop_threshold_cm:
                    # Ground fell away: hole, trench, or missing manhole cover
                    return FusedHazardAssessment(
                        alert_level="CRITICAL_STOP",
                        primary_source="ranging_tof",
                        distance_m=round(ranging.ground_dist_cm / 100.0, 2),
                        hazard_description_ne="अगाडि जमिन भासिएको वा खुल्ला खाल्डो छ, रोकिनुहोस्!",
                        hazard_description_en="Ground drop-off or open trench detected by LiDAR, stop!",
                        veto_applied=(not vision_hazard_detected),
                        timestamp=now
                    )
                elif ground_delta < -self.step_up_threshold_cm:
                    # Ground raised: curb or step up
                    return FusedHazardAssessment(
                        alert_level="WARNING",
                        primary_source="ranging_tof",
                        distance_m=round(ranging.ground_dist_cm / 100.0, 2),
                        hazard_description_ne="अगाडि पेटी वा अग्लो सतह छ, होसियार!",
                        hazard_description_en="Raised curb or step detected ahead.",
                        veto_applied=(not vision_hazard_detected),
                        timestamp=now
                    )

        # 3. Vision-based Detection (if physical sensors are clear or absent)
        if vision_hazard_detected:
            if vision_hazard_type == "uncertain_terrain":
                return FusedHazardAssessment(
                    alert_level="UNCERTAIN",
                    primary_source="vision",
                    hazard_description_ne=vision_message_ne or "बाटो अस्पष्ट छ, छडीले छामेर हिँड्नुहोस्।",
                    hazard_description_en="Terrain visually unclear, probe with cane.",
                    veto_applied=False,
                    timestamp=now
                )
            return FusedHazardAssessment(
                alert_level="WARNING",
                primary_source="vision",
                hazard_description_ne=vision_message_ne,
                hazard_description_en="Hazard detected optically.",
                veto_applied=False,
                timestamp=now
            )

        return FusedHazardAssessment(
            alert_level="CLEAR",
            primary_source="fused",
            hazard_description_ne="",
            hazard_description_en="Clear path.",
            veto_applied=False,
            timestamp=now
        )
