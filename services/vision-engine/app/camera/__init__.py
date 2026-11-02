"""
Trinetra Camera Package
"""
from app.camera.adapter import (
    CameraAdapter,
    CameraDeviceInfo,
    OpenCVCameraAdapter,
    FakeCameraAdapter,
    FramePacket,
    CameraError,
    CameraInitializationError,
    CameraBusyError,
    CameraNotFoundError,
    CameraPermissionError,
    CameraNotActiveError,
    FrameCaptureError,
)

__all__ = [
    "CameraAdapter",
    "CameraDeviceInfo",
    "OpenCVCameraAdapter",
    "FakeCameraAdapter",
    "FramePacket",
    "CameraError",
    "CameraInitializationError",
    "CameraBusyError",
    "CameraNotFoundError",
    "CameraPermissionError",
    "CameraNotActiveError",
    "FrameCaptureError",
]
