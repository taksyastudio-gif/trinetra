"""
TRINETRA: AI-Assisted Vision and Navigation Application for Visually Impaired Individuals
Core Backend Engine (trinetra_engine.py)

Orchestrates real-time video stream ingestion, YOLOv8 object detection, spatial positioning,
hardware sensor telemetry fusion, pluggable navigation rules, and a thread-safe
pyttsx3 Text-to-Speech queue system with rate-limited cooldown timers.
"""

import argparse
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from config import EngineConfig, SpatialConfig, TTSConfig, DetectorConfig, VisualizerConfig
from core.spatial import SpatialAnalyzer, Zone, Proximity
from core.detector import ObjectDetector, Detection
from core.tts_queue import TTSQueueManager
from core.visualizer import DebugVisualizer
from plugins.base import (
    BaseSensorPlugin,
    BaseNavigationRule,
    SensorReading,
    NavigationAlert,
    EngineContext
)
from plugins.sensors import MockUltrasonicSensor
from plugins.navigation_rules import SensorFusionCollisionRule, PathClearanceRule

# Configure application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TRINETRA.Engine")


class SyntheticVideoSource:
    """
    Generates synthetic frames for testing, simulation, and headless execution
    when physical webcams or video files are not attached.
    """

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self._cv2 = None
        self._np = None
        self._frame_count = 0
        try:
            import cv2
            import numpy as np
            self._cv2 = cv2
            self._np = np
        except ImportError:
            pass

    def read(self) -> Tuple[bool, Any]:
        """Returns synthetic frame with grid and simulated visual elements."""
        self._frame_count += 1
        time.sleep(1.0 / self.fps)

        if self._np is None:
            # Dummy fallback if numpy is not installed
            return True, None

        # Create dark slate simulated camera background
        frame = self._np.zeros((self.height, self.width, 3), dtype=self._np.uint8)
        frame[:] = (35, 30, 25)

        if self._cv2 is not None:
            cv2 = self._cv2
            # Draw synthetic room floor perspective lines
            cv2.line(frame, (0, self.height), (int(self.width * 0.35), int(self.height * 0.5)), (55, 55, 55), 1)
            cv2.line(frame, (self.width, self.height), (int(self.width * 0.65), int(self.height * 0.5)), (55, 55, 55), 1)
            cv2.line(frame, (0, int(self.height * 0.5)), (self.width, int(self.height * 0.5)), (60, 60, 60), 1)

            # Simulated obstacle in center (simulating approaching chair)
            box_w = int(120 + 20 * (self._frame_count % 30) / 10)
            box_h = int(140 + 25 * (self._frame_count % 30) / 10)
            cx = int(self.width * 0.5)
            cy = int(self.height * 0.65)
            cv2.rectangle(
                frame,
                (cx - box_w // 2, cy - box_h // 2),
                (cx + box_w // 2, cy + box_h // 2),
                (180, 110, 50),
                -1
            )

        return True, frame

    def release(self) -> None:
        pass


class TrinetraEngine:
    """
    Master navigation backend engine for TRINETRA.
    """

    def __init__(self, config: Optional[EngineConfig] = None):
        self.config = config or EngineConfig()
        self.is_running = False

        # 1. Initialize Spatial Reasoning Subsystem
        self.spatial_analyzer = SpatialAnalyzer(
            left_zone_boundary=self.config.spatial.left_zone_boundary,
            right_zone_boundary=self.config.spatial.right_zone_boundary,
            immediate_height_ratio=self.config.spatial.immediate_height_ratio,
            approaching_height_ratio=self.config.spatial.approaching_height_ratio,
            bottom_proximity_ratio=self.config.spatial.bottom_proximity_ratio
        )

        # 2. Initialize Object Detection Subsystem (YOLOv8)
        self.detector = ObjectDetector(
            config=self.config.detector,
            spatial_analyzer=self.spatial_analyzer
        )

        # 3. Initialize Thread-Safe TTS Audio Queue
        self.tts = TTSQueueManager(config=self.config.tts)

        # 4. Initialize Visualizer HUD
        self.visualizer = DebugVisualizer(
            config=self.config.visualizer,
            left_boundary=self.config.spatial.left_zone_boundary,
            right_boundary=self.config.spatial.right_zone_boundary
        )

        # 5. Extension Points / Plugin Registries
        self._sensors: Dict[str, BaseSensorPlugin] = {}
        self._navigation_rules: Dict[str, BaseNavigationRule] = {}

        # Video Capture handle
        self._cap = None
        self._is_synthetic_feed = False

        # Runtime telemetry metrics
        self._fps: float = 0.0
        self._last_fps_calc_time = time.time()
        self._frames_counted = 0

    # =========================================================================
    # Plugin Extension Points
    # =========================================================================

    def register_sensor(self, sensor: BaseSensorPlugin) -> bool:
        """
        Plugs in an external hardware or virtual sensor (e.g., Ultrasonic, LiDAR, IMU).
        """
        logger.info(f"Registering sensor plugin '{sensor.sensor_id}'...")
        if sensor.initialize():
            self._sensors[sensor.sensor_id] = sensor
            logger.info(f"Sensor plugin '{sensor.sensor_id}' active.")
            return True
        else:
            logger.warning(f"Sensor plugin '{sensor.sensor_id}' failed initialization.")
            return False

    def unregister_sensor(self, sensor_id: str) -> None:
        """Unregisters and terminates a sensor plugin."""
        if sensor_id in self._sensors:
            try:
                self._sensors[sensor_id].shutdown()
            except Exception as exc:
                logger.error(f"Error shutting down sensor '{sensor_id}': {exc}")
            del self._sensors[sensor_id]
            logger.info(f"Unregistered sensor '{sensor_id}'.")

    def register_navigation_rule(self, rule: BaseNavigationRule) -> None:
        """
        Plugs in a custom obstacle avoidance or navigation guidance rule.
        """
        self._navigation_rules[rule.rule_name] = rule
        logger.info(f"Registered navigation rule: '{rule.rule_name}'.")

    def unregister_navigation_rule(self, rule_name: str) -> None:
        """Removes a navigation rule."""
        if rule_name in self._navigation_rules:
            del self._navigation_rules[rule_name]
            logger.info(f"Unregistered navigation rule '{rule_name}'.")

    # =========================================================================
    # Video Ingestion Management
    # =========================================================================

    def _init_video_source(self) -> None:
        """Initializes OpenCV VideoCapture with fallback to synthetic stream."""
        source_str = str(self.config.video_source).strip()

        # Parse numeric camera index or stream string
        camera_idx = int(source_str) if source_str.isdigit() else source_str

        try:
            import cv2
            logger.info(f"Opening video capture stream from source: {camera_idx}")
            cap = cv2.VideoCapture(camera_idx)

            if cap and cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
                cap.set(cv2.CAP_PROP_FPS, self.config.target_fps)
                self._cap = cap
                self._is_synthetic_feed = False
                logger.info("Video capture opened successfully.")
                return
            else:
                logger.warning(f"Unable to open video source '{source_str}'. Falling back to SyntheticVideoSource.")
        except Exception as exc:
            logger.warning(f"OpenCV VideoCapture exception ({exc}). Falling back to SyntheticVideoSource.")

        # Fallback to simulated synthetic camera feed
        self._cap = SyntheticVideoSource(
            width=self.config.frame_width,
            height=self.config.frame_height,
            fps=self.config.target_fps
        )
        self._is_synthetic_feed = True
        logger.info("Synthetic video source initialized.")

    # =========================================================================
    # Core Processing Pipeline
    # =========================================================================

    def process_frame(self, frame: Any) -> Tuple[List[Detection], Dict[str, SensorReading], Optional[Any]]:
        """
        Executes a single end-to-end iteration of the TRINETRA perception pipeline:
        1. Reads hardware sensor data.
        2. Detects objects via YOLOv8 and analyzes spatial positioning.
        3. Evaluates custom navigation rules.
        4. Prioritizes and dispatches speech guidance with cooldown rate-limiting.
        5. Renders debug window HUD overlays.

        Args:
            frame: Video frame image.

        Returns:
            Tuple of (detections, sensor_readings, annotated_frame).
        """
        # Determine frame dimensions
        if hasattr(frame, "shape"):
            frame_h, frame_w = frame.shape[:2]
        else:
            frame_w, frame_h = self.config.frame_width, self.config.frame_height

        # Step 1: Ingest sensor telemetry
        current_readings: Dict[str, SensorReading] = {}
        for sensor_id, sensor in list(self._sensors.items()):
            try:
                reading = sensor.read_data()
                if reading:
                    current_readings[sensor_id] = reading
            except Exception as exc:
                logger.debug(f"Sensor read exception on '{sensor_id}': {exc}")

        # Step 2: Edge object detection & spatial calculation
        detections: List[Detection] = self.detector.detect(frame)

        # Step 3: Formulate Engine Context
        context = EngineContext(
            timestamp=time.time(),
            frame_width=frame_w,
            frame_height=frame_h,
            fps=self._fps,
            detections=detections,
            sensor_readings=current_readings,
            audio_is_speaking=self.tts.is_speaking
        )

        # Step 4: Evaluate Navigation Rules
        rule_alerts: List[NavigationAlert] = []
        for rule_name, rule in self._navigation_rules.items():
            if rule.enabled:
                try:
                    alerts = rule.evaluate(context)
                    if alerts:
                        rule_alerts.extend(alerts)
                except Exception as exc:
                    logger.error(f"Error evaluating rule '{rule_name}': {exc}")

        # Step 5: Queue prioritized audio warnings
        # 5a. First, dispatch rule-generated high-priority alerts (e.g. sensor collision / path guidance)
        for alert in rule_alerts:
            self.tts.speak(
                message=alert.message,
                priority=alert.priority,
                alert_key=alert.cooldown_key,
                source=alert.source
            )

        # 5b. Next, process vision obstacle detections
        # Sort detections by threat urgency (threat_level 1 first)
        sorted_detections = sorted(detections, key=lambda d: d.spatial.threat_level)
        for det in sorted_detections:
            # Only announce if threat level <= 3 or center obstacle
            if det.spatial.threat_level <= 3 or det.spatial.zone == Zone.CENTER:
                self.tts.speak(
                    message=det.spatial.speech_phrase,
                    priority=det.spatial.threat_level,
                    alert_key=det.alert_key,
                    source="vision"
                )

        # Step 6: Render visualizer overlay
        annotated_frame = self.visualizer.render(
            frame=frame,
            detections=detections,
            fps=self._fps,
            sensor_readings=current_readings,
            current_speech=self.tts.current_utterance,
            recent_speech_list=self.tts.get_recent_speech(),
            is_muted=self.config.tts.mute_audio
        )

        return detections, current_readings, annotated_frame

    def start(self) -> None:
        """Initializes resources, audio thread, and video stream."""
        logger.info("Initializing TRINETRA Vision Engine...")
        self.tts.start()
        self._init_video_source()
        self.is_running = True
        logger.info("TRINETRA Vision Engine is operational.")

    def run(self) -> None:
        """Main execution loop."""
        self.start()

        try:
            while self.is_running:
                loop_start = time.time()

                if self._cap is None:
                    break

                ret, frame = self._cap.read()
                if not ret or frame is None:
                    # In case of stream drop, brief sleep and retry
                    time.sleep(0.05)
                    continue

                # Process pipeline
                detections, readings, annotated_frame = self.process_frame(frame)

                # Render display & poll user input
                if annotated_frame is not None and not self.config.headless:
                    key = self.visualizer.show(annotated_frame)
                    if key in (ord('q'), 27):  # 'q' or ESC
                        logger.info("Exit key pressed. Stopping...")
                        break
                    elif key == ord('m'):
                        self.config.tts.mute_audio = not self.config.tts.mute_audio
                        logger.info(f"Audio mute toggled: {self.config.tts.mute_audio}")
                    elif key == ord('d'):
                        self.config.visualizer.show_hud = not self.config.visualizer.show_hud
                        logger.info(f"Debug HUD toggled: {self.config.visualizer.show_hud}")

                # Update FPS calculation
                self._frames_counted += 1
                now = time.time()
                elapsed = now - self._last_fps_calc_time
                if elapsed >= 1.0:
                    self._fps = self._frames_counted / elapsed
                    self._frames_counted = 0
                    self._last_fps_calc_time = now

                # Respect target FPS rate-limiting
                process_duration = time.time() - loop_start
                target_period = 1.0 / self.config.target_fps
                if process_duration < target_period:
                    time.sleep(target_period - process_duration)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Shutting down...")
        finally:
            self.stop()

    def stop(self) -> None:
        """Shuts down all engine subsystems cleanly."""
        self.is_running = False

        logger.info("Shutting down TRINETRA Engine subsystems...")
        # 1. Stop video stream
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

        # 2. Close visualizer
        self.visualizer.close()

        # 3. Stop TTS worker
        self.tts.stop()

        # 4. Shutdown sensors
        for sensor_id in list(self._sensors.keys()):
            self.unregister_sensor(sensor_id)

        logger.info("TRINETRA Engine successfully halted.")


# =============================================================================
# Command-Line Interface Entry Point
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TRINETRA: AI Vision and Navigation Engine for Visually Impaired Individuals"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Video source: camera index (e.g. 0), video file path, or RTSP stream"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="Path to YOLOv8 model weights (default: yolov8n.pt)"
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.45,
        help="YOLO detection confidence threshold (default: 0.45)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without displaying OpenCV GUI window"
    )
    parser.add_argument(
        "--mute",
        action="store_true",
        help="Mute Text-to-Speech audio output"
    )
    parser.add_argument(
        "--mock-sensor",
        action="store_true",
        help="Attach virtual ultrasonic distance sensor"
    )
    parser.add_argument(
        "--mock-detector",
        action="store_true",
        help="Force mock YOLO detector for synthetic testing"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Target frames per second"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Build Engine Configuration
    config = EngineConfig(
        video_source=args.source,
        target_fps=args.fps,
        headless=args.headless,
        detector=DetectorConfig(
            model_path=args.model,
            confidence_threshold=args.conf,
            use_mock=args.mock_detector
        ),
        tts=TTSConfig(
            mute_audio=args.mute
        ),
        visualizer=VisualizerConfig(
            show_window=not args.headless
        )
    )

    engine = TrinetraEngine(config=config)

    # Attach Built-in Pluggable Rules
    engine.register_navigation_rule(SensorFusionCollisionRule())
    engine.register_navigation_rule(PathClearanceRule())

    # Attach Mock Sensor if requested
    if args.mock_sensor:
        mock_ultrasonic = MockUltrasonicSensor(
            sensor_id="front_ultrasonic",
            target_zone=Zone.CENTER,
            simulate_approach=True,
            base_distance_cm=140.0
        )
        engine.register_sensor(mock_ultrasonic)

    print("==================================================================")
    print("                 TRINETRA VISION & NAVIGATION ENGINE               ")
    print("==================================================================")
    print(f" Source:           {config.video_source}")
    print(f" YOLO Model:       {config.detector.model_path}")
    print(f" Confidence:       {config.detector.confidence_threshold}")
    print(f" Audio Muted:      {config.tts.mute_audio}")
    print(f" Headless Mode:    {config.headless}")
    print(" Controls:         [q/ESC] Quit | [m] Toggle Mute | [d] Toggle HUD")
    print("==================================================================")

    engine.run()


if __name__ == "__main__":
    main()
