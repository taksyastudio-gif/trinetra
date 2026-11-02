"""
Trinetra Camera Ego-Motion Estimator
Lightweight sparse optical-flow-based camera ego-motion estimation using OpenCV.
Estimates camera translation (dx, dy), rotation (dtheta), and scale changes between consecutive frames.
Excludes detected foreground objects to prevent moving objects from polluting background ego-motion.
Computes multi-factor reliability metrics (inlier ratio, spatial spread, feature count, residual).
Provides honest fallback when confidence is insufficient.
"""

from dataclasses import dataclass
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from app.detection.types import BoundingBox

logger = logging.getLogger("trinetra.ego_motion")


@dataclass(frozen=True)
class EgoMotionEstimate:
    """
    Encapsulates camera ego-motion transformation and statistical reliability between consecutive frames.
    All translation coordinates and transforms are expressed in normalized image coordinate space [0.0, 1.0].
    """
    dx: float                                      # Normalized image translation along X-axis (right = positive)
    dy: float                                      # Normalized image translation along Y-axis (down = positive)
    rotation_rad: float                            # Rotation angle around camera optical axis in radians
    scale: float                                   # Uniform scale factor (1.0 = no scale change)
    transform_matrix: Optional[np.ndarray] = None  # 2x3 normalized affine transformation matrix
    is_reliable: bool = False                      # True if ego-motion satisfies all statistical confidence gates
    confidence: float = 0.0                        # Reliability confidence score in range [0.0, 1.0]
    num_features: int = 0                          # Total tracked feature points
    num_inliers: int = 0                           # Number of RANSAC inlier features
    inlier_ratio: float = 0.0                      # Ratio of inliers to tracked features
    error_reason: Optional[str] = None             # Diagnostic label explaining unreliability when is_reliable=False
    dt: float = 0.0                                # Time delta between frames in seconds
    timestamp: float = 0.0                         # Acquisition timestamp of current frame


