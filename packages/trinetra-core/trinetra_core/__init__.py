"""
TRINETRA Core Package (trinetra_core)
v2.0 Platform-Agnostic Core Runtime & Hardware Abstraction Layer
"""

__version__ = "0.2.0"

from trinetra_core.types import (
    BoundingBox,
    Point2D,
    Vector2D,
    DeviceType,
    AutonomyLevel,
    FrameMetadata,
)

__all__ = [
    "__version__",
    "BoundingBox",
    "Point2D",
    "Vector2D",
    "DeviceType",
    "AutonomyLevel",
    "FrameMetadata",
]
