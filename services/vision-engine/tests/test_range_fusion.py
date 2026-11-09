import time
import pytest
from app.sensors.range_fusion import (
    CaneRangingTelemetry,
    ConservativeSensorFusionEngine,
    FusedHazardAssessment,
)


def test_fusion_clear_when_both_clear():
    engine = ConservativeSensorFusionEngine()
    engine.ingest_ranging_telemetry(
        CaneRangingTelemetry(
            timestamp=time.time(),
            forward_dist_cm=250.0,
            ground_dist_cm=85.0,
            nominal_ground_cm=85.0
        )
    )
    result = engine.evaluate_fusion(
        vision_hazard_detected=False,
        vision_hazard_type="none",
        vision_message_ne=""
    )
    assert result.alert_level == "CLEAR"
    assert result.veto_applied is False


def test_tof_vetoes_optimistic_vision_on_pothole_drop():
    """When monocular vision thinks the road is flat, but ToF detects an open hole (>12cm drop), ToF vetoes and forces CRITICAL_STOP."""
    engine = ConservativeSensorFusionEngine()
    now = time.time()
    # Nominal is 85cm, ground drops to 110cm (+25cm hole)
    engine.ingest_ranging_telemetry(
        CaneRangingTelemetry(
            timestamp=now,
            forward_dist_cm=200.0,
            ground_dist_cm=110.0,
            nominal_ground_cm=85.0
        )
    )
    # Monocular camera falsely claims "clear"
    result = engine.evaluate_fusion(
        vision_hazard_detected=False,
        vision_hazard_type="none",
        vision_message_ne="",
        current_time=now
    )
    assert result.alert_level == "CRITICAL_STOP"
    assert result.primary_source == "ranging_tof"
    assert result.veto_applied is True
    assert "खाल्डो" in result.hazard_description_ne


def test_ultrasonic_vetoes_optimistic_vision_on_head_obstacle():
    """When vision misses a head-height truck bed or awning, ultrasonic forces CRITICAL_STOP."""
    engine = ConservativeSensorFusionEngine()
    now = time.time()
    # Obstacle 60cm ahead (< 90cm critical threshold)
    engine.ingest_ranging_telemetry(
        CaneRangingTelemetry(
            timestamp=now,
            forward_dist_cm=60.0,
            ground_dist_cm=85.0,
            nominal_ground_cm=85.0
        )
    )
    result = engine.evaluate_fusion(
        vision_hazard_detected=False,
        vision_hazard_type="none",
        vision_message_ne="",
        current_time=now
    )
    assert result.alert_level == "CRITICAL_STOP"
    assert result.primary_source == "ultrasonic"
    assert result.veto_applied is True
    assert result.distance_m == 0.60
