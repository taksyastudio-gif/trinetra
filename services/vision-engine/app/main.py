"""
Trinetra Vision Engine API
Local-first FastAPI service handling camera ingestion, status, and health.
Binds strictly to 127.0.0.1.
"""

from contextlib import asynccontextmanager
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.camera.adapter import (
    CameraAdapter,
    CameraError,
    CameraInitializationError,
    CameraNotActiveError,
    OpenCVCameraAdapter,
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


class CameraStatusResponse(BaseModel):
    active: bool
    adapter: str
    camera_index: Optional[int] = None
    resolution: Optional[str] = None
    frames_captured: int
    uptime_seconds: float


class CameraActionResponse(BaseModel):
    status: str
    active: bool
    message: str


class CameraManager:
    """Thread-safe holder for the active camera adapter."""
    def __init__(self, adapter: Optional[CameraAdapter] = None):
        self.adapter: CameraAdapter = adapter or OpenCVCameraAdapter()

    def set_adapter(self, adapter: CameraAdapter) -> None:
        if self.adapter.is_active():
            self.adapter.stop()
        self.adapter = adapter


# Singleton manager
camera_manager = CameraManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager ensuring hardware camera is released on server shutdown."""
    logger.info("Trinetra Vision Engine starting up...")
    yield
    logger.info("Trinetra Vision Engine shutting down. Releasing hardware resources...")
    try:
        camera_manager.adapter.stop()
    except Exception as exc:
        logger.warning(f"Error during shutdown camera release: {exc}")
    logger.info("Shutdown complete.")


def create_app(adapter: Optional[CameraAdapter] = None) -> FastAPI:
    """Factory function to build FastAPI app with optional custom camera adapter."""
    if adapter is not None:
        camera_manager.set_adapter(adapter)

    app = FastAPI(
        title="Trinetra Vision Engine",
        version="0.1.0",
        description="Local-first vision and camera control API for the Trinetra assistive navigation system.",
        lifespan=lifespan
    )

    # Restrict CORS strictly to local development and Tauri desktop origins
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
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
        "/api/camera/status",
        response_model=CameraStatusResponse,
        summary="Camera Hardware Status",
        tags=["Camera"]
    )
    def get_camera_status():
        """Returns current operational status, uptime, and frame counts of the camera."""
        info = camera_manager.adapter.get_status()
        return CameraStatusResponse(
            active=info.get("active", False),
            adapter=info.get("adapter", "Unknown"),
            camera_index=info.get("camera_index"),
            resolution=info.get("resolution"),
            frames_captured=info.get("frames_captured", 0),
            uptime_seconds=info.get("uptime_seconds", 0.0)
        )

    @app.post(
        "/api/camera/start",
        response_model=CameraActionResponse,
        summary="Start Camera Stream",
        tags=["Camera"]
    )
    def start_camera():
        """
        Initializes and opens the camera hardware stream.
        Requires explicit user action; never initiated spontaneously.
        """
        adapter = camera_manager.adapter
        if adapter.is_active():
            return CameraActionResponse(
                status="already_running",
                active=True,
                message="Camera stream is already active."
            )

        try:
            adapter.start()
            return CameraActionResponse(
                status="started",
                active=True,
                message="Camera successfully initialized and streaming."
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
        summary="Stop Camera Stream",
        tags=["Camera"]
    )
    def stop_camera():
        """
        Releases the camera hardware lock and halts video ingestion.
        Idempotent: safe to call even if camera is already stopped.
        """
        adapter = camera_manager.adapter
        adapter.stop()
        return CameraActionResponse(
            status="stopped",
            active=False,
            message="Camera stream stopped and hardware resource released."
        )

    @app.get(
        "/api/camera/frame",
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
        """
        adapter = camera_manager.adapter
        if not adapter.is_active():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Camera is not active. Call /api/camera/start before requesting frames."
            )

        try:
            jpeg_bytes = adapter.capture_jpeg()
            return Response(content=jpeg_bytes, media_type="image/jpeg")
        except CameraNotActiveError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Camera was stopped while frame was requested."
            )
        except CameraError as exc:
            logger.warning(f"Frame capture issue: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not retrieve video frame from active camera."
            )

    return app


# Default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    # Binds strictly to loopback IP 127.0.0.1
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
