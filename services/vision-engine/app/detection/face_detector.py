"""
Trinetra Isolated Face Detector Layer
Wraps OpenCV YuNet (cv2.FaceDetectorYN) for ultra-lightweight, high-accuracy face detection on CPU.
Zero external third-party dependencies beyond standard OpenCV.
"""

from dataclasses import dataclass
import hashlib
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.detection.types import BoundingBox

logger = logging.getLogger("trinetra.detection.face")

DEFAULT_YUNET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "models",
    "face_detection_yunet_2023mar.onnx"
)

# Pinned official SHA-256 for face_detection_yunet_2023mar.onnx (OpenCV Zoo)
EXPECTED_YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


@dataclass(frozen=True)
class FaceDetection:
    """Represents a localized human face with confidence and optional landmarks."""
    box: BoundingBox
    confidence: float
    landmarks: Optional[Tuple[Tuple[float, float], ...]] = None


def compute_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hexadecimal digest of a file in 64KB chunks."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


class YuNetFaceDetector:
    """
    Isolated face detector executing YuNet via OpenCV's native FaceDetectorYN interface.
    Operates on BGR image arrays or encoded JPEG bytes in ~4-6 ms on CPU.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        score_threshold: float = 0.60,
        nms_threshold: float = 0.30,
        verify_sha256: bool = True,
        top_k: int = 10
    ):
        self.model_path = model_path or DEFAULT_YUNET_PATH
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k
        self._detector: Optional[Any] = None
        self._current_size: Tuple[int, int] = (320, 320)

        self._model_info: Dict[str, Any] = {
            "model_path": self.model_path,
            "model_name": os.path.basename(self.model_path) if self.model_path else "unknown",
            "runtime": "opencv-FaceDetectorYN",
            "is_ready": False,
            "score_threshold": self.score_threshold
        }

        self._initialize_detector(verify_sha256=verify_sha256)

    def _initialize_detector(self, verify_sha256: bool = True) -> None:
        """Initializes and verifies the YuNet face detector model."""
        if not self.model_path or not os.path.isfile(self.model_path):
            logger.warning(f"YuNet model file not found at '{self.model_path}'. Face detection disabled.")
            return

        if verify_sha256:
            actual_sha = compute_file_sha256(self.model_path)
            if actual_sha != EXPECTED_YUNET_SHA256:
                logger.warning(
                    f"YuNet SHA-256 mismatch for '{self.model_path}'. "
                    f"Expected {EXPECTED_YUNET_SHA256}, got {actual_sha}."
                )

        try:
            self._detector = cv2.FaceDetectorYN.create(
                model=self.model_path,
                config="",
                input_size=self._current_size,
                score_threshold=self.score_threshold,
                nms_threshold=self.nms_threshold,
                top_k=self.top_k
            )
            self._model_info["is_ready"] = True
            logger.info(f"YuNet face detector initialized successfully from '{self.model_path}'.")
        except Exception as exc:
            logger.error(f"Failed to create cv2.FaceDetectorYN instance: {exc}")
            self._detector = None

    def is_ready(self) -> bool:
        return self._detector is not None

    def get_model_info(self) -> Dict[str, Any]:
        return dict(self._model_info)

    def detect_frame(self, img_bgr: np.ndarray) -> List[FaceDetection]:
        """Runs face detection on an existing BGR numpy image."""
        if not self.is_ready() or img_bgr is None or img_bgr.size == 0:
            return []

        h, w = img_bgr.shape[:2]
        if h < 16 or w < 16:
            return []

        if (w, h) != self._current_size:
            self._detector.setInputSize((w, h))
            self._current_size = (w, h)

        try:
            _, faces = self._detector.detect(img_bgr)
        except Exception as exc:
            logger.warning(f"FaceDetectorYN inference failed: {exc}")
            return []

        if faces is None or len(faces) == 0:
            return []

        detections: List[FaceDetection] = []
        for face in faces:
            # Layout: [x1, y1, w_px, h_px, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rcm, y_rcm, x_lcm, y_lcm, score]
            x1_px, y1_px, w_px, h_px = face[:4]
            score = float(face[-1])

            # Clamp coordinates to [0.0, 1.0]
            x_min = max(0.0, min(1.0, float(x1_px) / w))
            y_min = max(0.0, min(1.0, float(y1_px) / h))
            x_max = max(0.0, min(1.0, float(x1_px + w_px) / w))
            y_max = max(0.0, min(1.0, float(y1_px + h_px) / h))

            if x_min >= x_max or y_min >= y_max:
                continue

            # 5 facial landmarks (optional)
            landmarks: Optional[Tuple[Tuple[float, float], ...]] = None
            if len(face) >= 14:
                lm_pts = []
                for idx in range(4, 14, 2):
                    lm_x = max(0.0, min(1.0, float(face[idx]) / w))
                    lm_y = max(0.0, min(1.0, float(face[idx + 1]) / h))
                    lm_pts.append((round(lm_x, 4), round(lm_y, 4)))
                landmarks = tuple(lm_pts)

            detections.append(
                FaceDetection(
                    box=BoundingBox(
                        x_min=round(x_min, 4),
                        y_min=round(y_min, 4),
                        x_max=round(x_max, 4),
                        y_max=round(y_max, 4)
                    ),
                    confidence=round(score, 3),
                    landmarks=landmarks
                )
            )

        return detections

    def detect(self, jpeg_bytes: bytes) -> List[FaceDetection]:
        """Decodes JPEG bytes and runs face detection."""
        if not jpeg_bytes:
            return []
        try:
            nparr = np.frombuffer(jpeg_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return []
            return self.detect_frame(img)
        except Exception as exc:
            logger.warning(f"Failed to decode JPEG bytes for face detection: {exc}")
            return []
