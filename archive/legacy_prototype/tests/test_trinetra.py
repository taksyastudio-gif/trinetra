"""
TRINETRA Comprehensive Unit & Integration Test Suite
Tests spatial positioning logic, thread-safe TTS queue, cooldown rate-limiting,
sensor plugins, navigation rules, and the master engine execution pipeline.
"""

import time
import unittest
import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import EngineConfig, SpatialConfig, TTSConfig, DetectorConfig
from core.spatial import SpatialAnalyzer, Zone, Proximity
from core.tts_queue import TTSQueueManager, CooldownManager, AudioAlert
from core.detector import ObjectDetector, Detection
from plugins.base import EngineContext, SensorReading
from plugins.sensors import MockUltrasonicSensor
from plugins.navigation_rules import SensorFusionCollisionRule, PathClearanceRule
from trinetra_engine import TrinetraEngine, SyntheticVideoSource


class TestSpatialPositioning(unittest.TestCase):
    """Verifies horizontal zone determination, proximity calculations, and threat levels."""

    def setUp(self):
        self.analyzer = SpatialAnalyzer(
            left_zone_boundary=0.35,
            right_zone_boundary=0.65,
            immediate_height_ratio=0.42,
            approaching_height_ratio=0.22,
            bottom_proximity_ratio=0.85
        )
        self.frame_w = 640
        self.frame_h = 480

    def test_left_zone(self):
        # Box centered around x = 100 (100 / 640 = 0.156 < 0.35)
        bbox = (50, 100, 150, 250)
        res = self.analyzer.calculate_spatial_position(bbox, self.frame_w, self.frame_h, "chair")
        self.assertEqual(res.zone, Zone.LEFT)
        self.assertIn("on your left", res.speech_phrase)

    def test_center_zone_straight_ahead(self):
        # Box centered around x = 320 (320 / 640 = 0.50 -> between 0.35 and 0.65)
        bbox = (260, 200, 380, 420)
        res = self.analyzer.calculate_spatial_position(bbox, self.frame_w, self.frame_h, "person")
        self.assertEqual(res.zone, Zone.CENTER)

    def test_right_zone(self):
        # Box centered around x = 550 (550 / 640 = 0.859 > 0.65)
        bbox = (500, 150, 600, 300)
        res = self.analyzer.calculate_spatial_position(bbox, self.frame_w, self.frame_h, "dog")
        self.assertEqual(res.zone, Zone.RIGHT)
        self.assertIn("on your right", res.speech_phrase)

    def test_immediate_proximity_and_threat_level_1(self):
        # Large bounding box in center, occupying > 42% height and near ground
        # height = 450 - 100 = 350 / 480 = 72%
        bbox = (240, 100, 400, 450)
        res = self.analyzer.calculate_spatial_position(bbox, self.frame_w, self.frame_h, "table")
        self.assertEqual(res.zone, Zone.CENTER)
        self.assertEqual(res.proximity, Proximity.IMMEDIATE)
        self.assertEqual(res.threat_level, 1)  # Priority 1 critical emergency
        self.assertIn("Caution!", res.speech_phrase)
        self.assertIn("directly ahead", res.speech_phrase)

    def test_approaching_proximity(self):
        # Medium bounding box in center (height ~ 30%)
        # height = 150 / 480 = 0.312
        bbox = (280, 180, 360, 330)
        res = self.analyzer.calculate_spatial_position(bbox, self.frame_w, self.frame_h, "person")
        self.assertEqual(res.zone, Zone.CENTER)
        self.assertEqual(res.proximity, Proximity.APPROACHING)
        self.assertEqual(res.threat_level, 2)


class TestTTSQueueAndCooldown(unittest.TestCase):
    """Verifies thread-safe audio dispatch, rate-limiting, and urgency escalation."""

    def setUp(self):
        self.config = TTSConfig(
            default_cooldown_sec=2.0,
            critical_cooldown_sec=1.0,
            approaching_cooldown_sec=1.5,
            distant_cooldown_sec=3.0,
            mute_audio=False
        )
        self.cooldown = CooldownManager(self.config)

    def test_cooldown_suppression(self):
        key = "chair:straight ahead:immediate"
        # First time: not suppressed
        self.assertFalse(self.cooldown.should_suppress(key, priority=1))

        # Record spoken
        self.cooldown.record_spoken(key, priority=1)

        # Immediately after: suppressed
        self.assertTrue(self.cooldown.should_suppress(key, priority=1))

    def test_urgency_escalation_bypasses_cooldown(self):
        key = "person:straight ahead:approaching"
        # Spoken at priority 3
        self.cooldown.record_spoken(key, priority=3)

        # Wait 1.05s (less than the 2.0s standard cooldown, but >= 1.0s escalation window)
        time.sleep(1.05)

        # Still suppressed for normal priority 3
        self.assertTrue(self.cooldown.should_suppress(key, priority=3))

        # Bypassed when escalated to critical priority 1
        self.assertFalse(self.cooldown.should_suppress(key, priority=1))

    def test_tts_worker_lifecycle(self):
        tts = TTSQueueManager(self.config)
        tts.start()
        try:
            # Enqueue high priority speech
            success = tts.speak("Test alert one", priority=1, alert_key="test_1")
            self.assertTrue(success)

            # Give worker thread time to process
            time.sleep(0.5)

            # Recent speech history should record the announcement
            recent = tts.get_recent_speech()
            self.assertGreaterEqual(len(recent), 1)
            self.assertEqual(recent[-1][1], "Test alert one")
            self.assertEqual(recent[-1][2], 1)
        finally:
            tts.stop()


