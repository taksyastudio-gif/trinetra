"""
Trinetra Core Detection Data Types & Spatial Partitioning
Contains primitive dataclasses and geometric helpers for bounding boxes, sectors, and detections.
"""

from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass(frozen=True)
class BoundingBox:
    """Normalized coordinates [0.0, 1.0] representing object location in frame."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.x_max - self.x_min) * max(0.0, self.y_max - self.y_min)


def classify_sector(box: BoundingBox) -> str:
    """
    Partitions the 2D field of view into three horizontal directional sectors:
    - Left: center_x in [0.0, 0.33)
    - Center: center_x in [0.33, 0.66]
    - Right: center_x in (0.66, 1.0]
    """
    cx = box.center_x
    if cx < 0.33:
        return "left"
    elif cx > 0.66:
        return "right"
    return "center"


@dataclass(frozen=True)
class Detection:
    """Represents a single classified object instance within a video frame."""
    class_name: str
    confidence: float
    box: BoundingBox
    sector: str  # "left", "center", "right"


@dataclass(frozen=True)
class DetectionResult:
    """Container holding inference output for a specific frame sequence."""
    frame_id: int
    timestamp: float
    detections: List[Detection]
    inference_time_ms: float
    model_name: str
    e2e_latency_ms: float = 0.0
    ground_hazard: Optional[Any] = None
    overhead_wire: Optional[Any] = None
    auto_currency: Optional[Any] = None
    sign_gesture: Optional[Any] = None
