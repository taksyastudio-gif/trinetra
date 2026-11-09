"""
Unit tests for CaneSensorReader and its integration with ConservativeSensorFusionEngine.
"""

import time
from app.sensors.range_fusion import ConservativeSensorFusionEngine
from app.sensors.cane_reader import CaneSensorReader


def test_cane_reader_parse_json():
    engine = ConservativeSensorFusionEngine()
    reader = CaneSensorReader(fusion_engine=engine)

    raw_json = '{"f_dist": 65.5, "g_dist": 84.2, "nom_g": 85.0, "pitch": -3.5, "roll": 1.2, "tap": true}'
    packet = reader.parse_line(raw_json)

    assert packet is not None
    assert packet.forward_dist_cm == 65.5
    assert packet.ground_dist_cm == 84.2
    assert packet.pitch_deg == -3.5
    assert packet.roll_deg == 1.2
    assert packet.cane_tapping is True


def test_cane_reader_parse_csv():
    engine = ConservativeSensorFusionEngine()
    reader = CaneSensorReader(fusion_engine=engine)

    raw_csv = "CANE,55.0,86.0,-1.5,0.8,1"
    packet = reader.parse_line(raw_csv)

    assert packet is not None
    assert packet.forward_dist_cm == 55.0
    assert packet.ground_dist_cm == 86.0
    assert packet.pitch_deg == -1.5
    assert packet.roll_deg == 0.8
    assert packet.cane_tapping is True


def test_cane_reader_ingestion_and_fusion_veto():
    """Verifies that an incoming obstacle line ingested by CaneSensorReader immediately vetoes vision."""
    engine = ConservativeSensorFusionEngine(critical_forward_stop_cm=90.0)
    reader = CaneSensorReader(fusion_engine=engine)

    # Ingest forward obstacle at 60cm (below 90cm threshold)
    reader.ingest_line("CANE,60.0,85.0,0.0,0.0,1")

    assert reader.is_connected() is True
    assert reader.get_status()["packets_received"] == 1

    # Vision says: "Clear path ahead, zero obstacles"
    assessment = engine.evaluate_fusion(
        vision_hazard_detected=False,
        vision_hazard_type="none",
        vision_message_ne="बाटो सफा छ",
    )

    # Physical sensor MUST override and veto!
    assert assessment.alert_level == "CRITICAL_STOP"
    assert assessment.primary_source == "ultrasonic"
    assert assessment.veto_applied is True
    assert "रोकिनुहोस्" in assessment.hazard_description_ne


def test_cane_reader_pothole_drop_veto():
    """Verifies that downward ToF ground drop (e.g. open manhole) vetoes optimistic vision."""
    engine = ConservativeSensorFusionEngine(pothole_drop_threshold_cm=12.0)
    reader = CaneSensorReader(fusion_engine=engine)

    # Ingest ground distance of 110cm (nominal 85cm + 25cm drop into hole)
    reader.ingest_line('{"f_dist": 200.0, "g_dist": 110.0, "nom_g": 85.0}')

    assessment = engine.evaluate_fusion(
        vision_hazard_detected=False,
        vision_hazard_type="none",
        vision_message_ne="बाटो सफा छ",
    )

    assert assessment.alert_level == "CRITICAL_STOP"
    assert assessment.primary_source == "ranging_tof"
    assert assessment.veto_applied is True
    assert "खाल्डो" in assessment.hazard_description_ne
