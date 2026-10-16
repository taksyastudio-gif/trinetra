"""
Trinetra Camera Adapter Abstraction & Implementations
Decouples camera hardware access from the web API.
"""

from abc import ABC, abstractmethod
import io
import logging
import struct
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("trinetra.camera")


class CameraError(Exception):
    """Base exception for camera-related failures."""
    pass


class CameraInitializationError(CameraError):
    """Raised when camera hardware cannot be opened or initialized."""
    pass


class CameraNotActiveError(CameraError):
    """Raised when an operation requires an active camera but none is running."""
    pass


class CameraAdapter(ABC):
    """
    Abstract Base Class defining the contract for camera drivers.
    All camera integrations (OpenCV, CSI, RealSense, Fake) must implement this interface.
    """

    @abstractmethod
    def start(self) -> None:
        """Initializes and claims the camera hardware resource."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Releases the camera hardware resource safely."""
        pass

    @abstractmethod
    def is_active(self) -> bool:
        """Returns True if the camera is currently opened and active."""
        pass

    @abstractmethod
    def capture_jpeg(self) -> bytes:
        """
        Captures a single frame from the camera and returns it encoded as JPEG bytes.
        Must NOT write frames to disk.
        """
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns structured metadata about the camera state."""
        pass


class OpenCVCameraAdapter(CameraAdapter):
    """
    Standard camera adapter utilizing OpenCV (cv2.VideoCapture).
    Suitable for laptop webcams and USB video devices on Windows, Linux, and macOS.
    """

    def __init__(self, camera_index: int = 0, width: int = 640, height: int = 480, jpeg_quality: int = 85):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.jpeg_quality = jpeg_quality
        self._cap: Any = None
        self._lock = threading.Lock()
        self._active = False
        self._frames_captured = 0
        self._start_time: Optional[float] = None

    def start(self) -> None:
        with self._lock:
            if self._active:
                logger.info("OpenCV camera already active.")
                return

            try:
                import cv2
            except ImportError:
                raise CameraInitializationError(
                    "OpenCV library (opencv-python) is not installed in the environment."
                )

            logger.info(f"Attempting to open camera index {self.camera_index}...")

            # Attempt DirectShow backend first on Windows for faster initialization, fallback to default
            cap = None
            try:
                cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            except Exception:
                cap = None

            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(self.camera_index)

            if not cap.isOpened():
                if cap is not None:
                    cap.release()
                raise CameraInitializationError(
                    f"Could not open webcam at index {self.camera_index}. "
                    "Ensure the camera is connected, permissions are enabled, and no other app is using it."
                )

            # Set desired capture properties
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            self._cap = cap
            self._active = True
            self._frames_captured = 0
            self._start_time = time.time()
            logger.info(f"OpenCV camera index {self.camera_index} successfully opened.")

    def stop(self) -> None:
        with self._lock:
            if not self._active:
                return

            logger.info(f"Releasing camera index {self.camera_index}...")
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception as exc:
                    logger.warning(f"Error while releasing OpenCV VideoCapture: {exc}")
                self._cap = None

            self._active = False
            self._start_time = None
            logger.info(f"Camera index {self.camera_index} released.")

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def capture_jpeg(self) -> bytes:
        with self._lock:
            if not self._active or self._cap is None:
                raise CameraNotActiveError("Camera is not active. Call start() before requesting frames.")

            ret, frame = self._cap.read()
            if not ret or frame is None:
                raise CameraError("Failed to grab video frame from camera stream.")

            import cv2
            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            success, encoded_img = cv2.imencode(".jpg", frame, encode_params)
            if not success or encoded_img is None:
                raise CameraError("Failed to encode frame as JPEG buffer.")

            self._frames_captured += 1
            return encoded_img.tobytes()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            uptime = time.time() - self._start_time if self._start_time else 0.0
            return {
                "active": self._active,
                "adapter": "OpenCVCameraAdapter",
                "camera_index": self.camera_index,
                "resolution": f"{self.width}x{self.height}",
                "frames_captured": self._frames_captured,
                "uptime_seconds": round(uptime, 1)
            }


class FakeCameraAdapter(CameraAdapter):
    """
    Predictable mock camera adapter for automated testing and CI/CD pipelines.
    Generates genuine JPEG frames purely in memory without OpenCV or hardware dependencies.
    """

    def __init__(
        self,
        width: int = 320,
        height: int = 240,
        should_fail_init: bool = False,
        should_fail_capture: bool = False
    ):
        self.width = width
        self.height = height
        self.should_fail_init = should_fail_init
        self.should_fail_capture = should_fail_capture
        self._active = False
        self._lock = threading.Lock()
        self._frames_captured = 0
        self._start_time: Optional[float] = None

    def start(self) -> None:
        with self._lock:
            if self._active:
                return

            if self.should_fail_init:
                raise CameraInitializationError("Simulated camera hardware initialization failure.")

            self._active = True
            self._frames_captured = 0
            self._start_time = time.time()
            logger.info("FakeCameraAdapter started.")

    def stop(self) -> None:
        with self._lock:
            self._active = False
            self._start_time = None
            logger.info("FakeCameraAdapter stopped.")

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def capture_jpeg(self) -> bytes:
        with self._lock:
            if not self._active:
                raise CameraNotActiveError("Camera is not active. Call start() before requesting frames.")

            if self.should_fail_capture:
                raise CameraError("Simulated frame capture failure.")

            self._frames_captured += 1
            # Generate a valid, minimal, pure-Python in-memory JPEG frame
            return self._generate_test_jpeg()

    def _generate_test_jpeg(self) -> bytes:
        """
        Generates a valid minimal baseline JPEG image entirely in pure Python
        without any external binary dependencies.
        A standard 1x1 or patterned JPEG byte array with valid SOI, DQT, SOF, DHT, SOS, EOI markers.
        """
        # Minimal valid 1x1 neutral gray JPEG image
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
            b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
            b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
            b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x80\xff\xd9"
        )

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            uptime = time.time() - self._start_time if self._start_time else 0.0
            return {
                "active": self._active,
                "adapter": "FakeCameraAdapter",
                "resolution": f"{self.width}x{self.height}",
                "frames_captured": self._frames_captured,
                "uptime_seconds": round(uptime, 1)
            }
