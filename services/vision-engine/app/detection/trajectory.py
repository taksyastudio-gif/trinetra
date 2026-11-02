"""
Trinetra Crossing Vector & Path-Intersection Classification Layer
Estimates object trajectories relative to the user's projected walking corridor.
Distinguishes genuine environmental movement from camera motion, evaluates short-horizon
path intersections, and maintains conservative, honest confidence bounds without claiming
metric depth or certified collision avoidance.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.detection.types import BoundingBox

logger = logging.getLogger("trinetra.trajectory")


class TrajectoryClassification(str, Enum):
    CROSSING = "crossing"
    APPROACHING = "approaching"
    MOVING_AWAY = "moving_away"
    PARALLEL = "parallel"
    PATH_INTERSECTION = "path_intersection"
    STATIONARY = "stationary"
    UNCERTAIN = "uncertain"


class CrossingDirection(str, Enum):
    LEFT_TO_RIGHT = "left_to_right"
    RIGHT_TO_LEFT = "right_to_left"
    NONE = "none"


@dataclass(frozen=True)
class WalkingCorridor:
    """
    Projected image-space walking corridor representing the user's forward path.
    Coordinates are normalized to [0.0, 1.0] in image space.
    """
    x_min: float = 0.35
    x_max: float = 0.65
    y_min: float = 0.20
    y_max: float = 1.00

    def contains_point(self, x: float, y: float) -> bool:
        """Checks if a point falls within the 2D corridor."""
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max

    def overlaps_box(self, box: BoundingBox) -> bool:
        """Checks if an axis-aligned bounding box intersects the walking corridor."""
        x_overlap = not (box.x_max < self.x_min or box.x_min > self.x_max)
        y_overlap = not (box.y_max < self.y_min or box.y_min > self.y_max)
        return x_overlap and y_overlap

    def horizontal_overlap_ratio(self, box: BoundingBox) -> float:
        """Computes fraction of the box's horizontal extent that overlaps the corridor."""
        box_w = max(0.001, box.x_max - box.x_min)
        inter_x_min = max(self.x_min, box.x_min)
        inter_x_max = min(self.x_max, box.x_max)
        if inter_x_max <= inter_x_min:
            return 0.0
        return (inter_x_max - inter_x_min) / box_w


@dataclass
class TrajectoryEstimate:
    """Detailed spatial trajectory assessment for a tracked entity."""
    classification: TrajectoryClassification
    crossing_direction: CrossingDirection = CrossingDirection.NONE
    intersects_path: bool = False
    time_to_corridor: Optional[float] = None
    confidence: float = 0.0
    uncertainty_margin: float = 0.0
    projected_positions: List[Tuple[float, float]] = field(default_factory=list)
    rationale: str = ""


