"""
Platform-agnostic types and primitives for TRINETRA v2 Core.
Zero OS-specific dependencies.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, IntEnum
import time
from typing import Any, Optional


class DeviceType(str, Enum):
    """Supported physical and container device categories."""
    DESKTOP_WORKSTATION = "desktop_workstation"
    ANDROID_PHONE = "android_phone"
    IOS_PHONE = "ios_phone"
    ESP32_CAM_WEARABLE = "esp32_cam_wearable"
    SMART_GLASSES_WEARABLE = "smart_glasses_wearable"
    GENERIC_EDGE = "generic_edge"


class AutonomyLevel(IntEnum):
    """
    Graded autonomy governance tiers:
    L0: Inform Only (explicit query only)
    L1: Suggest (proactively suggests, waits for confirmation)
    L2: Act after Confirmation (default)
    L3: Pre-Approved Routine Autonomy (reminders, step counting, auto-save bookmarks)
    L4: Emergency Action (audible 10s countdown, tamper-evident log, SMS dispatch)
    """
    L0_INFORM = 0
    L1_SUGGEST = 1
    L2_ACT_CONFIRMED = 2
    L3_ROUTINE_AUTO = 3
    L4_EMERGENCY = 4


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class Vector2D:
    dx: float
    dy: float

    @property
    def magnitude(self) -> float:
        return (self.dx ** 2 + self.dy ** 2) ** 0.5


@dataclass(frozen=True)
class BoundingBox:
    """
    Bounding box representation.
    Coordinates are normalized [0.0, 1.0] or absolute pixels depending on context.
    """
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def width(self) -> float:
        return max(0.0, self.xmax - self.xmin)

    @property
    def height(self) -> float:
        return max(0.0, self.ymax - self.ymin)

    @property
    def center_x(self) -> float:
        return (self.xmin + self.xmax) / 2.0

    @property
    def center_y(self) -> float:
        return (self.ymin + self.ymax) / 2.0

    @property
    def area(self) -> float:
        return self.width * self.height

    def iou(self, other: BoundingBox) -> float:
        """Compute Intersection-over-Union with another bounding box."""
        ixmin = max(self.xmin, other.xmin)
        iymin = max(self.ymin, other.ymin)
        ixmax = min(self.xmax, other.xmax)
        iymax = min(self.ymax, other.ymax)

        iw = max(0.0, ixmax - ixmin)
        ih = max(0.0, iymax - iymin)
        intersection = iw * ih

        union = self.area + other.area - intersection
        if union <= 0.0:
            return 0.0
        return intersection / union


@dataclass
class FrameMetadata:
    """Metadata attached to an ingested visual frame."""
    frame_id: int
    timestamp_utc: float = field(default_factory=time.time)
    source_device: DeviceType = DeviceType.DESKTOP_WORKSTATION
    width: int = 640
    height: int = 480
    is_mirrored: bool = False
    format: str = "RGB"
    dropped_frames: int = 0
    exposure_status: str = "normal"  # normal, low_light, overexposed, dark
    motion_blur_score: float = 0.0