class TestPluginSystem(unittest.TestCase):
    """Verifies sensor plugins and pluggable navigation rule execution."""

    def test_mock_ultrasonic_sensor(self):
        sensor = MockUltrasonicSensor(sensor_id="us_test", target_zone=Zone.CENTER, base_distance_cm=100.0)
        self.assertTrue(sensor.initialize())
        self.assertTrue(sensor.is_healthy())

        reading = sensor.read_data()
        self.assertIsNotNone(reading)
        self.assertEqual(reading.sensor_id, "us_test")
        self.assertEqual(reading.target_zone, Zone.CENTER)
        self.assertAlmostEqual(reading.distance_cm, 100.0, delta=5.0)

        sensor.shutdown()
        self.assertFalse(sensor.is_healthy())

    def test_sensor_fusion_collision_rule(self):
        rule = SensorFusionCollisionRule(critical_distance_cm=80.0)
        analyzer = SpatialAnalyzer()

        # Create dummy detection in center
        det_spatial = analyzer.calculate_spatial_position((260, 200, 380, 420), 640, 480, "door")
        det = Detection(class_id=1, label="door", confidence=0.9, bbox=(260, 200, 380, 420), spatial=det_spatial)

        # Sensor reading reporting 55cm (below 80cm critical threshold)
        reading = SensorReading(
            sensor_id="us_front",
            sensor_type="ultrasonic",
            timestamp=time.time(),
            distance_cm=55.0,
            target_zone=Zone.CENTER
        )

        context = EngineContext(
            timestamp=time.time(),
            frame_width=640,
            frame_height=480,
            fps=30.0,
            detections=[det],
            sensor_readings={"us_front": reading},
            audio_is_speaking=False
        )

        alerts = rule.evaluate(context)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].priority, 1)  # Priority 1 Emergency
        self.assertIn("Stop!", alerts[0].message)
        self.assertIn("55 centimeters", alerts[0].message)

    def test_path_clearance_rule(self):
        rule = PathClearanceRule()
        analyzer = SpatialAnalyzer()

        # Create immediate obstacle in center and obstacle on right, leaving left completely clear
        center_spatial = analyzer.calculate_spatial_position((250, 100, 390, 440), 640, 480, "chair")
        right_spatial = analyzer.calculate_spatial_position((500, 150, 600, 350), 640, 480, "cart")

        d_center = Detection(1, "chair", 0.9, (250, 100, 390, 440), center_spatial)
        d_right = Detection(2, "cart", 0.8, (500, 150, 600, 350), right_spatial)

        context = EngineContext(
            timestamp=time.time(),
            frame_width=640,
            frame_height=480,
            fps=30.0,
            detections=[d_center, d_right],
            sensor_readings={},
            audio_is_speaking=False
        )

        alerts = rule.evaluate(context)
        self.assertEqual(len(alerts), 1)
        self.assertIn("Clear on your left", alerts[0].message)


class TestTrinetraEngineIntegration(unittest.TestCase):
    """Verifies end-to-end frame processing in TrinetraEngine."""

    def test_engine_single_step(self):
        cfg = EngineConfig(
            headless=True,
            detector=DetectorConfig(use_mock=True),
            tts=TTSConfig(mute_audio=True)
        )
        engine = TrinetraEngine(config=cfg)
        engine.register_navigation_rule(PathClearanceRule())
        mock_sensor = MockUltrasonicSensor("front_us", Zone.CENTER, base_distance_cm=95.0)
        engine.register_sensor(mock_sensor)

        engine.start()
        try:
            # Generate synthetic frame
            source = SyntheticVideoSource(640, 480)
            ret, frame = source.read()
            self.assertTrue(ret)

            # Process single frame
            detections, readings, annotated = engine.process_frame(frame)
            self.assertIsInstance(detections, list)
            self.assertGreater(len(detections), 0)
            self.assertIn("front_us", readings)
        finally:
            engine.stop()


if __name__ == "__main__":
    unittest.main()
