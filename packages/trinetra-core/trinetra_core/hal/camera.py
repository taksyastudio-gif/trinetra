"""
Camera Hardware Abstraction Layer (HAL) Interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
from trinetra_core.types import FrameMetadata


class CameraAdapterInterface(ABC):
    """
    Abstract interface for all visual ingestion sources.
    Supported concrete adapters:
    - DirectShow (Windows laptop / USB cam)
    - CameraX / WebRTC (Android / Mobile PWA)
    - MJPEGStreamCameraAdapter (ESP32-CAM / IP Camera)
    - MockCameraAdapter (Synthetic testing)
    """

    @abstractmethod
    def open(self, source_index_or_url: Any = 0) -> bool:
        """Initialize and open the video stream."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Release underlying camera resources."""
        pass

    @abstractmethod
    def read_frame(self) -> Tuple[bool, Optional[Any], Optional[FrameMetadata]]:
        """
        Capture the most recent frame.
        Returns: (success, frame_buffer, frame_metadata)
        Frame buffer is typically a numpy ndarray (H, W, 3) BGR/RGB or raw bytearray.
        """
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Check whether camera device is alive and streaming without stall."""
        pass

    @abstractmethod
    def get_telemetry(self) -> Dict[str, Any]:
        """Return frame rate, dropped frame count, resolution, and exposure status."""
        pass
