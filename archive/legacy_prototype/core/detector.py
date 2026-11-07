"""
TRINETRA Object Detection Engine
Performs edge object detection using Ultralytics YOLOv8, integrated with
spatial position analysis and distance estimation.
"""

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from config import DetectorConfig
from core.spatial import SpatialAnalyzer, SpatialAssessment

logger = logging.getLogger("TRINETRA.Detector")


@dataclass
class Detection:
    """Standardized representation of an object detected in a frame."""
    class_id: int
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    spatial: SpatialAssessment
    track_id: Optional[int] = None

    @property
    def alert_key(self) -> str:
        """Unique key for deduplication and cooldown tracking."""
        return f"{self.label.lower()}:{self.spatial.zone.value}:{self.spatial.proximity.value}"


class ObjectDetector:
    """
    YOLOv8 Edge Object Detector with spatial mapping and graceful fallback.
    """

    def __init__(self, config: DetectorConfig, spatial_analyzer: SpatialAnalyzer):
        self.config = config
        self.spatial_analyzer = spatial_analyzer
        self.model = None
        self._is_mock = self.config.use_mock
        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initializes YOLOv8 model or switches to mock detector if unavailable."""
        if self._is_mock:
            logger.info("Operating in Mock Detector mode (configured).")
            return

        try:
            from ultralytics import YOLO
            logger.info(f"Loading YOLOv8 model from '{self.config.model_path}' on device '{self.config.device}'...")
            self.model = YOLO(self.config.model_path)
            logger.info("YOLOv8 model loaded successfully.")
        except ImportError:
            logger.warning(
                "Ultralytics package not found. Falling back to Mock Detector mode for headless/test simulation."
            )
            self._is_mock = True
        except Exception as exc:
            logger.warning(
                f"Failed to load YOLO model from '{self.config.model_path}': {exc}. Using Mock Detector mode."
            )
            self._is_mock = True

    def detect(self, frame: Any) -> List[Detection]:
        """
        Runs object detection on a single video frame.

        Args:
            frame: OpenCV BGR image (numpy ndarray) or mock frame structure.

        Returns:
            List of Detection objects enriched with spatial assessments.
        """
        # Determine frame dimensions
        if hasattr(frame, "shape"):
            frame_h, frame_w = frame.shape[:2]
        else:
            frame_w, frame_h = 640, 480

        if self._is_mock or self.model is None:
            return self._mock_detect(frame_w, frame_h)

        detections: List[Detection] = []

        try:
            # Run inference
            results = self.model(
                frame,
                conf=self.config.confidence_threshold,
                iou=self.config.iou_threshold,
                device=self.config.device,
                verbose=False
            )

            if not results:
                return []

            result = results[0]
            boxes = result.boxes

            if boxes is None or len(boxes) == 0:
                return []

            for i in range(len(boxes)):
                box = boxes[i]
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                label = result.names.get(cls_id, f"obj_{cls_id}").lower()

                # Filter target navigation classes if specified
                if self.config.navigation_classes and label not in self.config.navigation_classes:
                    continue

                coords = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = coords[0], coords[1], coords[2], coords[3]
                bbox = (int(x1), int(y1), int(x2), int(y2))

                spatial_data = self.spatial_analyzer.calculate_spatial_position(
                    bbox=bbox,
                    frame_width=frame_w,
                    frame_height=frame_h,
                    label=label
                )

                detections.append(Detection(
                    class_id=cls_id,
                    label=label,
                    confidence=conf,
                    bbox=bbox,
                    spatial=spatial_data
                ))

        except Exception as exc:
            logger.error(f"Inference error: {exc}")

        return detections

    def _mock_detect(self, frame_w: int, frame_h: int) -> List[Detection]:
        """
        Generates simulated realistic obstacle detections for testing/headless execution.
        """
        # Example: chair in center close, person on left approaching
        sample_boxes = [
            # (label, conf, x1, y1, x2, y2)
            ("chair", 0.88, int(frame_w * 0.38), int(frame_h * 0.45), int(frame_w * 0.62), int(frame_h * 0.92)),
            ("person", 0.76, int(frame_w * 0.05), int(frame_h * 0.25), int(frame_w * 0.28), int(frame_h * 0.65))
        ]

        detections = []
        for cls_id, (label, conf, x1, y1, x2, y2) in enumerate(sample_boxes):
            bbox = (x1, y1, x2, y2)
            spatial_data = self.spatial_analyzer.calculate_spatial_position(
                bbox=bbox,
                frame_width=frame_w,
                frame_height=frame_h,
                label=label
            )
            detections.append(Detection(
                class_id=cls_id,
                label=label,
                confidence=conf,
                bbox=bbox,
                spatial=spatial_data
            ))

        return detections
