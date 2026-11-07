"""
TRINETRA Navigation Rules & Obstacle Avoidance Processors
Implements pluggable domain logic for sensor fusion, path clearance, and urgent evasion cues.
"""

from typing import Dict, List

from core.spatial import Proximity, Zone
from plugins.base import BaseNavigationRule, EngineContext, NavigationAlert


class SensorFusionCollisionRule(BaseNavigationRule):
    """
    Fuses camera vision detections with hardware ultrasonic/LiDAR rangefinder data.
    When a physical sensor measures an obstacle < critical_distance_cm in the center
    and vision detects an object in the same zone, emits an immediate urgent halt command.
    """

    def __init__(
        self,
        rule_name: str = "SensorFusionCollisionRule",
        critical_distance_cm: float = 90.0,
        warning_distance_cm: float = 180.0
    ):
        super().__init__(rule_name=rule_name, enabled=True)
        self.critical_distance_cm = critical_distance_cm
        self.warning_distance_cm = warning_distance_cm

    def evaluate(self, context: EngineContext) -> List[NavigationAlert]:
        alerts: List[NavigationAlert] = []

        # Find any sensor reading corresponding to the Center zone
        center_sensor_reading = None
        for reading in context.sensor_readings.values():
            if reading.target_zone == Zone.CENTER and reading.distance_cm is not None:
                center_sensor_reading = reading
                break

        if not center_sensor_reading:
            return alerts

        dist_cm = center_sensor_reading.distance_cm

        # Check if vision also detects an object in center
        center_detections = [
            d for d in context.detections
            if d.spatial.zone == Zone.CENTER
        ]

        if dist_cm <= self.critical_distance_cm:
            # Physical obstacle is dangerously close!
            label = center_detections[0].label.capitalize() if center_detections else "Obstacle"
            alerts.append(NavigationAlert(
                message=f"Stop! {label} {int(dist_cm)} centimeters directly ahead.",
                priority=1,  # Critical Emergency
                source=self.rule_name,
                cooldown_key=f"fusion_critical_{label.lower()}",
                visual_marker={"urgency": "critical", "distance_cm": dist_cm}
            ))
        elif dist_cm <= self.warning_distance_cm and center_detections:
            # Approaching obstacle verified by both camera and sensor
            closest = center_detections[0]
            label = closest.label.capitalize()
            alerts.append(NavigationAlert(
                message=f"Caution: {label} ahead, {int(dist_cm)} centimeters.",
                priority=2,
                source=self.rule_name,
                cooldown_key=f"fusion_warning_{label.lower()}",
                visual_marker={"urgency": "warning", "distance_cm": dist_cm}
            ))

        return alerts


class PathClearanceRule(BaseNavigationRule):
    """
    Evaluates field of view clearance. If the center path is blocked by an obstacle,
    identifies whether the left or right corridor offers an unobstructed walking route.
    """

    def __init__(self, rule_name: str = "PathClearanceRule"):
        super().__init__(rule_name=rule_name, enabled=True)

    def evaluate(self, context: EngineContext) -> List[NavigationAlert]:
        alerts: List[NavigationAlert] = []

        # Group obstacles by zone
        zone_counts: Dict[Zone, int] = {Zone.LEFT: 0, Zone.CENTER: 0, Zone.RIGHT: 0}
        close_center_threats = []

        for d in context.detections:
            zone_counts[d.spatial.zone] += 1
            if d.spatial.zone == Zone.CENTER and d.spatial.proximity in (Proximity.IMMEDIATE, Proximity.APPROACHING):
                close_center_threats.append(d)

        # If center is obstructed by a close or approaching obstacle
        if close_center_threats:
            obstacle_label = close_center_threats[0].label.capitalize()

            left_clear = zone_counts[Zone.LEFT] == 0
            right_clear = zone_counts[Zone.RIGHT] == 0

            if left_clear and not right_clear:
                advice = f"Path ahead blocked by {obstacle_label}. Clear on your left."
                alerts.append(NavigationAlert(
                    message=advice,
                    priority=2,
                    source=self.rule_name,
                    cooldown_key="path_clear_left"
                ))
            elif right_clear and not left_clear:
                advice = f"Path ahead blocked by {obstacle_label}. Clear on your right."
                alerts.append(NavigationAlert(
                    message=advice,
                    priority=2,
                    source=self.rule_name,
                    cooldown_key="path_clear_right"
                ))
            elif left_clear and right_clear:
                advice = f"{obstacle_label} ahead. Path is clear on both sides."
                alerts.append(NavigationAlert(
                    message=advice,
                    priority=2,
                    source=self.rule_name,
                    cooldown_key="path_clear_both"
                ))

        return alerts
