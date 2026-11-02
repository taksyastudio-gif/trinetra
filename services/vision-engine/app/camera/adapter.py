"""
Trinetra Camera Adapter Abstraction & Implementations
Decouples camera hardware access from the web API.
Incorporates capacity-1 bounded latest-frame buffer and monotonic frame sequence tracking.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import logging
import math
import threading
import time
from typing import Any, Dict, Optional, Tuple, Union
import uuid

logger = logging.getLogger("trinetra.camera")


# =============================================================================
# Typed Error Hierarchy & Connection States
# =============================================================================

class CameraConnectionState(str, Enum):
    """Lifecycle operational state of the camera hardware connection."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class CameraError(Exception):
    """Base exception for all camera-related failures."""
    code: str = "camera_error"


class CameraInitializationError(CameraError):
    """Raised when camera hardware cannot be opened or claimed."""
    code: str = "initialization_failed"


class CameraBusyError(CameraInitializationError):
    """Raised when the camera device is locked by another operating system process."""
    code: str = "device_busy"


class CameraNotFoundError(CameraInitializationError):
    """Raised when the requested camera index or device does not exist."""
    code: str = "device_missing"


class CameraPermissionError(CameraInitializationError):
    """Raised when operating system camera permissions are denied."""
    code: str = "permission_denied"


class CameraNotActiveError(CameraError):
    """Raised when an operation requires an active camera session but none is running."""
    code: str = "camera_not_active"


class FrameCaptureError(CameraError):
    """Raised when frame capture or encoding stalls or produces invalid output."""
    code: str = "frame_capture_failed"


class CameraReconnectingError(CameraError):
    """Raised when camera connection dropped and automatic bounded reconnection is in progress."""
    code: str = "camera_reconnecting"

    def __init__(self, attempt: int, max_attempts: int, retry_after: float, message: Optional[str] = None):
        self.attempt = attempt
        self.max_attempts = max_attempts
        self.retry_after = retry_after
        msg = message or f"Camera disconnected. Reconnection attempt {attempt}/{max_attempts} in progress. Retry in {retry_after:.1f}s."
        super().__init__(msg)


class CameraConnectionExhaustedError(CameraError):
    """Raised when maximum reconnection attempts have been exceeded without success."""
    code: str = "camera_reconnection_exhausted"

    def __init__(self, total_attempts: int, message: Optional[str] = None):
        self.total_attempts = total_attempts
        msg = message or f"Camera reconnection exhausted after {total_attempts} attempts. Manual intervention required."
        super().__init__(msg)


# =============================================================================
# Value Shapes & Frame Containers
# =============================================================================

@dataclass(frozen=True)
class FramePacket:
    """
    Immutable container representing a single captured frame and its telemetry.
    Strictly kept in volatile memory; never persisted to disk.
    """
    frame_id: int               # Monotonically increasing sequence number
    captured_at: float          # Monotonic timestamp of acquisition
    jpeg_bytes: bytes           # In-memory JPEG encoded byte stream
    width: int                  # Frame width in pixels
    height: int                 # Frame height in pixels
    source_id: str              # Identifier of originating camera adapter
    dropped_frames: int = 0     # Overwritten/dropped frames since session start
    session_id: str = ""        # Camera session generation identifier


@dataclass(frozen=True)
class CameraDeviceInfo:
    """Metadata describing a discoverable camera device."""
    index: int
    name: str
    is_available: bool
    status: str  # "available", "in_use", "busy", "disconnected", "error"


