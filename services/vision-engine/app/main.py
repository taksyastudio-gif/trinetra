"""
Trinetra Vision Engine API
Local-first FastAPI service handling camera ingestion, status, and health.
Binds strictly to 127.0.0.1.
Incorporates monotonic frame headers, session tracking, and structured error responses.
"""

from contextlib import asynccontextmanager
import dataclasses
import json
import logging
import math
import os
import threading
from typing import Any, Dict, List, Optional, Union
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.camera.adapter import (
    CameraAdapter,
    CameraBusyError,
    CameraConnectionExhaustedError,
    CameraConnectionState,
    CameraDeviceInfo,
    CameraError,
    CameraInitializationError,
    CameraNotActiveError,
    CameraNotFoundError,
    CameraPermissionError,
    CameraReconnectingError,
    FakeCameraAdapter,
    FrameCaptureError,
    OpenCVCameraAdapter,
)

from pathlib import Path

from app.audio.speaker import (
    SpeechBackend,
    SpeechItem,
    SpeechManager,
    SpeechPriority,
)
from app.detection.engine import (
    BoundingBox,
    Detection,
    DetectionEngine,
    DetectionResult,
    FakeDetectionEngine,
    UnavailableDetectionEngine,
    PerceptionPipeline,
)
from app.detection.onnx_engine import (
    OnnxDetectionEngine,
    ModelError,
    ModelIntegrityError,
    ModelNotFoundError,
    InferenceRuntimeError,
)
from app.incident import (
    IncidentRecord,
    IncidentRecorder,
    LEGAL_DISCLAIMER_TEXT,
)
from app.localization import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    SupportedLanguage,
    is_supported_language,
    normalize_language,
)
from app.location import (
    DisabledLocationProvider,
    LocationManager,
    LocationProvider,
    LocationReport,
    LocationStatus,
    ManualOfflineLocationProvider,
    PRIVACY_GUARANTEE_STATEMENT,
    WindowsLocationProvider,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [trinetra.engine]: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("trinetra.api")


# Pydantic Schemas for Type-Safe Structured Responses
class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class PerceptionHealthTelemetry(BaseModel):
    state: str = "VALID_OBSERVATION"
    status: str = "NORMAL"
    is_degraded: bool = False
    reasons: list[str] = Field(default_factory=list)
    last_evaluated_timestamp: Optional[float] = None
    disclaimer: str = "Diagnostics and debugging only; not safety certified."


class CameraStatusResponse(BaseModel):
    active: bool
    adapter: str
    camera_index: Optional[Union[int, str]] = None
    source_type: Optional[str] = None
    resolution: Optional[str] = None
    frames_captured: int
    dropped_frames: int = 0
    uptime_seconds: float
    session_id: Optional[str] = None
    perception_health: Optional[PerceptionHealthTelemetry] = None
    connection_state: str = "disconnected"
    reconnect_attempts: int = 0
    max_reconnect_attempts: int = 5
    last_error: Optional[str] = None


class CameraActionResponse(BaseModel):
    status: str
    active: bool
    message: str
    session_id: Optional[str] = None


class CameraDeviceResponse(BaseModel):
    index: int
    name: str
    is_available: bool
    status: str


class CameraStartRequest(BaseModel):
    camera_index: Optional[Union[int, str]] = None


class SpeechAnnounceRequest(BaseModel):
    text: str
    priority: Optional[str] = "spatial_navigation"
    interrupt: Optional[bool] = False
    language: Optional[str] = None


class SpeechMuteRequest(BaseModel):
    muted: bool


class SpeechStatusResponse(BaseModel):
    muted: bool
    paused: bool
    language: Optional[str] = DEFAULT_LANGUAGE
    queue_size: int
    backend: str
    available_voices: Optional[List[Dict[str, Any]]] = None
    nepali_voice_available: Optional[bool] = False


class SpeechLanguageResponse(BaseModel):
    language: str
    default_language: str = DEFAULT_LANGUAGE
    supported_languages: List[str] = SUPPORTED_LANGUAGES


class SpeechLanguageUpdateRequest(BaseModel):
    language: str


class SpeechLanguageUpdateResponse(BaseModel):
    status: str = "ok"
    language: str
    previous_language: str
    supported_languages: List[str] = SUPPORTED_LANGUAGES


class DetectionBoxSchema(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class DetectionItemSchema(BaseModel):
    class_name: str
    confidence: float
    box: DetectionBoxSchema
    sector: str


class DetectionResultResponse(BaseModel):
    frame_id: int
    timestamp: float
    detections: list[DetectionItemSchema]
    inference_time_ms: float
    model_name: str
    e2e_latency_ms: float = 0.0


class DetectionStatusResponse(BaseModel):
    active: bool
    model_name: str
    is_ready: bool
    supported_classes: list[str]
    runtime: Optional[str] = "unknown"
    error: Optional[str] = None
    error_type: Optional[str] = None


class IncidentCaptureRequest(BaseModel):
    notes: Optional[str] = ""
    language: Optional[str] = None


class IncidentSummaryResponse(BaseModel):
    incident_id: str
    timestamp_utc: str
    frame_id: int
    image_filename: str
    integrity_digest: str
    detections_count: int
    has_location: bool


class LocationStatusResponse(BaseModel):
    status: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_meters: Optional[float] = None
    timestamp_utc: Optional[str] = None
    source: str
    is_live: bool
    is_stale: bool
    privacy_notice: str


class LocationConfigureRequest(BaseModel):
    enabled: bool
    provider_type: Optional[str] = "windows"
    manual_latitude: Optional[float] = None
    manual_longitude: Optional[float] = None
    manual_accuracy_meters: Optional[float] = None


def get_default_camera_adapter() -> CameraAdapter:
    env_fake = os.environ.get("TRINETRA_USE_FAKE_CAMERA", "").lower() in ("1", "true", "yes")
    if env_fake:
        logger.info("TRINETRA_USE_FAKE_CAMERA active: using FakeCameraAdapter.")
        return FakeCameraAdapter()
    return OpenCVCameraAdapter()


class CameraManager:
    """Thread-safe holder for the authoritative camera adapter and session."""
    def __init__(self, adapter: Optional[CameraAdapter] = None):
        self.adapter: CameraAdapter = adapter or get_default_camera_adapter()
        self.session_id: Optional[str] = None
        self._lock = threading.RLock()

    def set_adapter(self, adapter: CameraAdapter) -> None:
        with self._lock:
            if self.adapter.is_active():
                self.adapter.stop()
            self.adapter = adapter
            self.session_id = None
            if "perception_pipeline" in globals() and perception_pipeline is not None:
                perception_pipeline.reset_session()

    def enumerate_devices(self) -> list[CameraDeviceInfo]:
        with self._lock:
            return self.adapter.enumerate_devices()

    def switch_device(self, new_index: Union[int, str]) -> None:
        with self._lock:
            if self.adapter.is_active():
                self.adapter.stop()
                self.session_id = None
            if "perception_pipeline" in globals() and perception_pipeline is not None:
                perception_pipeline.reset_session()
            if isinstance(self.adapter, OpenCVCameraAdapter):
                self.adapter = OpenCVCameraAdapter(camera_index=new_index)
            elif isinstance(self.adapter, FakeCameraAdapter):
                # FakeCameraAdapter preserves mock capabilities
                pass

    def start_session(self) -> str:
        """Starts camera and generates a new session identifier."""
        with self._lock:
            if not self.adapter.is_active():
                self.adapter.start()
                adapter_status = self.adapter.get_status()
                self.session_id = adapter_status.get("session_id") or uuid.uuid4().hex
                if "perception_pipeline" in globals() and perception_pipeline is not None:
                    perception_pipeline.reset_session(self.session_id)
            return self.session_id or ""

    def stop_session(self) -> None:
        """Releases camera and clears session."""
        with self._lock:
            if self.adapter.is_active():
                self.adapter.stop()
            self.session_id = None
            if "perception_pipeline" in globals() and perception_pipeline is not None:
                perception_pipeline.reset_session()


DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "yolox_nano.onnx"
EXPECTED_MODEL_SHA256 = "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"
DEFAULT_YUNET_PATH = Path(__file__).resolve().parent.parent / "models" / "face_detection_yunet_2023mar.onnx"
EXPECTED_YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


def get_default_detection_fusion() -> Optional[Any]:
    """Initializes DetectionFusion using YuNet face detector if weights are present."""
    if os.environ.get("TRINETRA_DISABLE_FACE_FUSION", "").lower() in ("1", "true", "yes"):
        logger.info("TRINETRA_DISABLE_FACE_FUSION active: face detection fusion disabled.")
        return None

    if DEFAULT_YUNET_PATH.is_file():
        try:
            from app.detection.face_detector import YuNetFaceDetector
            from app.detection.fusion import DetectionFusion
            face_detector = YuNetFaceDetector(model_path=str(DEFAULT_YUNET_PATH))
            if face_detector.is_ready():
                logger.info(f"Loaded verified YuNet face detection model from {DEFAULT_YUNET_PATH}")
                return DetectionFusion(face_detector=face_detector, enabled=True)
        except Exception as exc:
            logger.warning(f"Failed to load YuNet face detection model from {DEFAULT_YUNET_PATH}: {exc}")
    return None


def get_default_detection_engine() -> DetectionEngine:
    """
    Returns the real OnnxDetectionEngine if model weights are present and verified.
    If TRINETRA_USE_FAKE_DETECTION=1 is explicitly set, returns FakeDetectionEngine for testing.
    If TRINETRA_MODEL_PATH is set, initializes that explicit model or raises ModelError/InferenceRuntimeError.
    If the default model weights are missing or corrupt, returns UnavailableDetectionEngine
    with actionable error details. Never silently falls back to FakeDetectionEngine.
    """
    env_fake = os.environ.get("TRINETRA_USE_FAKE_DETECTION", "").lower() in ("1", "true", "yes")
    if env_fake:
        logger.info("TRINETRA_USE_FAKE_DETECTION active: using FakeDetectionEngine for testing.")
        return FakeDetectionEngine()

    env_model = os.environ.get("TRINETRA_MODEL_PATH")
    if env_model:
        logger.info(f"Loading model from TRINETRA_MODEL_PATH: {env_model}")
        return OnnxDetectionEngine(model_path=env_model)

    default_model = DEFAULT_MODEL_PATH
    expected_sha = EXPECTED_MODEL_SHA256
    if default_model.is_file():
        logger.info(f"Loading verified YOLOX-Nano ONNX model from {default_model}")
        try:
            return OnnxDetectionEngine(
                model_path=str(default_model),
                expected_sha256=expected_sha,
                confidence_threshold=0.35,
                iou_threshold=0.45
            )
        except Exception as exc:
            logger.error(f"Failed to load ONNX model from {default_model}: {exc}")
            return UnavailableDetectionEngine(
                error_message=f"Failed to load ONNX model ({default_model.name}): {exc}",
                error_type=type(exc).__name__,
                model_name="yolox_nano.onnx"
            )

    setup_hint = "Run 'python services/vision-engine/scripts/setup_models.py' to download verified weights."
    logger.warning(f"No ONNX model found at default path '{default_model}'. {setup_hint}")
    return UnavailableDetectionEngine(
        error_message=f"Model file not found at '{default_model}'. {setup_hint}",
        error_type="ModelFileNotFound",
        model_name="yolox_nano.onnx"
    )


# Singleton instances
camera_manager = CameraManager()
speech_manager = SpeechManager()
location_manager = LocationManager()
incident_recorder = IncidentRecorder(speech_manager=speech_manager)

perception_pipeline = PerceptionPipeline(
    speech_manager=speech_manager,
    language=DEFAULT_LANGUAGE,
    fusion=get_default_detection_fusion()
)
global_language_lock = threading.RLock()


def start_parent_pid_watchdog() -> None:
    """Watches parent desktop application process and self-terminates if parent dies unexpectedly."""
    parent_pid_str = os.environ.get("TRINETRA_PARENT_PID")
    if not parent_pid_str:
        return
    try:
        parent_pid = int(parent_pid_str.strip())
    except ValueError:
        return

    import time

    def _watchdog_loop():
        while True:
            time.sleep(1.5)
            alive = False
            if os.name == "nt":
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, parent_pid)
                if handle:
                    exit_code = ctypes.c_ulong()
                    ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                    ctypes.windll.kernel32.CloseHandle(handle)
                    alive = (exit_code.value == 259)
            else:
                try:
                    os.kill(parent_pid, 0)
                    alive = True
                except OSError:
                    alive = False

            if not alive:
                logger.info(f"Parent desktop process (PID {parent_pid}) exited. Vision engine shutting down cleanly.")
                try:
                    perception_pipeline.stop()
                    camera_manager.stop_session()
                    speech_manager.shutdown()
                except Exception:
                    pass
                os._exit(0)

    t = threading.Thread(target=_watchdog_loop, daemon=True, name="ParentWatchdog")
    t.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager ensuring hardware camera and services are released on server shutdown."""
    logger.info("Trinetra Vision Engine starting up...")
    start_parent_pid_watchdog()
    yield
    logger.info("Trinetra Vision Engine shutting down. Releasing hardware resources...")
    try:
        perception_pipeline.stop()
        camera_manager.stop_session()
        speech_manager.shutdown()
    except Exception as exc:
        logger.warning(f"Error during shutdown: {exc}")
    logger.info("Shutdown complete.")


def create_app(
    adapter: Optional[CameraAdapter] = None,
    session_token: Optional[str] = None,
    speech_backend: Optional[SpeechBackend] = None,
    detection_engine: Optional[DetectionEngine] = None,
    location_provider: Optional[LocationProvider] = None,
    custom_incident_recorder: Optional[IncidentRecorder] = None,
    enable_docs: Optional[bool] = None,
    language: Optional[str] = None,
    fusion: Optional[Any] = None
) -> FastAPI:
    """Factory function to build FastAPI app with optional custom camera adapter, speech backend, detection engine, location, and token."""
    global incident_recorder
    if adapter is not None:
        camera_manager.set_adapter(adapter)
    elif os.environ.get("TRINETRA_USE_FAKE_CAMERA", "").lower() in ("1", "true", "yes"):
        camera_manager.set_adapter(FakeCameraAdapter())
    if speech_backend is not None:
        speech_manager.backend = speech_backend
    if location_provider is not None:
        location_manager.set_provider(location_provider)
    if custom_incident_recorder is not None:
        incident_recorder = custom_incident_recorder
    if detection_engine is not None:
        perception_pipeline.engine = detection_engine
    else:
        perception_pipeline.engine = get_default_detection_engine()

    if fusion is not None:
        perception_pipeline.fusion = fusion
    elif perception_pipeline.fusion is None:
        perception_pipeline.fusion = get_default_detection_fusion()

    init_lang = normalize_language(language) if (language and is_supported_language(language)) else DEFAULT_LANGUAGE
    with global_language_lock:
        perception_pipeline.language = init_lang
        speech_manager.language = init_lang
        incident_recorder.set_default_language(init_lang)

    with perception_pipeline._lock:
        perception_pipeline._latest_result = None
        perception_pipeline._last_processed_frame_id = -1

    # Optional local authorization token (can be injected or read from env)
    raw_token = session_token if session_token is not None else os.environ.get("TRINETRA_SESSION_TOKEN")
    auth_token = raw_token.strip() if raw_token and raw_token.strip() else None

    # Documentation exposure: disabled by default in production, enabled explicitly via env or parameter
    docs_enabled = (
        enable_docs
        if enable_docs is not None
        else (os.environ.get("TRINETRA_ENABLE_DOCS", "").lower() in ("1", "true", "yes"))
    )

    app = FastAPI(
        title="Trinetra Vision Engine",
        version="0.1.0",
        description="Local-first vision and camera control API for the Trinetra assistive navigation system.",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Restrict CORS strictly to local development and Tauri desktop origins
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5175",  # Current Vite development origin
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
        "http://tauri.localhost",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Frame-Id", "X-Captured-At", "X-Frames-Dropped", "X-Session-Id"],
    )

    def verify_token(x_trinetra_session_token: Optional[str] = Header(None)):
        """Verifies session authorization header if configured."""
        if auth_token and x_trinetra_session_token != auth_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid or missing X-Trinetra-Session-Token."
            )

    @app.get(
        "/api/health",
        response_model=HealthResponse,
        summary="Service Health Check",
        tags=["System"]
    )
    def get_health():
        """Verifies that the Vision Engine service is running locally."""
        return HealthResponse(
            status="ok",
            service="trinetra-vision-engine",
            version="0.1.0"
        )

    @app.get(
        "/api/camera/devices",
        response_model=list[CameraDeviceResponse],
        dependencies=[Depends(verify_token)],
        summary="List Available Camera Devices",
        tags=["Camera"]
    )
    def get_camera_devices():
        """Enumerates connected and available video capture devices."""
        devices = camera_manager.enumerate_devices()
        return [
            CameraDeviceResponse(
                index=d.index,
                name=d.name,
                is_available=d.is_available,
                status=d.status
            )
            for d in devices
        ]

    @app.get(
        "/api/camera/status",
        response_model=CameraStatusResponse,
        dependencies=[Depends(verify_token)],
        summary="Camera Hardware Status",
        tags=["Camera"]
    )
    def get_camera_status():
        """Returns current operational status, uptime, frame counts, perception health, and session id."""
        info = camera_manager.adapter.get_status()

        health_telemetry = None
        if "perception_pipeline" in globals() and perception_pipeline is not None:
            ctrl = getattr(perception_pipeline, "health_controller", None)
            if ctrl is not None:
                state_val = getattr(ctrl.state, "value", str(ctrl.state))
                ass = getattr(ctrl, "latest_assessment", None)
                if ass is not None:
                    status_val = getattr(ass.status, "value", str(ass.status))
                    is_deg = status_val != "NORMAL" or state_val != "VALID_OBSERVATION"
                    reasons = [getattr(r, "value", str(r)) for r in (ass.reasons or ())]
                    ts = ass.timestamp
                else:
                    status_val = "NORMAL"
                    is_deg = state_val != "VALID_OBSERVATION"
                    reasons = []
                    ts = None

                health_telemetry = PerceptionHealthTelemetry(
                    state=state_val,
                    status=status_val,
                    is_degraded=is_deg,
                    reasons=reasons,
                    last_evaluated_timestamp=ts,
                    disclaimer="Diagnostics and debugging only; not safety certified."
                )

        return CameraStatusResponse(
            active=info.get("active", False),
            adapter=info.get("adapter", "Unknown"),
            camera_index=info.get("camera_index"),
            source_type=info.get("source_type"),
            resolution=info.get("resolution"),
            frames_captured=info.get("frames_captured", 0),
            dropped_frames=info.get("dropped_frames", 0),
            uptime_seconds=info.get("uptime_seconds", 0.0),
            session_id=camera_manager.session_id,
            perception_health=health_telemetry,
            connection_state=info.get("connection_state", "connected" if info.get("active", False) else "disconnected"),
            reconnect_attempts=info.get("reconnect_attempts", 0),
            max_reconnect_attempts=info.get("max_reconnect_attempts", 5),
            last_error=info.get("last_error", None)
        )

    @app.post(
        "/api/camera/start",
        response_model=CameraActionResponse,
        dependencies=[Depends(verify_token)],
        summary="Start Camera Stream",
        tags=["Camera"]
    )
    def start_camera(payload: Optional[CameraStartRequest] = None):
        """
        Initializes and opens the camera hardware stream.
        Requires explicit user action; never initiated spontaneously.
        Optionally switches to requested camera_index before starting.
        """
        requested_index = payload.camera_index if payload else None

        with camera_manager._lock:
            current_idx = getattr(camera_manager.adapter, "camera_index", 0)
            if requested_index is not None and requested_index != current_idx:
                camera_manager.switch_device(requested_index)

            if camera_manager.adapter.is_active():
                return CameraActionResponse(
                    status="already_running",
                    active=True,
                    message="Camera stream is already active.",
                    session_id=camera_manager.session_id
                )

            try:
                session_id = camera_manager.start_session()
                return CameraActionResponse(
                    status="started",
                    active=True,
                    message="Camera successfully initialized and streaming.",
                    session_id=session_id
                )
            except CameraBusyError as exc:
                logger.error(f"Camera busy: {exc}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc)
                )
            except CameraInitializationError as exc:
                logger.error(f"Camera start failure: {exc}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc)
                )
            except Exception as exc:
                logger.error(f"Unexpected camera start exception: {exc}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="An internal error occurred while trying to initialize the camera."
                )

    @app.post(
        "/api/camera/stop",
        response_model=CameraActionResponse,
        dependencies=[Depends(verify_token)],
        summary="Stop Camera Stream",
        tags=["Camera"]
    )
    def stop_camera():
        """
        Releases the camera hardware lock and halts video ingestion.
        Idempotent: safe to call even if camera is already stopped.
        """
        camera_manager.stop_session()
        return CameraActionResponse(
            status="stopped",
            active=False,
            message="Camera stream stopped and hardware resource released.",
            session_id=None
        )

    @app.get(
        "/api/camera/frame",
        dependencies=[Depends(verify_token)],
        summary="Get Latest Video Frame",
        tags=["Camera"],
        responses={
            200: {
                "content": {"image/jpeg": {}},
                "description": "Returns latest JPEG encoded video frame."
            },
            409: {"description": "Camera is not currently active."},
            500: {"description": "Frame capture or encoding failure."}
        }
    )
    def get_camera_frame():
        """
        Fetches the latest live frame from the active camera as an encoded JPEG buffer.
        Frames are kept purely in memory and never written to disk.
        Returns monotonic frame telemetry headers (X-Frame-Id, X-Captured-At, X-Frames-Dropped).
        """
        if not camera_manager.adapter.is_active():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Camera is not active. Call /api/camera/start before requesting frames."
            )

        try:
            packet = camera_manager.adapter.capture_packet()
            if camera_manager.session_id and not packet.session_id:
                packet = dataclasses.replace(packet, session_id=camera_manager.session_id)

            # Asynchronously submit frame to perception pipeline (completely non-blocking)
            if perception_pipeline.is_active():
                perception_pipeline.submit_frame(packet)

            headers = {
                "X-Frame-Id": str(packet.frame_id),
                "X-Captured-At": f"{packet.captured_at:.3f}",
                "X-Frames-Dropped": str(packet.dropped_frames),
                "X-Session-Id": camera_manager.session_id or ""
            }
            return Response(content=packet.jpeg_bytes, media_type="image/jpeg", headers=headers)
        except CameraNotActiveError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Camera was stopped while frame was requested."
            )
        except CameraReconnectingError as exc:
            logger.info(f"Camera recovering: {exc}")
            retry_int = max(1, int(math.ceil(exc.retry_after)))
            resp_body = {
                "detail": str(exc),
                "status": "reconnecting",
                "attempt": exc.attempt,
                "max_attempts": exc.max_attempts,
                "retry_after": round(exc.retry_after, 2),
                "error_code": "camera_reconnecting"
            }
            return Response(
                content=json.dumps(resp_body).encode("utf-8"),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="application/json",
                headers={"Retry-After": str(retry_int)}
            )
        except CameraConnectionExhaustedError as exc:
            logger.error(f"Camera reconnection exhausted: {exc}")
            resp_body = {
                "detail": str(exc),
                "status": "exhausted",
                "total_attempts": exc.total_attempts,
                "error_code": "camera_reconnection_exhausted"
            }
            return Response(
                content=json.dumps(resp_body).encode("utf-8"),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="application/json"
            )
        except (FrameCaptureError, CameraError) as exc:
            logger.warning(f"Frame capture issue: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not retrieve video frame from active camera."
            )

    # =========================================================================
    # Speech Announcement Endpoints
    # =========================================================================

    @app.get(
        "/api/speech/language",
        response_model=SpeechLanguageResponse,
        dependencies=[Depends(verify_token)],
        summary="Get Spoken Announcement Language",
        tags=["Speech"]
    )
    def speech_get_language():
        """Returns the current active language, default language, and supported speech languages."""
        with global_language_lock:
            cur_lang = perception_pipeline.language
        return SpeechLanguageResponse(
            language=cur_lang,
            default_language=DEFAULT_LANGUAGE,
            supported_languages=SUPPORTED_LANGUAGES,
        )

    @app.post(
        "/api/speech/language",
        response_model=SpeechLanguageUpdateResponse,
        dependencies=[Depends(verify_token)],
        summary="Set Spoken Announcement Language",
        tags=["Speech"]
    )
    def speech_set_language(payload: SpeechLanguageUpdateRequest):
        """
        Dynamically updates the active spoken language (e.g. 'ne' or 'en')
        across perception, scene decision, speech manager, and incident recording
        without restarting camera or pipeline.
        """
        try:
            target_lang = normalize_language(payload.language)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc)
            )

        with global_language_lock:
            prev_lang = perception_pipeline.language
            perception_pipeline.language = target_lang
            speech_manager.language = target_lang
            incident_recorder.set_default_language(target_lang)

        logger.info(f"Language switched dynamically without restarting: '{prev_lang}' -> '{target_lang}'")
        return SpeechLanguageUpdateResponse(
            status="ok",
            language=target_lang,
            previous_language=prev_lang,
            supported_languages=SUPPORTED_LANGUAGES,
        )

    @app.post(
        "/api/speech/announce",
        dependencies=[Depends(verify_token)],
        summary="Speak Announcement",
        tags=["Speech"]
    )
    def speech_announce(payload: SpeechAnnounceRequest):
        p_map = {
            "critical_hazard": SpeechPriority.CRITICAL_HAZARD,
            "spatial_navigation": SpeechPriority.SPATIAL_NAVIGATION,
            "informational": SpeechPriority.INFORMATIONAL
        }
        priority = p_map.get(payload.priority.lower(), SpeechPriority.SPATIAL_NAVIGATION)
        target_lang = (
            normalize_language(payload.language)
            if payload.language and is_supported_language(payload.language)
            else (payload.language or perception_pipeline.language)
        )
        enqueued = speech_manager.announce(
            text=payload.text,
            priority=priority,
            interrupt=payload.interrupt or False,
            language=target_lang
        )
        return {"status": "enqueued" if enqueued else "suppressed", "enqueued": enqueued}

    @app.post(
        "/api/speech/stop",
        dependencies=[Depends(verify_token)],
        summary="Stop Current Speech",
        tags=["Speech"]
    )
    def speech_stop():
        speech_manager.stop()
        return {"status": "stopped"}

    @app.post(
        "/api/speech/mute",
        dependencies=[Depends(verify_token)],
        summary="Set Speech Mute",
        tags=["Speech"]
    )
    def speech_mute(payload: SpeechMuteRequest):
        if payload.muted:
            speech_manager.mute()
        else:
            speech_manager.unmute()
        return {"status": "ok", "muted": speech_manager.is_muted()}

    @app.get(
        "/api/speech/status",
        response_model=SpeechStatusResponse,
        dependencies=[Depends(verify_token)],
        summary="Get Speech Status",
        tags=["Speech"]
    )
    def speech_status():
        info = speech_manager.get_status()
        return SpeechStatusResponse(
            muted=info["muted"],
            paused=info["paused"],
            language=info.get("language", perception_pipeline.language),
            queue_size=info["queue_size"],
            backend=info["backend"],
            available_voices=info.get("available_voices", []),
            nepali_voice_available=info.get("nepali_voice_available", False)
        )

    # =========================================================================
    # Object Detection & Perception Endpoints
    # =========================================================================

    @app.get(
        "/api/detection/status",
        response_model=DetectionStatusResponse,
        dependencies=[Depends(verify_token)],
        summary="Get Detection Status",
        tags=["Detection"]
    )
    def detection_status():
        info = perception_pipeline.engine.get_model_info()
        return DetectionStatusResponse(
            active=perception_pipeline.is_active(),
            model_name=info.get("model_name", "Unknown"),
            is_ready=info.get("is_ready", False),
            supported_classes=info.get("supported_classes", []),
            runtime=info.get("runtime", "unknown"),
            error=info.get("error"),
            error_type=info.get("error_type")
        )

    @app.post(
        "/api/detection/start",
        dependencies=[Depends(verify_token)],
        summary="Start Object Detection Pipeline",
        tags=["Detection"]
    )
    def detection_start():
        if not perception_pipeline.engine.is_ready():
            info = perception_pipeline.engine.get_model_info()
            err_msg = info.get("error") or "Detection model is not ready or unavailable."
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Cannot start detection: {err_msg}"
            )
        perception_pipeline.start()
        return {"status": "started", "active": True}

    @app.post(
        "/api/detection/stop",
        dependencies=[Depends(verify_token)],
        summary="Stop Object Detection Pipeline",
        tags=["Detection"]
    )
    def detection_stop():
        perception_pipeline.stop()
        return {"status": "stopped", "active": False}

    @app.get(
        "/api/detection/latest",
        response_model=Optional[DetectionResultResponse],
        dependencies=[Depends(verify_token)],
        summary="Get Latest Detections",
        tags=["Detection"]
    )
    def detection_latest():
        latest = perception_pipeline.get_latest_result()
        if latest is None:
            return None
        return DetectionResultResponse(
            frame_id=latest.frame_id,
            timestamp=latest.timestamp,
            detections=[
                DetectionItemSchema(
                    class_name=d.class_name,
                    confidence=d.confidence,
                    box=DetectionBoxSchema(
                        x_min=d.box.x_min,
                        y_min=d.box.y_min,
                        x_max=d.box.x_max,
                        y_max=d.box.y_max
                    ),
                    sector=d.sector
                )
                for d in latest.detections
            ],
            inference_time_ms=latest.inference_time_ms,
            model_name=latest.model_name,
            e2e_latency_ms=getattr(latest, "e2e_latency_ms", 0.0)
        )

    # =========================================================================
    # Accessible Incident Documentation Endpoints
    # =========================================================================

    @app.post(
        "/api/incident/capture",
        dependencies=[Depends(verify_token)],
        summary="Capture Accessible Incident Snapshot",
        tags=["Incident"]
    )
    def incident_capture(payload: Optional[IncidentCaptureRequest] = None):
        if not camera_manager.adapter.is_active():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Camera is not active. Start camera session before capturing incident snapshot."
            )

        try:
            packet = camera_manager.adapter.capture_packet()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Frame acquisition failed during incident capture: {exc}"
            )

        notes = payload.notes if payload and payload.notes else "Manual incident capture"
        lang = (
            normalize_language(payload.language)
            if payload and payload.language and is_supported_language(payload.language)
            else (payload.language if payload and payload.language else perception_pipeline.language)
        )

        latest_detections = perception_pipeline.get_latest_result()
        loc_report = location_manager.get_report().to_dict()

        record = incident_recorder.capture(
            packet=packet,
            detection_result=latest_detections,
            location_data=loc_report,
            notes=notes,
            language=lang
        )
        return record.to_dict()

    @app.get(
        "/api/incident/list",
        dependencies=[Depends(verify_token)],
        summary="List Incident Snapshots",
        tags=["Incident"]
    )
    def incident_list():
        return incident_recorder.list_incidents()

    @app.get(
        "/api/incident/{incident_id}",
        dependencies=[Depends(verify_token)],
        summary="Get Incident Metadata",
        tags=["Incident"]
    )
    def incident_get(incident_id: str):
        res = incident_recorder.get_incident(incident_id)
        if res is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident record '{incident_id}' not found."
            )
        record, _ = res
        return record.to_dict()

    @app.get(
        "/api/incident/{incident_id}/image",
        dependencies=[Depends(verify_token)],
        summary="Get Incident Image JPEG",
        tags=["Incident"]
    )
    def incident_get_image(incident_id: str):
        res = incident_recorder.get_incident(incident_id)
        if res is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident record '{incident_id}' not found."
            )
        _, img_bytes = res
        return Response(content=img_bytes, media_type="image/jpeg")

    @app.post(
        "/api/incident/{incident_id}/verify",
        dependencies=[Depends(verify_token)],
        summary="Cryptographically Verify Incident Integrity",
        tags=["Incident"]
    )
    def incident_verify(incident_id: str):
        result = incident_recorder.verify_integrity(incident_id)
        if not result.get("verified") and result.get("error") == "Metadata file not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident record '{incident_id}' not found."
            )
        return result

    # =========================================================================
    # Offline Location Endpoints
    # =========================================================================

    @app.get(
        "/api/location/status",
        response_model=LocationStatusResponse,
        dependencies=[Depends(verify_token)],
        summary="Get Offline Location Status",
        tags=["Location"]
    )
    def location_status():
        rep = location_manager.get_report()
        return LocationStatusResponse(
            status=rep.status.value,
            latitude=rep.latitude,
            longitude=rep.longitude,
            accuracy_meters=rep.accuracy_meters,
            timestamp_utc=rep.timestamp_utc,
            source=rep.source,
            is_live=rep.is_live,
            is_stale=rep.is_stale,
            privacy_notice=rep.privacy_notice
        )

    @app.post(
        "/api/location/configure",
        dependencies=[Depends(verify_token)],
        summary="Configure Location Provider",
        tags=["Location"]
    )
    def location_configure(payload: LocationConfigureRequest):
        if not payload.enabled:
            location_manager.set_provider(DisabledLocationProvider())
        else:
            ptype = (payload.provider_type or "windows").lower()
            if ptype == "manual":
                provider = ManualOfflineLocationProvider(
                    latitude=payload.manual_latitude,
                    longitude=payload.manual_longitude,
                    accuracy_meters=payload.manual_accuracy_meters or 50.0
                )
                location_manager.set_provider(provider)
            elif ptype == "windows":
                provider = WindowsLocationProvider()
                provider.enable()
                location_manager.set_provider(provider)
            else:
                location_manager.set_provider(DisabledLocationProvider())

        rep = location_manager.get_report()
        return rep.to_dict()

    return app


# Default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    # Binds strictly to loopback IP 127.0.0.1
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
