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


def classify_sector(
    box_or_xmin: Any,
    x_max: Optional[float] = None,
    current_sector: Optional[str] = None,
    hysteresis: float = 0.04
) -> str:
    """
    Partitions the 2D field of view into three horizontal directional sectors
    with hysteresis to eliminate boundary flicker on moving pedestrian hazards:
    - Left: center_x in [0.0, 0.33)
    - Center: center_x in [0.33, 0.66]
    - Right: center_x in (0.66, 1.0]
    When current_sector is provided, a +/- hysteresis deadband is applied to prevent
    rapid Left <-> Center <-> Right oscillation.
    Supports passing a BoundingBox instance or (x_min, x_max) scalar bounds.
    """
    if x_max is not None:
        cx = (float(box_or_xmin) + float(x_max)) / 2.0
    elif hasattr(box_or_xmin, "center_x"):
        cx = box_or_xmin.center_x
    else:
        cx = 0.5

    # Apply deadband hysteresis if an active sector track is provided
    if current_sector == "left":
        return "left" if cx < (0.33 + hysteresis) else "center"
    elif current_sector == "right":
        return "right" if cx > (0.66 - hysteresis) else "center"
    elif current_sector == "center":
        if cx < (0.33 - hysteresis):
            return "left"
        elif cx > (0.66 + hysteresis):
            return "right"
        return "center"

    # Default initial classification without prior state
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
    distance_m: Optional[float] = None


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
