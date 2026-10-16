"""
TRINETRA OpenCV Debug Visualizer
Renders high-contrast visual HUD, spatial zone boundaries, color-coded obstacle
bounding boxes, and real-time audio announcement logs.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from config import VisualizerConfig
from core.spatial import Proximity, Zone
from plugins.base import SensorReading

logger = logging.getLogger("TRINETRA.Visualizer")

# Color palette (BGR format for OpenCV)
COLOR_CRITICAL = (30, 30, 230)     # Vibrant Red (Urgent / Immediate collision)
COLOR_WARNING = (20, 160, 240)     # Amber / Orange (Approaching)
COLOR_SAFE = (60, 200, 60)         # Green (Distant / Low threat)
COLOR_ZONE_LINE = (180, 180, 180)  # Semi-translucent Gray/White
COLOR_HUD_BG = (25, 25, 25)        # Dark Charcoal HUD background
COLOR_TEXT_WHITE = (245, 245, 245)
COLOR_TEXT_YELLOW = (50, 220, 255)
COLOR_ACCENT = (255, 120, 0)       # Cyan/Blue


class DebugVisualizer:
    """
    Renders an assistive debug view over the ingested video frame.
    """

    def __init__(self, config: VisualizerConfig, left_boundary: float = 0.35, right_boundary: float = 0.65):
        self.config = config
        self.left_boundary = left_boundary
        self.right_boundary = right_boundary
        self._cv2 = None
        self._init_opencv()

    def _init_opencv(self) -> None:
        """Loads cv2 dynamically and creates window if display is available."""
        try:
            import cv2
            self._cv2 = cv2
            if self.config.show_window:
                try:
                    cv2.namedWindow(self.config.window_name, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(self.config.window_name, self.config.window_size[0], self.config.window_size[1])
                except Exception as exc:
                    logger.debug(f"Headless display detected or window creation skipped: {exc}")
        except ImportError:
            logger.warning("OpenCV (cv2) not available. Visual window disabled.")

    def render(
        self,
        frame: Any,
        detections: List[Any],
        fps: float,
        sensor_readings: Dict[str, SensorReading],
        current_speech: Optional[str] = None,
        recent_speech_list: Optional[List[Tuple[float, str, int]]] = None,
        is_muted: bool = False
    ) -> Any:
        """
        Draws visual overlays onto the frame.

        Args:
            frame: OpenCV BGR image (numpy ndarray).
            detections: List of Detection objects.
            fps: Current frames-per-second measurement.
            sensor_readings: Current hardware sensor telemetry.
            current_speech: Text currently being spoken.
            recent_speech_list: List of recently spoken announcements.
            is_muted: Whether TTS is currently muted.

        Returns:
            Annotated frame.
        """
        if self._cv2 is None or frame is None or not hasattr(frame, "shape"):
            return frame

        cv2 = self._cv2
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        left_x = int(w * self.left_boundary)
        right_x = int(w * self.right_boundary)

        # 1. Draw Spatial Zone Boundaries
        if self.config.show_zones:
            # Vertical dashed/translucent boundary lines
            cv2.line(annotated, (left_x, 40), (left_x, h - 30), COLOR_ZONE_LINE, 1, cv2.LINE_AA)
            cv2.line(annotated, (right_x, 40), (right_x, h - 30), COLOR_ZONE_LINE, 1, cv2.LINE_AA)

            # Zone Labels at bottom of screen
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(annotated, "LEFT ZONE", (int(left_x * 0.25), h - 12), font, 0.45, (160, 160, 160), 1, cv2.LINE_AA)
            cv2.putText(annotated, "[ STRAIGHT AHEAD ]", (int(left_x + (right_x - left_x) * 0.2), h - 12), font, 0.5, (0, 220, 255), 2, cv2.LINE_AA)
            cv2.putText(annotated, "RIGHT ZONE", (int(right_x + (w - right_x) * 0.25), h - 12), font, 0.45, (160, 160, 160), 1, cv2.LINE_AA)

        # 2. Draw Obstacle Bounding Boxes
        if self.config.show_bboxes:
            for det in detections:
                x1, y1, x2, y2 = det.bbox

                # Choose color by proximity/urgency
                if det.spatial.proximity == Proximity.IMMEDIATE:
                    color = COLOR_CRITICAL
                    thickness = 3
                elif det.spatial.proximity == Proximity.APPROACHING:
                    color = COLOR_WARNING
                    thickness = 2
                else:
                    color = COLOR_SAFE
                    thickness = 1

                # Draw box
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thickness)

                # Label text
                label_text = f"{det.label.upper()} ({int(det.confidence * 100)}%)"
                sub_text = f"{det.spatial.zone.value} | ~{det.spatial.estimated_distance_m}m"

                # Text background banner
                (tw1, th1), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                cv2.rectangle(annotated, (x1, max(0, y1 - 24)), (x1 + max(tw1 + 10, 130), y1), color, -1)
                cv2.putText(annotated, label_text, (x1 + 4, max(12, y1 - 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
                cv2.putText(annotated, sub_text, (x1 + 4, max(22, y1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1, cv2.LINE_AA)

        # 3. Top HUD Status Bar
        if self.config.show_hud:
            # Draw translucent top bar
            hud_height = 36
            overlay = annotated.copy()
            cv2.rectangle(overlay, (0, 0), (w, hud_height), COLOR_HUD_BG, -1)
            cv2.addWeighted(overlay, 0.8, annotated, 0.2, 0, annotated)

            # Left: App Brand & FPS
            cv2.putText(
                annotated,
                f"TRINETRA AI ENGINE | FPS: {fps:.1f}",
                (12, 23),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                COLOR_TEXT_YELLOW,
                2,
                cv2.LINE_AA
            )

            # Center: Sensor Readings Summary
            sensor_texts = []
            for s_id, s_reading in sensor_readings.items():
                if s_reading.distance_cm is not None:
                    sensor_texts.append(f"{s_id}: {int(s_reading.distance_cm)}cm")
            sensor_summary = " | ".join(sensor_texts) if sensor_texts else "Sensors: OK"
            cv2.putText(
                annotated,
                sensor_summary,
                (int(w * 0.42), 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (200, 200, 200),
                1,
                cv2.LINE_AA
            )

            # Right: Audio Mute Status
            audio_status = "MUTED" if is_muted else "AUDIO: ON"
            audio_color = (0, 0, 255) if is_muted else (0, 255, 120)
            cv2.putText(
                annotated,
                audio_status,
                (w - 110, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                audio_color,
                1,
                cv2.LINE_AA
            )

        # 4. Active Speech Bubble / Subtitle
        if current_speech:
            bubble_y = h - 45
            overlay = annotated.copy()
            cv2.rectangle(overlay, (20, bubble_y - 20), (w - 20, bubble_y + 10), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.75, annotated, 0.25, 0, annotated)
            cv2.putText(
                annotated,
                f"SPEECH: \"{current_speech}\"",
                (30, bubble_y - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (50, 255, 50),
                2,
                cv2.LINE_AA
            )

        return annotated

    def show(self, frame: Any) -> int:
        """
        Displays frame in OpenCV window and polls keyboard inputs.

        Returns:
            Key code pressed by user (or -1 if no key).
        """
        if self._cv2 is None or not self.config.show_window:
            return -1

        try:
            self._cv2.imshow(self.config.window_name, frame)
            return self._cv2.waitKey(1) & 0xFF
        except Exception:
            return -1

    def close(self) -> None:
        """Closes OpenCV windows."""
        if self._cv2 is not None:
            try:
                self._cv2.destroyAllWindows()
            except Exception:
                pass