class SparseOpticalFlowEgoMotionEstimator:
    """
    Lightweight, CPU-only sparse optical flow camera ego-motion estimator.
    Uses Shi-Tomasi corner detection, pyramidal Lucas-Kanade feature tracking,
    and RANSAC partial affine estimation to recover 4-DOF global camera motion.
    """

    def __init__(
        self,
        max_features: int = 150,
        downscale_width: int = 320,
        min_inliers: int = 12,
        min_inlier_ratio: float = 0.50,
        ransac_reproj_threshold_px: float = 2.5,
        max_dt_sec: float = 1.0,
        min_dt_sec: float = 0.001
    ):
        self.max_features = max_features
        self.downscale_width = downscale_width
        self.min_inliers = min_inliers
        self.min_inlier_ratio = min_inlier_ratio
        self.ransac_reproj_threshold_px = ransac_reproj_threshold_px
        self.max_dt_sec = max_dt_sec
        self.min_dt_sec = min_dt_sec

        self._prev_gray: Optional[np.ndarray] = None
        self._prev_time: float = 0.0
        self._prev_shape: Optional[Tuple[int, int]] = None

    def reset(self) -> None:
        """Purges internal temporal state (used across session resets or camera interruptions)."""
        self._prev_gray = None
        self._prev_time = 0.0
        self._prev_shape = None

    def estimate(
        self,
        image: Union[np.ndarray, bytes],
        timestamp: float,
        detected_boxes: Optional[List[BoundingBox]] = None
    ) -> EgoMotionEstimate:
        """
        Estimates camera ego-motion from previous frame to current frame.
        Accepts raw JPEG bytes or a NumPy image array (grayscale or BGR).
        Optionally masks out detected object bounding boxes to avoid foreground motion pollution.
        """
        # 1. Preprocess & validate input image
        gray, decode_error = self._preprocess_image(image)
        if gray is None:
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                error_reason=decode_error or "invalid_image",
                timestamp=timestamp
            )

        # 2. Check resolution continuity
        curr_shape = gray.shape
        if self._prev_shape is not None and curr_shape != self._prev_shape:
            self._prev_gray = gray
            self._prev_time = timestamp
            self._prev_shape = curr_shape
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                error_reason="resolution_changed",
                timestamp=timestamp
            )

        # 3. Check temporal continuity
        if self._prev_gray is None or self._prev_time <= 0.0:
            self._prev_gray = gray
            self._prev_time = timestamp
            self._prev_shape = curr_shape
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                error_reason="first_frame",
                timestamp=timestamp
            )

        dt = timestamp - self._prev_time
        if dt < self.min_dt_sec or dt > self.max_dt_sec:
            self._prev_gray = gray
            self._prev_time = timestamp
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                error_reason="irregular_timestamp",
                dt=dt, timestamp=timestamp
            )

        # 4. Construct foreground exclusion mask to isolate static background
        # Moving objects must NOT dominate the ego-motion estimate
        mask = self._build_background_mask(gray.shape, detected_boxes)

        # 5. Extract background features from previous frame
        p0 = cv2.goodFeaturesToTrack(
            self._prev_gray,
            maxCorners=self.max_features,
            qualityLevel=0.01,
            minDistance=8,
            mask=mask
        )

        if p0 is None or len(p0) < self.min_inliers:
            self._prev_gray = gray
            self._prev_time = timestamp
            num_found = len(p0) if p0 is not None else 0
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                num_features=num_found,
                error_reason="insufficient_features",
                dt=dt, timestamp=timestamp
            )

        # 6. Track sparse features across consecutive frames via Pyramidal Lucas-Kanade
        p1, status, err = cv2.calcOpticalFlowPyrLK(
            self._prev_gray,
            gray,
            p0,
            None,
            winSize=(15, 15),
            maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)
        )

        if status is None:
            self._prev_gray = gray
            self._prev_time = timestamp
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                error_reason="optical_flow_failed",
                dt=dt, timestamp=timestamp
            )

        valid_mask = status.flatten() == 1
        good_p0 = p0[valid_mask]
        good_p1 = p1[valid_mask]

        if len(good_p1) < self.min_inliers:
            self._prev_gray = gray
            self._prev_time = timestamp
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                num_features=len(good_p1),
                error_reason="insufficient_tracked_features",
                dt=dt, timestamp=timestamp
            )

        # 7. Robust global motion estimation using RANSAC estimateAffinePartial2D (4-DOF: tx, ty, rot, scale)
        M, inliers = cv2.estimateAffinePartial2D(
            good_p0,
            good_p1,
            method=cv2.RANSAC,
            ransacReprojThreshold=self.ransac_reproj_threshold_px,
            maxIters=500,
            confidence=0.99
        )

        if M is None or inliers is None:
            self._prev_gray = gray
            self._prev_time = timestamp
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                num_features=len(good_p1),
                error_reason="affine_estimation_failed",
                dt=dt, timestamp=timestamp
            )

        num_inliers = int(np.sum(inliers))
        inlier_ratio = float(num_inliers) / float(len(good_p1))

        if num_inliers < self.min_inliers:
            self._prev_gray = gray
            self._prev_time = timestamp
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                num_features=len(good_p1),
                num_inliers=num_inliers,
                inlier_ratio=inlier_ratio,
                error_reason="insufficient_inliers",
                dt=dt, timestamp=timestamp
            )

        if inlier_ratio < self.min_inlier_ratio:
            self._prev_gray = gray
            self._prev_time = timestamp
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                num_features=len(good_p1),
                num_inliers=num_inliers,
                inlier_ratio=inlier_ratio,
                error_reason="low_inlier_ratio",
                dt=dt, timestamp=timestamp
            )

        # 8. Spatial distribution check: inliers must not be concentrated in a single degenerate cluster
        inlier_pts_0 = good_p0[inliers.flatten() == 1]
        inlier_pts_1 = good_p1[inliers.flatten() == 1]

        std_x = float(np.std(inlier_pts_0[:, 0, 0])) / float(gray.shape[1])
        std_y = float(np.std(inlier_pts_0[:, 0, 1])) / float(gray.shape[0])

        if std_x < 0.05 or std_y < 0.05:
            self._prev_gray = gray
            self._prev_time = timestamp
            return EgoMotionEstimate(
                dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0,
                is_reliable=False, confidence=0.0,
                num_features=len(good_p1),
                num_inliers=num_inliers,
                inlier_ratio=inlier_ratio,
                error_reason="poor_spatial_spread",
                dt=dt, timestamp=timestamp
            )

        # 9. Extract physical parameters and normalize coordinates
        # M is in downscaled pixel units:
        # [ [s*cos(theta), -s*sin(theta), tx],
        #   [s*sin(theta),  s*cos(theta), ty] ]
        s = float(np.sqrt(M[0, 0] ** 2 + M[1, 0] ** 2))
        theta = float(np.arctan2(M[1, 0], M[0, 0]))
        dx_norm = float(M[0, 2]) / float(gray.shape[1])
        dy_norm = float(M[1, 2]) / float(gray.shape[0])

        # 10. Motion boundary / scene-cut checks
        if (
            abs(dx_norm) > 0.35
            or abs(dy_norm) > 0.35
            or abs(s - 1.0) > 0.35
            or abs(theta) > math.radians(35.0)
        ):
            self._prev_gray = gray
            self._prev_time = timestamp
            return EgoMotionEstimate(
                dx=dx_norm, dy=dy_norm, rotation_rad=theta, scale=s,
                is_reliable=False, confidence=0.0,
                num_features=len(good_p1),
                num_inliers=num_inliers,
                inlier_ratio=inlier_ratio,
                error_reason="extreme_motion_or_scene_cut",
                dt=dt, timestamp=timestamp
            )

        # 11. Model residual check: mean reprojection error of inliers
        transformed_p0 = cv2.transform(inlier_pts_0, M)
        diff = inlier_pts_1 - transformed_p0
        mean_residual_px = float(np.mean(np.linalg.norm(diff, axis=2)))

        if mean_residual_px > 3.0:
            self._prev_gray = gray
            self._prev_time = timestamp
            return EgoMotionEstimate(
                dx=dx_norm, dy=dy_norm, rotation_rad=theta, scale=s,
                is_reliable=False, confidence=0.0,
                num_features=len(good_p1),
                num_inliers=num_inliers,
                inlier_ratio=inlier_ratio,
                error_reason="high_model_residual",
                dt=dt, timestamp=timestamp
            )

        # 12. Normalized affine transformation matrix for [0, 1] normalized space
        # u' = M00 * u + M01 * (H/W) * v + (tx / W)
        # v' = M10 * (W/H) * u + M11 * v + (ty / H)
        h_px, w_px = gray.shape[:2]
        aspect = float(h_px) / float(w_px)
        M_norm = np.array([
            [M[0, 0], M[0, 1] * aspect, dx_norm],
            [M[1, 0] / aspect, M[1, 1], dy_norm]
        ], dtype=np.float64)

        # 13. Multi-factor confidence score [0.0, 1.0]
        # Combines inlier ratio, feature count, spatial spread, and residual quality
        inlier_score = inlier_ratio
        count_score = min(1.0, float(num_inliers) / 25.0)
        spread_score = min(1.0, (std_x + std_y) / 0.25)
        residual_score = max(0.0, 1.0 - (mean_residual_px / 3.0))

        confidence = float(np.clip(
            inlier_score * count_score * spread_score * residual_score,
            0.0,
            1.0
        ))

        # Advance temporal state
        self._prev_gray = gray
        self._prev_time = timestamp
        self._prev_shape = curr_shape

        return EgoMotionEstimate(
            dx=round(dx_norm, 4),
            dy=round(dy_norm, 4),
            rotation_rad=round(theta, 4),
            scale=round(s, 4),
            transform_matrix=M_norm,
            is_reliable=True,
            confidence=round(confidence, 3),
            num_features=len(good_p1),
            num_inliers=num_inliers,
            inlier_ratio=round(inlier_ratio, 3),
            error_reason=None,
            dt=round(dt, 4),
            timestamp=timestamp
        )

    def _preprocess_image(self, image: Union[np.ndarray, bytes]) -> Tuple[Optional[np.ndarray], Optional[str]]:
        """Extracts and resizes downscaled single-channel grayscale buffer in CPU memory."""
        if image is None:
            return None, "empty_image"

        if isinstance(image, bytes):
            if len(image) == 0:
                return None, "empty_image_bytes"
            nparr = np.frombuffer(image, np.uint8)
            gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                return None, "corrupt_image_bytes"
            if gray.shape[0] < 16 or gray.shape[1] < 16:
                return None, "image_too_small"
        elif isinstance(image, np.ndarray):
            if image.size == 0:
                return None, "empty_image_array"
            if image.shape[0] < 16 or image.shape[1] < 16:
                return None, "image_too_small"
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            elif len(image.shape) == 2:
                gray = image
            else:
                return None, "unsupported_image_shape"
        else:
            return None, "unsupported_image_type"

        orig_h, orig_w = gray.shape[:2]
        if orig_w > self.downscale_width:
            scale = self.downscale_width / float(orig_w)
            target_h = int(orig_h * scale)
            gray = cv2.resize(gray, (self.downscale_width, target_h), interpolation=cv2.INTER_AREA)

        return gray, None

    def _build_background_mask(
        self,
        shape: Tuple[int, int],
        detected_boxes: Optional[List[BoundingBox]]
    ) -> np.ndarray:
        """
        Creates an 8-bit single-channel mask where detected foreground objects are zeroed out
        with an expanded safety margin, preventing foreground features from polluting camera ego-motion.
        """
        mask = np.full(shape, 255, dtype=np.uint8)
        if not detected_boxes:
            return mask

        h, w = shape
        for box in detected_boxes:
            # 3% margin expansion around detected objects
            margin_x = 0.03
            margin_y = 0.03
            x0 = max(0, int((box.x_min - margin_x) * w))
            x1 = min(w, int((box.x_max + margin_x) * w))
            y0 = max(0, int((box.y_min - margin_y) * h))
            y1 = min(h, int((box.y_max + margin_y) * h))
            mask[y0:y1, x0:x1] = 0

        return mask