# =============================================================================
# Camera Adapter Interface
# =============================================================================

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
    def capture_packet(self) -> FramePacket:
        """
        Captures a single frame from the camera and returns a FramePacket with metadata.
        Must NOT write frames to disk.
        """
        pass

    def capture_jpeg(self) -> bytes:
        """
        Convenience method returning raw JPEG bytes.
        """
        return self.capture_packet().jpeg_bytes

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns structured metadata about the camera state."""
        pass

    @abstractmethod
    def enumerate_devices(self) -> list[CameraDeviceInfo]:
        """Discovers available camera devices on the host system."""
        pass


# =============================================================================
# OpenCV Camera Adapter
# =============================================================================

class OpenCVCameraAdapter(CameraAdapter):
    """
    Authoritative single-owner camera adapter utilizing OpenCV (cv2.VideoCapture).
    Maintains a capacity-1 bounded latest-frame buffer to prevent stale frame queuing.
    Suitable for laptop webcams and USB video devices on Windows, Linux, and macOS.
    """

    def __init__(
        self,
        camera_index: Union[int, str] = 0,
        width: int = 640,
        height: int = 480,
        jpeg_quality: int = 85
    ):
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.jpeg_quality = jpeg_quality

        self._cap: Any = None
        self._lock = threading.Lock()
        self._active = False
        self._connection_state: CameraConnectionState = CameraConnectionState.DISCONNECTED
        self._reconnect_attempts: int = 0
        self.max_reconnect_attempts: int = 5
        self.initial_backoff: float = 0.5
        self.backoff_multiplier: float = 2.0
        self.max_backoff: float = 4.0
        self._next_reconnect_time: float = 0.0
        self._last_error: Optional[str] = None
        self._frame_seq = 0
        self._dropped_frames = 0
        self._session_id: str = ""
        self._start_time: Optional[float] = None
        self._last_read_time: Optional[float] = None

    def start(self) -> None:
        with self._lock:
            if self._active:
                logger.info("OpenCV camera already active.")
                return

            self._connection_state = CameraConnectionState.CONNECTING
            try:
                import cv2
            except ImportError:
                self._connection_state = CameraConnectionState.ERROR
                self._last_error = "OpenCV library (opencv-python) is not installed."
                raise CameraInitializationError(
                    "OpenCV library (opencv-python) is not installed in the environment."
                )

            logger.info(f"Attempting to open camera source {self.camera_index}...")

            cap = None
            if isinstance(self.camera_index, int):
                # Attempt DirectShow backend first on Windows for faster initialization, fallback to default
                try:
                    cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                except Exception:
                    cap = None

                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self.camera_index)
            else:
                # String URL (e.g., http://... or rtsp://... for ESP32-CAM / IP Camera)
                cap = cv2.VideoCapture(self.camera_index)

            if not cap.isOpened():
                if cap is not None:
                    cap.release()
                self._connection_state = CameraConnectionState.ERROR
                self._last_error = f"Could not open camera at {self.camera_index}."
                raise CameraBusyError(
                    f"Could not open camera at {self.camera_index}. "
                    "Ensure the camera is connected, Windows permissions are granted, "
                    "or the network stream URL is accessible."
                )

            # Set desired capture properties
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            self._cap = cap
            self._active = True
            self._connection_state = CameraConnectionState.CONNECTED
            self._reconnect_attempts = 0
            self._last_error = None
            self._frame_seq = 0
            self._dropped_frames = 0
            self._session_id = uuid.uuid4().hex
            self._start_time = time.time()
            self._last_read_time = None
            logger.info(f"OpenCV camera source {self.camera_index} successfully opened.")

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
            self._connection_state = CameraConnectionState.DISCONNECTED
            self._reconnect_attempts = 0
            self._next_reconnect_time = 0.0
            self._last_error = None
            self._session_id = ""
            self._start_time = None
            self._last_read_time = None
            logger.info(f"Camera index {self.camera_index} released.")

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def _attempt_reconnect(self) -> bool:
        """Attempts to reinitialize the VideoCapture resource after disconnection."""
        try:
            import cv2
            cap = None
            if isinstance(self.camera_index, int):
                try:
                    cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                except Exception:
                    cap = None

                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self.camera_index)
            else:
                cap = cv2.VideoCapture(self.camera_index)

            if cap is not None and cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self._cap = cap
                return True

            if cap is not None:
                cap.release()
            return False
        except Exception as exc:
            logger.warning(f"Reconnection attempt failed on source {self.camera_index}: {exc}")
            return False

    def capture_packet(self) -> FramePacket:
        with self._lock:
            if not self._active:
                raise CameraNotActiveError("Camera is not active. Call start() before requesting frames.")

            now = time.time()

            # If currently in error / exhausted state
            if self._connection_state == CameraConnectionState.ERROR:
                raise CameraConnectionExhaustedError(
                    self.max_reconnect_attempts,
                    self._last_error or f"Camera reconnection exhausted after {self.max_reconnect_attempts} attempts."
                )

            # If in RECONNECTING state, enforce backoff and attempt recovery
            if self._connection_state == CameraConnectionState.RECONNECTING:
                if now < self._next_reconnect_time:
                    retry_after = max(0.1, self._next_reconnect_time - now)
                    raise CameraReconnectingError(self._reconnect_attempts, self.max_reconnect_attempts, retry_after)

                # Time to attempt reconnection
                reconnected = self._attempt_reconnect()
                if reconnected:
                    self._connection_state = CameraConnectionState.CONNECTED
                    self._reconnect_attempts = 0
                    self._last_error = None
                    logger.info(f"Camera index {self.camera_index} successfully reconnected.")
                else:
                    self._reconnect_attempts += 1
                    if self._reconnect_attempts > self.max_reconnect_attempts:
                        self._connection_state = CameraConnectionState.ERROR
                        self._last_error = f"Reconnection exhausted after {self.max_reconnect_attempts} attempts."
                        raise CameraConnectionExhaustedError(self.max_reconnect_attempts)
                    backoff = min(self.max_backoff, self.initial_backoff * (self.backoff_multiplier ** (self._reconnect_attempts - 1)))
                    self._next_reconnect_time = now + backoff
                    raise CameraReconnectingError(self._reconnect_attempts, self.max_reconnect_attempts, backoff)

            if self._cap is None:
                raise CameraNotActiveError("Camera hardware handle is None.")

            ret, frame = self._cap.read()
            now = time.time()

            if not ret or frame is None:
                logger.warning(f"Failed to grab video frame from camera stream (index {self.camera_index}). Transitioning to RECONNECTING.")
                if self._cap is not None:
                    try:
                        self._cap.release()
                    except Exception:
                        pass
                    self._cap = None

                self._connection_state = CameraConnectionState.RECONNECTING
                self._reconnect_attempts = 1
                backoff = self.initial_backoff
                self._next_reconnect_time = now + backoff
                self._last_error = "Frame grab failed: device disconnected or read timeout."
                raise CameraReconnectingError(self._reconnect_attempts, self.max_reconnect_attempts, backoff)

            import cv2
            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            success, encoded_img = cv2.imencode(".jpg", frame, encode_params)
            if not success or encoded_img is None:
                raise FrameCaptureError("Failed to encode frame as JPEG buffer.")

            self._frame_seq += 1
            self._last_read_time = now

            h, w = frame.shape[:2]
            return FramePacket(
                frame_id=self._frame_seq,
                captured_at=now,
                jpeg_bytes=encoded_img.tobytes(),
                width=w,
                height=h,
                source_id=f"opencv:{self.camera_index}",
                dropped_frames=self._dropped_frames,
                session_id=self._session_id
            )

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            uptime = time.time() - self._start_time if self._start_time else 0.0
            source_type = "network_stream" if isinstance(self.camera_index, str) else "usb_directshow"
            return {
                "active": self._active,
                "adapter": "OpenCVCameraAdapter",
                "source_type": source_type,
                "camera_index": self.camera_index,
                "resolution": f"{self.width}x{self.height}",
                "frames_captured": self._frame_seq,
                "dropped_frames": self._dropped_frames,
                "uptime_seconds": round(uptime, 1),
                "session_id": self._session_id,
                "connection_state": self._connection_state.value,
                "reconnect_attempts": self._reconnect_attempts,
                "max_reconnect_attempts": self.max_reconnect_attempts,
                "last_error": self._last_error
            }

    def enumerate_devices(self, max_devices_to_probe: int = 4) -> list[CameraDeviceInfo]:
        """
        Discovers available video capture devices on Windows.
        Probes indices 0..max_devices_to_probe-1 safely using DirectShow.
        """
        devices: list[CameraDeviceInfo] = []
        try:
            import cv2
        except ImportError:
            return devices

        for idx in range(max_devices_to_probe):
            with self._lock:
                if self._active and idx == self.camera_index:
                    devices.append(
                        CameraDeviceInfo(
                            index=idx,
                            name=f"Camera {idx} (Active)",
                            is_available=True,
                            status="in_use"
                        )
                    )
                    continue

            cap = None
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    devices.append(
                        CameraDeviceInfo(
                            index=idx,
                            name=f"Camera {idx}",
                            is_available=True,
                            status="available"
                        )
                    )
                    cap.release()
                else:
                    if cap is not None:
                        cap.release()
                    devices.append(
                        CameraDeviceInfo(
                            index=idx,
                            name=f"Camera {idx}",
                            is_available=False,
                            status="disconnected"
                        )
                    )
            except Exception as exc:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                devices.append(
                    CameraDeviceInfo(
                        index=idx,
                        name=f"Camera {idx}",
                        is_available=False,
                        status=f"error: {exc}"
                    )
                )
        return devices


# =============================================================================
# Fake Camera Adapter (For Automated Testing)
# =============================================================================

class FakeCameraAdapter(CameraAdapter):
    """
    Predictable mock camera adapter for automated testing and CI/CD pipelines.
    Generates genuine JPEG frames purely in memory without OpenCV or hardware dependencies.
    Supports capacity-1 bounded latest-frame sequencing and simulated fault injection.
    """

    def __init__(
        self,
        width: int = 320,
        height: int = 240,
        should_fail_init: bool = False,
        should_fail_capture: bool = False,
        devices: Optional[list[CameraDeviceInfo]] = None
    ):
        self.width = width
        self.height = height
        self.should_fail_init = should_fail_init
        self.should_fail_capture = should_fail_capture
        self._devices = devices if devices is not None else [
            CameraDeviceInfo(index=0, name="Simulated Built-in Camera", is_available=True, status="available"),
            CameraDeviceInfo(index=1, name="Simulated External USB Camera", is_available=True, status="available"),
        ]

        self._active = False
        self._lock = threading.Lock()
        self._connection_state: CameraConnectionState = CameraConnectionState.DISCONNECTED
        self._reconnect_attempts: int = 0
        self.max_reconnect_attempts: int = 5
        self.initial_backoff: float = 0.5
        self.backoff_multiplier: float = 2.0
        self.max_backoff: float = 4.0
        self._next_reconnect_time: float = 0.0
        self._last_error: Optional[str] = None
        self._simulate_transient_failures: int = 0
        self._simulate_permanent_disconnection: bool = False
        self._frame_seq = 0
        self._dropped_frames = 0
        self._session_id: str = ""
        self._start_time: Optional[float] = None
        self._latest_packet: Optional[FramePacket] = None

    def enumerate_devices(self) -> list[CameraDeviceInfo]:
        with self._lock:
            result = []
            for d in self._devices:
                if self._active and d.index == 0:
                    result.append(
                        CameraDeviceInfo(
                            index=d.index,
                            name=f"{d.name} (Active)",
                            is_available=True,
                            status="in_use"
                        )
                    )
                else:
                    result.append(d)
            return result

    def start(self) -> None:
        with self._lock:
            if self._active:
                return

            if self.should_fail_init:
                self._connection_state = CameraConnectionState.ERROR
                self._last_error = "Simulated camera hardware initialization failure."
                raise CameraInitializationError("Simulated camera hardware initialization failure.")

            self._active = True
            self._connection_state = CameraConnectionState.CONNECTED
            self._reconnect_attempts = 0
            self._next_reconnect_time = 0.0
            self._last_error = None
            self._frame_seq = 0
            self._dropped_frames = 0
            self._session_id = uuid.uuid4().hex
            self._start_time = time.time()
            self._latest_packet = None
            logger.info("FakeCameraAdapter started.")

    def stop(self) -> None:
        with self._lock:
            self._active = False
            self._connection_state = CameraConnectionState.DISCONNECTED
            self._reconnect_attempts = 0
            self._next_reconnect_time = 0.0
            self._last_error = None
            self._simulate_transient_failures = 0
            self._simulate_permanent_disconnection = False
            self._session_id = ""
            self._start_time = None
            self._latest_packet = None
            logger.info("FakeCameraAdapter stopped.")

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def simulate_transient_disconnection(self, failure_count: int = 2) -> None:
        """Injects a temporary disconnection requiring failure_count reconnection cycles to recover."""
        with self._lock:
            self._connection_state = CameraConnectionState.RECONNECTING
            self._simulate_transient_failures = failure_count
            self._simulate_permanent_disconnection = False
            self._reconnect_attempts = 1
            backoff = self.initial_backoff
            self._next_reconnect_time = time.time() + backoff
            self._last_error = f"Simulated transient disconnection ({failure_count} cycles)."
            logger.info(f"FakeCameraAdapter: simulated transient disconnection injected ({failure_count} cycles).")

    def simulate_permanent_disconnection(self) -> None:
        """Injects a permanent disconnection that exhausts all reconnection attempts."""
        with self._lock:
            self._connection_state = CameraConnectionState.RECONNECTING
            self._simulate_permanent_disconnection = True
            self._simulate_transient_failures = 0
            self._reconnect_attempts = 1
            backoff = self.initial_backoff
            self._next_reconnect_time = time.time() + backoff
            self._last_error = "Simulated permanent hardware disconnection."
            logger.info("FakeCameraAdapter: simulated permanent disconnection injected.")

    def push_frame(self, custom_bytes: Optional[bytes] = None) -> FramePacket:
        """
        Simulates camera hardware delivering a frame into the capacity-1 buffer.
        If a previous frame was not consumed by a client, it is overwritten and
        counted as dropped.
        """
        with self._lock:
            if not self._active:
                raise CameraNotActiveError("Cannot push frame to inactive camera.")

            if self._latest_packet is not None:
                self._dropped_frames += 1

            self._frame_seq += 1
            now = time.time()
            jpeg_bytes = custom_bytes or self._generate_test_jpeg()

            self._latest_packet = FramePacket(
                frame_id=self._frame_seq,
                captured_at=now,
                jpeg_bytes=jpeg_bytes,
                width=self.width,
                height=self.height,
                source_id="fake_camera",
                dropped_frames=self._dropped_frames,
                session_id=self._session_id
            )
            return self._latest_packet

    def capture_packet(self) -> FramePacket:
        with self._lock:
            if not self._active:
                raise CameraNotActiveError("Camera is not active. Call start() before requesting frames.")

            now = time.time()

            # If exhausted into ERROR state
            if self._connection_state == CameraConnectionState.ERROR:
                raise CameraConnectionExhaustedError(
                    self.max_reconnect_attempts,
                    self._last_error or f"Camera reconnection exhausted after {self.max_reconnect_attempts} attempts."
                )

            # If in RECONNECTING state, enforce backoff and process recovery attempts
            if self._connection_state == CameraConnectionState.RECONNECTING:
                if now < self._next_reconnect_time:
                    retry_after = max(0.05, self._next_reconnect_time - now)
                    raise CameraReconnectingError(self._reconnect_attempts, self.max_reconnect_attempts, retry_after)

                # Time to attempt reconnection
                if self._simulate_permanent_disconnection:
                    self._reconnect_attempts += 1
                    if self._reconnect_attempts > self.max_reconnect_attempts:
                        self._connection_state = CameraConnectionState.ERROR
                        self._last_error = f"Reconnection exhausted after {self.max_reconnect_attempts} attempts."
                        raise CameraConnectionExhaustedError(self.max_reconnect_attempts)
                    backoff = min(self.max_backoff, self.initial_backoff * (self.backoff_multiplier ** (self._reconnect_attempts - 1)))
                    self._next_reconnect_time = now + backoff
                    raise CameraReconnectingError(self._reconnect_attempts, self.max_reconnect_attempts, backoff)
                elif self._simulate_transient_failures > 0:
                    self._simulate_transient_failures -= 1
                    self._reconnect_attempts += 1
                    if self._reconnect_attempts > self.max_reconnect_attempts:
                        self._connection_state = CameraConnectionState.ERROR
                        self._last_error = f"Reconnection exhausted after {self.max_reconnect_attempts} attempts."
                        raise CameraConnectionExhaustedError(self.max_reconnect_attempts)
                    backoff = min(self.max_backoff, self.initial_backoff * (self.backoff_multiplier ** (self._reconnect_attempts - 1)))
                    self._next_reconnect_time = now + backoff
                    raise CameraReconnectingError(self._reconnect_attempts, self.max_reconnect_attempts, backoff)
                else:
                    # Successfully reconnected!
                    self._connection_state = CameraConnectionState.CONNECTED
                    self._reconnect_attempts = 0
                    self._last_error = None
                    logger.info("FakeCameraAdapter successfully reconnected.")

            if self.should_fail_capture:
                raise FrameCaptureError("Simulated frame capture failure.")

            if self._latest_packet is not None:
                packet = self._latest_packet
                self._latest_packet = None
                return packet

            self._frame_seq += 1
            now = time.time()

            # Generate valid in-memory JPEG frame on demand
            jpeg_bytes = self._generate_test_jpeg()

            return FramePacket(
                frame_id=self._frame_seq,
                captured_at=now,
                jpeg_bytes=jpeg_bytes,
                width=self.width,
                height=self.height,
                source_id="fake_camera",
                dropped_frames=self._dropped_frames,
                session_id=self._session_id
            )

    def _generate_test_jpeg(self) -> bytes:
        """Valid 32x24 neutral gray JPEG image generated without external runtime dependencies."""
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x02\x01\x01\x01\x01\x01\x02\x01\x01\x01\x02\x02\x02\x02\x02\x04\x03\x02\x02\x02\x02\x05\x04\x04\x03\x04\x06\x05\x06\x06\x06\x05\x06\x06\x06\x07\t\x08\x06\x07\t\x07\x06\x06\x08\x0b\x08\t\n\n\n\n\n\x06\x08\x0b\x0c\x0b\n\x0c\t\n\n\n\xff\xdb\x00C\x01\x02\x02\x02\x02\x02\x02\x05\x03\x03\x05\n\x07\x06\x07\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\xff\xc0\x00\x11\x08\x00\x18\x00 \x03\x01\"\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02w\x00\x01\x02\x03\x11\x04\x05!1\x06\x12AQ\x07aq\x13\"2\x81\x08\x14B\x91\xa1\xb1\xc1\t#3R\xf0\x15br\xd1\n\x16$4\xe1%\xf1\x17\x18\x19\x1a&\'()*56789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00(\xa2\x8a\x00(\xa2\x8a\x00(\xa2\x8a\x00(\xa2\x8a\x00\xff\xd9"
        )

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            uptime = time.time() - self._start_time if self._start_time else 0.0
            return {
                "active": self._active,
                "adapter": "FakeCameraAdapter",
                "resolution": f"{self.width}x{self.height}",
                "frames_captured": self._frame_seq,
                "dropped_frames": self._dropped_frames,
                "uptime_seconds": round(uptime, 1),
                "session_id": self._session_id,
                "connection_state": self._connection_state.value,
                "reconnect_attempts": self._reconnect_attempts,
                "max_reconnect_attempts": self.max_reconnect_attempts,
                "last_error": self._last_error
            }
