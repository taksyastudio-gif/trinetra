"""
Trinetra Temporal Object Tracking Layer
Maintains object persistence across consecutive camera frames, associates observations with
monotonic track IDs, computes movement trajectories, and handles missing frames and occlusion.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import time
from typing import Any, List, Optional, Tuple

import numpy as np

from app.detection.trajectory import (
    CrossingDirection,
    TrajectoryClassification,
    TrajectoryClassifier,
    TrajectoryEstimate,
)
from app.detection.types import BoundingBox, Detection, classify_sector

logger = logging.getLogger("trinetra.tracking")


class TrackState(str, Enum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    LOST = "lost"
    DELETED = "deleted"


class MovementDirection(str, Enum):
    APPROACHING = "approaching"
    RECEDING = "receding"
    MOVING_LEFT = "moving_left"
    MOVING_RIGHT = "moving_right"
    STATIONARY = "stationary"
    UNKNOWN = "unknown"


def compute_iou(box_a: BoundingBox, box_b: BoundingBox) -> float:
    """Computes Intersection-over-Union (IoU) overlap between two normalized 2D bounding boxes."""
    x_left = max(box_a.x_min, box_b.x_min)
    y_top = max(box_a.y_min, box_b.y_min)
    x_right = min(box_a.x_max, box_b.x_max)
    y_bottom = min(box_a.y_max, box_b.y_max)

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    area_a = box_a.area
    area_b = box_b.area
    union_area = area_a + area_b - intersection_area

    if union_area <= 0.0:
        return 0.0
    return intersection_area / union_area


class KalmanBoxTracker:
    """
    Lightweight 8-state constant-velocity Kalman filter for 2D bounding boxes in normalized coordinates.
    State vector: x = [x_c, y_c, w, h, v_x, v_y, v_w, v_h]^T.
    Maintains continuous estimates of position, box dimensions, and corresponding velocities.
    """

    def __init__(self, initial_box: BoundingBox, initial_time: float):
        self.last_time = initial_time

        # Initial state vector x
        w = max(0.005, initial_box.x_max - initial_box.x_min)
        h = max(0.005, initial_box.y_max - initial_box.y_min)
        xc = initial_box.center_x
        yc = initial_box.center_y
        self.x = np.array([xc, yc, w, h, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)

        # Initial covariance P
        # Low uncertainty on initial positions and box dimensions; higher uncertainty on velocities.
        self.P = np.diag([
            0.01 ** 2, 0.01 ** 2, 0.02 ** 2, 0.02 ** 2,
            0.20 ** 2, 0.20 ** 2, 0.20 ** 2, 0.20 ** 2
        ])

        # Measurement matrix H (4x8): directly observes [x_c, y_c, w, h]
        self.H = np.zeros((4, 8), dtype=np.float64)
        np.fill_diagonal(self.H, 1.0)

        # Measurement noise covariance R (4x4)
        self.R = np.diag([0.01 ** 2, 0.01 ** 2, 0.015 ** 2, 0.015 ** 2])

        # Acceleration standard deviations for continuous white noise acceleration model
        self.sigma_a_pos = 1.0   # position acceleration spectral density
        self.sigma_a_size = 0.5  # size acceleration spectral density

    def predict(self, timestamp: float, ego_motion: Optional[Any] = None) -> BoundingBox:
        """
        Advances the state distribution forward in time by dt = timestamp - last_time.
        Applies camera ego-motion transformation if reliable estimate is provided.
        Returns the predicted BoundingBox.
        """
        dt = max(0.001, min(1.0, timestamp - self.last_time))
        self.last_time = timestamp

        # Transition matrix F (8x8)
        F = np.eye(8, dtype=np.float64)
        for i in range(4):
            F[i, i + 4] = dt

        # Continuous white noise acceleration process covariance Q (8x8)
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt3 * dt

        Q = np.zeros((8, 8), dtype=np.float64)
        for i, sigma_a in [(0, self.sigma_a_pos), (1, self.sigma_a_pos),
                          (2, self.sigma_a_size), (3, self.sigma_a_size)]:
            q_var = sigma_a ** 2
            Q[i, i] = 0.25 * dt4 * q_var
            Q[i, i + 4] = 0.5 * dt3 * q_var
            Q[i + 4, i] = 0.5 * dt3 * q_var
            Q[i + 4, i + 4] = dt2 * q_var

        # Prior state and covariance prediction
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

        # Apply camera ego-motion transformation if reliable
        if (
            ego_motion is not None
            and getattr(ego_motion, "is_reliable", False)
            and getattr(ego_motion, "transform_matrix", None) is not None
        ):
            M = ego_motion.transform_matrix
            xc, yc, w, h = self.x[:4]
            # Affine transformation of center coordinate: [xc', yc'] = M * [xc, yc, 1]^T
            xc_new = M[0, 0] * xc + M[0, 1] * yc + M[0, 2]
            yc_new = M[1, 0] * xc + M[1, 1] * yc + M[1, 2]
            s = max(0.2, min(2.0, getattr(ego_motion, "scale", 1.0)))
            w_new = w * s
            h_new = h * s

            self.x[0] = max(0.005, min(0.995, xc_new))
            self.x[1] = max(0.005, min(0.995, yc_new))
            self.x[2] = max(0.005, min(0.990, w_new))
            self.x[3] = max(0.005, min(0.990, h_new))

            # Transform velocity components under rotation and scaling
            vx, vy = self.x[4], self.x[5]
            self.x[4] = M[0, 0] * vx + M[0, 1] * vy
            self.x[5] = M[1, 0] * vx + M[1, 1] * vy
            self.x[6] *= s
            self.x[7] *= s

            # Full 8x8 block Jacobian for state transformation:
            # Position and velocity blocks rotate by 2x2 affine matrix R = M[:2, :2]
            # Size and size-rate blocks scale uniformly by s
            R = M[:2, :2]
            J = np.zeros((8, 8), dtype=np.float64)
            J[0:2, 0:2] = R
            J[2:4, 2:4] = np.diag([s, s])
            J[4:6, 4:6] = R
            J[6:8, 6:8] = np.diag([s, s])

            ego_conf = float(getattr(ego_motion, "confidence", 0.5))
            q_ego_var = (0.01 ** 2) * max(0.1, 1.0 - ego_conf)
            Q_ego = np.diag([q_ego_var, q_ego_var, q_ego_var, q_ego_var,
                             q_ego_var * 2, q_ego_var * 2, q_ego_var * 2, q_ego_var * 2])
            self.P = J @ self.P @ J.T + Q_ego
            self.P = 0.5 * (self.P + self.P.T)
            # Guarantee positive semi-definiteness via eigenvalue thresholding
            w_eig, v_eig = np.linalg.eigh(self.P)
            w_eig = np.maximum(w_eig, 1e-8)
            self.P = v_eig @ np.diag(w_eig) @ v_eig.T
            self.P = 0.5 * (self.P + self.P.T)

        # Enforce valid box dimensions
        self.x[2] = max(0.005, self.x[2])
        self.x[3] = max(0.005, self.x[3])

        return self.get_bounding_box()

    def update(self, box: BoundingBox, timestamp: float) -> None:
        """
        Incorporates a fresh bounding box measurement into the Kalman filter state.
        Uses numerically stable Joseph form covariance update.
        """
        self.last_time = timestamp

        w = max(0.005, box.x_max - box.x_min)
        h = max(0.005, box.y_max - box.y_min)
        xc = box.center_x
        yc = box.center_y
        z = np.array([xc, yc, w, h], dtype=np.float64)

        # Innovation (measurement residual)
        y = z - self.H @ self.x

        # Innovation covariance
        S = self.H @ self.P @ self.H.T + self.R

        # Kalman gain K = P H^T S^-1
        K = self.P @ self.H.T @ np.linalg.inv(S)

        # Posterior state
        self.x = self.x + K @ y

        # Numerically stable Joseph form covariance update: P = (I - KH) P (I - KH)^T + K R K^T
        I_KH = np.eye(8, dtype=np.float64) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ self.R @ K.T

        # Enforce valid box dimensions
        self.x[2] = max(0.005, self.x[2])
        self.x[3] = max(0.005, self.x[3])

    def get_bounding_box(self) -> BoundingBox:
        """Extracts normalized BoundingBox from current state estimate [x_c, y_c, w, h]."""
        xc, yc, w, h = self.x[:4]
        x_min = max(0.0, min(0.99, xc - w / 2.0))
        y_min = max(0.0, min(0.99, yc - h / 2.0))
        x_max = min(1.0, max(x_min + 0.005, xc + w / 2.0))
        y_max = min(1.0, max(y_min + 0.005, yc + h / 2.0))
        return BoundingBox(
            x_min=round(float(x_min), 4),
            y_min=round(float(y_min), 4),
            x_max=round(float(x_max), 4),
            y_max=round(float(y_max), 4)
        )


@dataclass
class TrackedObject:
    """Represents a temporally confirmed object instance tracked across frames."""
    track_id: int
    class_name: str
    confidence: float
    box: BoundingBox
    sector: str
    first_seen: float
    last_seen: float
    hit_streak: int = 1
    miss_streak: int = 0
    state: TrackState = TrackState.TENTATIVE
    movement: MovementDirection = MovementDirection.UNKNOWN
    history: List[Tuple[float, BoundingBox]] = field(default_factory=list)
    speed_x: float = 0.0
    growth_rate_h: float = 0.0
    announced: bool = False
    last_announced_sector: Optional[str] = None
    last_announced_box: Optional[BoundingBox] = None
    last_announced_movement: MovementDirection = MovementDirection.UNKNOWN
    last_announced_time: float = 0.0
    last_announced_language: Optional[str] = None
    kf: Optional[KalmanBoxTracker] = field(default=None, repr=False)
    predicted_box: Optional[BoundingBox] = None
    compensated_speed_x: float = 0.0
    compensated_growth_rate_h: float = 0.0
    ego_motion_compensated: bool = False
    trajectory: Optional[TrajectoryEstimate] = None
    last_announced_trajectory: Optional[TrajectoryClassification] = None
    _trajectory_classifier: Optional[TrajectoryClassifier] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.kf is None:
            self.kf = KalmanBoxTracker(self.box, self.first_seen)
        if self.predicted_box is None:
            self.predicted_box = self.box

    @property
    def height(self) -> float:
        return max(0.0, self.box.y_max - self.box.y_min)

    @property
    def width(self) -> float:
        return max(0.0, self.box.x_max - self.box.x_min)

    def predict(self, timestamp: float, ego_motion: Optional[Any] = None) -> BoundingBox:
        """Propagates Kalman filter state forward to timestamp and updates predicted_box with optional ego-motion."""
        if self.kf is not None:
            self.predicted_box = self.kf.predict(timestamp, ego_motion=ego_motion)
        else:
            self.predicted_box = self.box
        return self.predicted_box

    def has_meaningfully_changed(self, language: Optional[str] = None) -> bool:
        """
        Determines if the object's spatial context, behavior, or target language has meaningfully
        changed since its last spoken announcement.
        Returns True if:
        - Never announced yet.
        - Target announcement language changed (e.g. ne -> en).
        - Sector changed (e.g. center -> left).
        - Movement escalated to APPROACHING when not previously announced as approaching.
        - Visual bounding box height expanded significantly (> 25%), indicating apparent approach.
        Returns False if changes are within stationary jitter thresholds.
        """
        if not self.announced:
            return True
        if language and self.last_announced_language and language != self.last_announced_language:
            return True
        if self.sector != self.last_announced_sector:
            return True
        if (
            self.movement == MovementDirection.APPROACHING
            and self.last_announced_movement != MovementDirection.APPROACHING
        ):
            return True
        if self.trajectory and self.trajectory.classification in (
            TrajectoryClassification.PATH_INTERSECTION,
            TrajectoryClassification.CROSSING,
        ):
            if self.last_announced_trajectory != self.trajectory.classification:
                return True
        if self.last_announced_box is not None:
            prev_h = max(0.001, self.last_announced_box.y_max - self.last_announced_box.y_min)
            curr_h = max(0.001, self.box.y_max - self.box.y_min)
            if (curr_h - prev_h) / prev_h > 0.25:
                return True
        return False

    def mark_announced(self, timestamp: float, language: Optional[str] = None) -> None:
        """Updates persistent announcement state records upon successful dispatch."""
        self.announced = True
        self.last_announced_sector = self.sector
        self.last_announced_box = self.box
        self.last_announced_movement = self.movement
        self.last_announced_time = timestamp
        if self.trajectory:
            self.last_announced_trajectory = self.trajectory.classification
        if language:
            self.last_announced_language = language

    def update(
        self,
        detection: Detection,
        timestamp: float,
        min_hits: int = 2,
        ego_motion: Optional[Any] = None
    ) -> None:
        """Updates track with a fresh frame detection and estimates movement trajectory."""
        if self.kf is not None:
            self.kf.update(detection.box, timestamp)

        self.box = detection.box
        self.predicted_box = self.box
        self.confidence = detection.confidence
        self.sector = classify_sector(self.box, current_sector=self.sector)
        self.last_seen = timestamp
        self.hit_streak += 1
        self.miss_streak = 0

        if self.hit_streak >= min_hits:
            self.state = TrackState.CONFIRMED

        self.history.append((timestamp, detection.box))
        if len(self.history) > 10:
            self.history.pop(0)

        self._estimate_movement(ego_motion=ego_motion)

    def _estimate_movement(self, ego_motion: Optional[Any] = None) -> None:
        """
        Estimates object movement using filtered Kalman velocities and ego-motion compensation.
        Never presents speculative motion as a confirmed fact.
        """
        if len(self.history) < 3:
            self.movement = MovementDirection.UNKNOWN
            return

        t_first, box_first = self.history[0]
        t_last, box_last = self.history[-1]
        dt = t_last - t_first
        h_last = max(0.001, box_last.y_max - box_last.y_min)

        if dt < 0.10:
            self.movement = MovementDirection.UNKNOWN
            return

        # Lateral movement (center_x delta per second) and apparent bounding box expansion (height delta per second)
        has_ego = (
            ego_motion is not None
            and getattr(ego_motion, "is_reliable", False)
            and getattr(ego_motion, "dt", 0.0) > 0.001
        )
        has_ego_transform = has_ego and getattr(ego_motion, "transform_matrix", None) is not None

        if has_ego:
            v_x_ego = getattr(ego_motion, "dx", 0.0) / ego_motion.dt
            v_h_ego = (getattr(ego_motion, "scale", 1.0) - 1.0) * h_last / ego_motion.dt
        else:
            v_x_ego = 0.0
            v_h_ego = 0.0

        if self.kf is not None and self.hit_streak >= 3:
            # If kf prediction transformed position with ego-motion transform_matrix,
            # then kf.x[4] and kf.x[7] are ALREADY world/compensated velocities!
            if has_ego_transform:
                self.compensated_speed_x = round(float(self.kf.x[4]), 3)
                self.compensated_growth_rate_h = round(float(self.kf.x[7]), 3)
                self.speed_x = round(float(self.compensated_speed_x + v_x_ego), 3)
                self.growth_rate_h = round(float(self.compensated_growth_rate_h + v_h_ego), 3)
                self.ego_motion_compensated = True
            elif has_ego:
                # kf was not ego-transformed; kf.x[4] represents apparent image velocity
                self.speed_x = round(float(self.kf.x[4]), 3)
                self.growth_rate_h = round(float(self.kf.x[7]), 3)
                self.compensated_speed_x = round(float(self.speed_x - v_x_ego), 3)
                self.compensated_growth_rate_h = round(float(self.growth_rate_h - v_h_ego), 3)
                self.ego_motion_compensated = True
            else:
                self.speed_x = round(float(self.kf.x[4]), 3)
                self.growth_rate_h = round(float(self.kf.x[7]), 3)
                self.compensated_speed_x = self.speed_x
                self.compensated_growth_rate_h = self.growth_rate_h
                self.ego_motion_compensated = False
        else:
            # History-based fallback (detections are in camera image coordinates)
            dx = box_last.center_x - box_first.center_x
            self.speed_x = round(dx / dt, 3)
            h_first = max(0.001, box_first.y_max - box_first.y_min)
            h_last = max(0.001, box_last.y_max - box_last.y_min)
            dh = h_last - h_first
            self.growth_rate_h = round(dh / dt, 3)

            if has_ego:
                self.compensated_speed_x = round(float(self.speed_x - v_x_ego), 3)
                self.compensated_growth_rate_h = round(float(self.growth_rate_h - v_h_ego), 3)
                self.ego_motion_compensated = True
            else:
                self.compensated_speed_x = self.speed_x
                self.compensated_growth_rate_h = self.growth_rate_h
                self.ego_motion_compensated = False

        effective_speed_x = self.compensated_speed_x
        effective_growth_rate_h = self.compensated_growth_rate_h

        # Distinguish significant movement from stationary noise jitter
        if effective_growth_rate_h > 0.12 and h_last > 0.18:
            self.movement = MovementDirection.APPROACHING
        elif effective_growth_rate_h < -0.15:
            self.movement = MovementDirection.RECEDING
        elif effective_speed_x < -0.20:
            self.movement = MovementDirection.MOVING_LEFT
        elif effective_speed_x > 0.20:
            self.movement = MovementDirection.MOVING_RIGHT
        else:
            self.movement = MovementDirection.STATIONARY

        # Short-horizon path trajectory & intersection estimation
        if self._trajectory_classifier is None:
            self._trajectory_classifier = TrajectoryClassifier()
        self.trajectory = self._trajectory_classifier.classify(self, ego_motion=ego_motion)

    def mark_missed(self, max_age: int = 15) -> None:
        """Marks track missed in current frame. Transitions to LOST or DELETED while coasting along predicted trajectory."""
        self.miss_streak += 1
        if self.predicted_box is not None:
            self.box = self.predicted_box
            self.sector = classify_sector(self.box, current_sector=self.sector)
        if self.miss_streak >= max_age:
            self.state = TrackState.DELETED
        else:
            self.state = TrackState.LOST


class TemporalTracker:
    """
    Real-time, lightweight Kalman-based IoU temporal tracker with optional ego-motion compensation.
    Maintains persistent object identity across camera frames, smooths trajectories,
    predicts motion across occlusions, and isolates processing on CPU.
    """

    def __init__(
        self,
        iou_threshold: float = 0.15,
        min_hits: int = 1,
        max_age: int = 15
    ):
        self.iou_threshold = iou_threshold
        self.min_hits = min_hits
        self.max_age = max_age
        self._next_track_id = 1
        self.tracks: List[TrackedObject] = []

    def update(
        self,
        detections: List[Detection],
        timestamp: float,
        ego_motion: Optional[Any] = None
    ) -> List[TrackedObject]:
        """
        Associates fresh detections with active tracks using predicted position and IoU matching.
        Compensates for camera ego-motion when a reliable estimate is provided.
        Creates tentative tracks for new objects and prunes expired tracks.
        """
        # Partition active candidate tracks
        active_tracks = [t for t in self.tracks if t.state != TrackState.DELETED]

        # Step 0: Predict track positions ahead of association (with ego-motion)
        for track in active_tracks:
            track.predict(timestamp, ego_motion=ego_motion)

        unmatched_detections = list(range(len(detections)))
        unmatched_tracks = list(range(len(active_tracks)))
        matches: List[Tuple[int, int]] = []

        if active_tracks and detections:
            # Build IoU cost matrix between predicted tracks and detections of same class
            cost_matrix = []
            for t_idx, track in enumerate(active_tracks):
                row = []
                for d_idx, det in enumerate(detections):
                    if track.class_name == det.class_name:
                        # Associate with Kalman predicted box
                        target_box = track.predicted_box if track.predicted_box is not None else track.box
                        iou = compute_iou(target_box, det.box)
                    else:
                        iou = 0.0
                    row.append(iou)
                cost_matrix.append(row)

            # Greedy matching for highest IoU pairs >= iou_threshold
            matched_det_indices = set()
            matched_track_indices = set()

            # Flatten candidates sorted by descending IoU
            candidates = []
            for t_idx in range(len(active_tracks)):
                for d_idx in range(len(detections)):
                    score = cost_matrix[t_idx][d_idx]
                    if score >= self.iou_threshold:
                        candidates.append((score, t_idx, d_idx))

            candidates.sort(key=lambda x: x[0], reverse=True)

            for score, t_idx, d_idx in candidates:
                if t_idx not in matched_track_indices and d_idx not in matched_det_indices:
                    matches.append((t_idx, d_idx))
                    matched_track_indices.add(t_idx)
                    matched_det_indices.add(d_idx)

            unmatched_tracks = [t for t in range(len(active_tracks)) if t not in matched_track_indices]
            unmatched_detections = [d for d in range(len(detections)) if d not in matched_det_indices]

        # 1. Update matched tracks
        for t_idx, d_idx in matches:
            active_tracks[t_idx].update(
                detections[d_idx],
                timestamp,
                min_hits=self.min_hits,
                ego_motion=ego_motion
            )

        # 2. Mark unmatched tracks as missed (coasts along predicted Kalman trajectory)
        for t_idx in unmatched_tracks:
            active_tracks[t_idx].mark_missed(max_age=self.max_age)

        # 3. Create new tentative tracks for unmatched detections
        for d_idx in unmatched_detections:
            det = detections[d_idx]
            new_track = TrackedObject(
                track_id=self._next_track_id,
                class_name=det.class_name,
                confidence=det.confidence,
                box=det.box,
                sector=det.sector,
                first_seen=timestamp,
                last_seen=timestamp,
                hit_streak=1,
                miss_streak=0,
                state=TrackState.TENTATIVE if self.min_hits > 1 else TrackState.CONFIRMED,
                history=[(timestamp, det.box)]
            )
            self._next_track_id += 1
            active_tracks.append(new_track)

        # 4. Prune deleted tracks
        self.tracks = [t for t in active_tracks if t.state != TrackState.DELETED]
        return self.tracks

    def get_confirmed_tracks(self) -> List[TrackedObject]:
        """Returns only temporally confirmed tracks."""
        return [t for t in self.tracks if t.state == TrackState.CONFIRMED]

    def reset(self) -> None:
        """Purges all tracking state and resets track counter."""
        self.tracks.clear()
        self._next_track_id = 1