class TrajectoryClassifier:
    """
    Evaluates tracked objects to determine relative trajectory and path-intersection risk.
    Uses compensated Kalman velocities where reliable and guards against speculative claims.
    """

    def __init__(
        self,
        corridor: Optional[WalkingCorridor] = None,
        min_hits: int = 3,
        max_miss_streak: int = 2,
        min_detection_confidence: float = 0.40,
        prediction_horizon_sec: float = 2.0,
        prediction_step_sec: float = 0.20,
        lateral_speed_threshold: float = 0.08,
        expansion_speed_threshold: float = 0.08,
        stationary_speed_threshold: float = 0.04,
        max_position_uncertainty: float = 0.15,
    ):
        self.corridor = corridor if corridor is not None else WalkingCorridor()
        self.min_hits = min_hits
        self.max_miss_streak = max_miss_streak
        self.min_detection_confidence = min_detection_confidence
        self.prediction_horizon_sec = prediction_horizon_sec
        self.prediction_step_sec = prediction_step_sec
        self.lateral_speed_threshold = lateral_speed_threshold
        self.expansion_speed_threshold = expansion_speed_threshold
        self.stationary_speed_threshold = stationary_speed_threshold
        self.max_position_uncertainty = max_position_uncertainty

    def classify(
        self,
        track: Any,
        ego_motion: Optional[Any] = None,
        corridor: Optional[WalkingCorridor] = None,
    ) -> TrajectoryEstimate:
        """
        Classifies a single TrackedObject into one of the 7 trajectory states.
        Enforces evidence gates before declaring dynamic movement.
        """
        active_corridor = corridor if corridor is not None else self.corridor

        # -------------------------------------------------------------
        # Gate 1: Track Lifecycle and Observation Fidelity
        # -------------------------------------------------------------
        if getattr(track, "hit_streak", 0) < self.min_hits:
            return TrajectoryEstimate(
                classification=TrajectoryClassification.UNCERTAIN,
                confidence=0.0,
                rationale=f"Insufficient observation history ({getattr(track, 'hit_streak', 0)} < {self.min_hits} hits)"
            )

        if getattr(track, "miss_streak", 0) > self.max_miss_streak:
            return TrajectoryEstimate(
                classification=TrajectoryClassification.UNCERTAIN,
                confidence=0.0,
                rationale=f"Missing detections exceed tolerance ({getattr(track, 'miss_streak', 0)} frames missed)"
            )

        if getattr(track, "confidence", 1.0) < self.min_detection_confidence:
            return TrajectoryEstimate(
                classification=TrajectoryClassification.UNCERTAIN,
                confidence=float(getattr(track, "confidence", 0.0)),
                rationale="Detection confidence below minimum threshold"
            )

        # -------------------------------------------------------------
        # Gate 2: Camera Ego-Motion Reliability
        # -------------------------------------------------------------
        # If ego_motion is provided but explicitly marked unreliable, apparent velocity is ambiguous
        if ego_motion is not None and not getattr(ego_motion, "is_reliable", True):
            return TrajectoryEstimate(
                classification=TrajectoryClassification.UNCERTAIN,
                confidence=0.20,
                rationale="Unreliable camera ego-motion prevents distinguishing head turn from physical motion"
            )

        # -------------------------------------------------------------
        # Gate 3: Kalman State & Covariance Extraction
        # -------------------------------------------------------------
        kf = getattr(track, "kf", None)
        if kf is None or not hasattr(kf, "x") or not hasattr(kf, "P"):
            return TrajectoryEstimate(
                classification=TrajectoryClassification.UNCERTAIN,
                confidence=0.0,
                rationale="No active Kalman filter state available"
            )

        xc = float(kf.x[0])
        yc = float(kf.x[1])
        w = max(0.01, float(kf.x[2]))
        h = max(0.01, float(kf.x[3]))
        vx = float(kf.x[4])
        vy = float(kf.x[5])
        vw = float(kf.x[6])
        vh = float(kf.x[7])

        # Spatial uncertainty from covariance matrix
        var_x = float(max(1e-8, kf.P[0, 0]))
        var_y = float(max(1e-8, kf.P[1, 1]))
        pos_uncertainty = math.sqrt(var_x + var_y)

        if pos_uncertainty > self.max_position_uncertainty:
            return TrajectoryEstimate(
                classification=TrajectoryClassification.UNCERTAIN,
                confidence=max(0.1, 1.0 - (pos_uncertainty / 0.30)),
                uncertainty_margin=pos_uncertainty,
                rationale=f"High Kalman covariance uncertainty (sigma={pos_uncertainty:.3f})"
            )

        # Base confidence calculation based on hit streak, uncertainty, and detection confidence
        streak_factor = min(1.0, getattr(track, "hit_streak", 1) / 5.0)
        uncertainty_factor = max(0.1, 1.0 - (pos_uncertainty / self.max_position_uncertainty))
        det_conf = float(getattr(track, "confidence", 0.8))
        est_confidence = round(float(streak_factor * uncertainty_factor * det_conf), 3)

        # -------------------------------------------------------------
        # Gate 4: Stationary Deadband
        # -------------------------------------------------------------
        is_stationary_x = abs(vx) < self.stationary_speed_threshold
        is_stationary_y = abs(vy) < self.stationary_speed_threshold
        is_stationary_h = abs(vh) < self.stationary_speed_threshold

        if is_stationary_x and is_stationary_y and is_stationary_h:
            # Check if stationary obstacle is inside or outside the walking corridor
            current_box = track.box
            overlaps = active_corridor.overlaps_box(current_box)
            return TrajectoryEstimate(
                classification=TrajectoryClassification.STATIONARY,
                crossing_direction=CrossingDirection.NONE,
                intersects_path=overlaps,
                time_to_corridor=0.0 if overlaps else None,
                confidence=est_confidence,
                uncertainty_margin=pos_uncertainty,
                projected_positions=[(xc, yc)],
                rationale="Object velocity is within stationary deadband"
            )

        # -------------------------------------------------------------
        # Gate 5: Short-Horizon Trajectory Projection
        # -------------------------------------------------------------
        steps = max(1, int(self.prediction_horizon_sec / self.prediction_step_sec))
        projected_positions: List[Tuple[float, float]] = [(xc, yc)]

        time_to_corridor: Optional[float] = None
        intersects_corridor = False

        current_box = track.box
        currently_in_corridor = active_corridor.overlaps_box(current_box)
        if currently_in_corridor:
            intersects_corridor = True
            time_to_corridor = 0.0

        for s_idx in range(1, steps + 1):
            t_offset = s_idx * self.prediction_step_sec
            p_x = xc + vx * t_offset
            p_y = yc + vy * t_offset
            p_w = max(0.01, w + vw * t_offset)
            p_h = max(0.01, h + vh * t_offset)
            projected_positions.append((round(p_x, 3), round(p_y, 3)))

            proj_box = BoundingBox(
                x_min=p_x - p_w / 2.0,
                y_min=p_y - p_h / 2.0,
                x_max=p_x + p_w / 2.0,
                y_max=p_y + p_h / 2.0
            )

            if active_corridor.overlaps_box(proj_box):
                if not intersects_corridor:
                    intersects_corridor = True
                    time_to_corridor = round(t_offset, 2)

        # -------------------------------------------------------------
        # Gate 6: Directional Classification Synthesis
        # -------------------------------------------------------------
        # Lateral movement
        is_moving_lateral = abs(vx) >= self.lateral_speed_threshold
        crossing_dir = CrossingDirection.NONE
        if vx >= self.lateral_speed_threshold:
            crossing_dir = CrossingDirection.LEFT_TO_RIGHT
        elif vx <= -self.lateral_speed_threshold:
            crossing_dir = CrossingDirection.RIGHT_TO_LEFT

        # Check if object trajectory is strictly confined to a flank alongside the corridor
        is_strictly_parallel_flank = (
            not intersects_corridor
            and (
                (xc + w/2.0 < active_corridor.x_min and all(p[0] < active_corridor.x_min for p in projected_positions))
                or (xc - w/2.0 > active_corridor.x_max and all(p[0] > active_corridor.x_max for p in projected_positions))
            )
        )

        # Expansion/recession movement (approaching / moving away)
        # Direct approach is indicated by bounding box growth rate (vh) or vertical motion heading towards user
        is_expanding = (vh >= self.expansion_speed_threshold) or (
            vy >= self.expansion_speed_threshold and h >= 0.15 and not is_strictly_parallel_flank
        )
        is_receding = (vh <= -self.expansion_speed_threshold) or (vy <= -self.expansion_speed_threshold)

        # Path intersection check:
        # A trajectory is classified as PATH_INTERSECTION when:
        # 1. It is outside the corridor and its predicted trajectory enters the corridor
        # 2. Or it is in the corridor and actively approaching or crossing within it
        if intersects_corridor:
            if not currently_in_corridor:
                # Outside moving in
                return TrajectoryEstimate(
                    classification=TrajectoryClassification.PATH_INTERSECTION,
                    crossing_direction=crossing_dir,
                    intersects_path=True,
                    time_to_corridor=time_to_corridor,
                    confidence=est_confidence,
                    uncertainty_margin=pos_uncertainty,
                    projected_positions=projected_positions,
                    rationale=f"Object trajectory projects intersection with walking corridor in {time_to_corridor}s"
                )
            elif is_expanding or is_moving_lateral:
                return TrajectoryEstimate(
                    classification=TrajectoryClassification.PATH_INTERSECTION,
                    crossing_direction=crossing_dir,
                    intersects_path=True,
                    time_to_corridor=0.0,
                    confidence=est_confidence,
                    uncertainty_margin=pos_uncertainty,
                    projected_positions=projected_positions,
                    rationale="Dynamic object actively moving within walking corridor"
                )

        # Pure lateral crossing (outside corridor or crossing beyond corridor bounds)
        if is_moving_lateral:
            # Check if trajectory moves parallel without intersection
            is_parallel_left = (xc + w/2.0 < active_corridor.x_min) and (all(p[0] < active_corridor.x_min for p in projected_positions))
            is_parallel_right = (xc - w/2.0 > active_corridor.x_max) and (all(p[0] > active_corridor.x_max for p in projected_positions))

            # If lateral movement is small and vertical movement dominates parallel to path
            if (is_parallel_left or is_parallel_right) and abs(vy) > abs(vx):
                return TrajectoryEstimate(
                    classification=TrajectoryClassification.PARALLEL,
                    crossing_direction=CrossingDirection.NONE,
                    intersects_path=False,
                    time_to_corridor=None,
                    confidence=est_confidence,
                    uncertainty_margin=pos_uncertainty,
                    projected_positions=projected_positions,
                    rationale="Object trajectory runs parallel alongside the walking corridor"
                )

            return TrajectoryEstimate(
                classification=TrajectoryClassification.CROSSING,
                crossing_direction=crossing_dir,
                intersects_path=False,
                time_to_corridor=None,
                confidence=est_confidence,
                uncertainty_margin=pos_uncertainty,
                projected_positions=projected_positions,
                rationale=f"Object crossing {crossing_dir.value} without path intersection"
            )

        # Approaching (outside corridor, e.g. on flanking sidewalk)
        if is_expanding:
            return TrajectoryEstimate(
                classification=TrajectoryClassification.APPROACHING,
                crossing_direction=CrossingDirection.NONE,
                intersects_path=intersects_corridor,
                time_to_corridor=time_to_corridor,
                confidence=est_confidence,
                uncertainty_margin=pos_uncertainty,
                projected_positions=projected_positions,
                rationale="Object expanding in visual field outside projected corridor"
            )

        # Moving away / receding
        if is_receding:
            return TrajectoryEstimate(
                classification=TrajectoryClassification.MOVING_AWAY,
                crossing_direction=CrossingDirection.NONE,
                intersects_path=False,
                time_to_corridor=None,
                confidence=est_confidence,
                uncertainty_margin=pos_uncertainty,
                projected_positions=projected_positions,
                rationale="Object receding away from user"
            )

        # Parallel motion: moving along flank with neither crossing nor direct approach
        is_parallel_flank = (xc < active_corridor.x_min or xc > active_corridor.x_max)
        if is_parallel_flank and not intersects_corridor:
            return TrajectoryEstimate(
                classification=TrajectoryClassification.PARALLEL,
                crossing_direction=CrossingDirection.NONE,
                intersects_path=False,
                time_to_corridor=None,
                confidence=est_confidence,
                uncertainty_margin=pos_uncertainty,
                projected_positions=projected_positions,
                rationale="Object moving parallel along flanking sector"
            )

        # Fallback to stationary if no significant motion verified
        return TrajectoryEstimate(
            classification=TrajectoryClassification.STATIONARY,
            crossing_direction=CrossingDirection.NONE,
            intersects_path=currently_in_corridor,
            time_to_corridor=0.0 if currently_in_corridor else None,
            confidence=est_confidence,
            uncertainty_margin=pos_uncertainty,
            projected_positions=projected_positions,
            rationale="No directional threshold exceeded; classified stationary"
        )
