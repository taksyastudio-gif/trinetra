"""
Trinetra Scene & Walkable-Space Understanding Layer
Interprets tracked objects over time, estimates walkable regions, assesses collision risks,
and distinguishes directly observed facts from uncertain spatial inferences.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Dict, List, Optional, Set

from app.detection.tracking import MovementDirection, TrackState, TrackedObject
from app.detection.trajectory import TrajectoryClassification, TrajectoryEstimate

logger = logging.getLogger("trinetra.scene")

# Classification of obstacle dynamics
VEHICLE_CLASSES: Set[str] = {"car", "bus", "truck", "motorcycle", "bicycle"}
STATIC_OBSTACLE_CLASSES: Set[str] = {"chair", "table", "dining table", "couch", "bed", "bench", "potted plant"}
BARRIER_CLASSES: Set[str] = {"stairs", "door", "stop sign", "traffic light", "fire hydrant"}


class CollisionRisk(str, Enum):
    CRITICAL = "critical"      # Immediate hazard: approaching vehicle or ground obstruction ahead
    WARNING = "warning"        # Impeding obstacle in path of motion
    INFORMATIONAL = "informational"  # Peripheral or distant object
    CLEAR = "clear"            # No significant collision threat detected


@dataclass
class WalkablePath:
    """Represents honest estimation of navigable directional sectors."""
    left_clear: bool
    center_clear: bool
    right_clear: bool
    recommended_direction: Optional[str]  # "ahead", "left", "right", or None
    confidence: float  # Visual confidence in path recommendation [0.0, 1.0]
    rationale: str


@dataclass
class SceneAssessment:
    """Comprehensive interpretation of the visual scene across time."""
    frame_id: int
    timestamp: float
    confirmed_tracks: List[TrackedObject]
    crowd_count: int
    is_crowded: bool
    highest_risk: CollisionRisk
    critical_track: Optional[TrackedObject]
    path: WalkablePath
    approaching_objects: List[TrackedObject]
    path_intersecting_objects: List[TrackedObject] = field(default_factory=list)
    crossing_objects: List[TrackedObject] = field(default_factory=list)


class SceneAnalyzer:
    """
    Evaluates tracked visual entities to derive spatial scene awareness,
    walkable sector clearance, and prioritized collision hazards without claiming
    exact physical metric distance from single-camera 2D bounding boxes.
    """

    def __init__(
        self,
        crowd_threshold: int = 3,
        immediate_height_ratio: float = 0.45,
        bottom_cutoff_ratio: float = 0.85
    ):
        self.crowd_threshold = crowd_threshold
        self.immediate_height_ratio = immediate_height_ratio
        self.bottom_cutoff_ratio = bottom_cutoff_ratio

    def analyze_scene(
        self,
        tracks: List[TrackedObject],
        frame_id: int,
        timestamp: float
    ) -> SceneAssessment:
        """
        Synthesizes active tracked objects into an actionable SceneAssessment.
        Only relies on confirmed tracks to eliminate single-frame detector artifacts.
        """
        confirmed = [t for t in tracks if t.state == TrackState.CONFIRMED]

        # 1. Crowd aggregation: count persons in scene
        persons = [t for t in confirmed if t.class_name == "person"]
        crowd_count = len(persons)
        is_crowded = crowd_count >= self.crowd_threshold

        # 2. Sector obstacle occupancy mapping
        left_obstacles = [t for t in confirmed if t.sector == "left"]
        center_obstacles = [t for t in confirmed if t.sector == "center"]
        right_obstacles = [t for t in confirmed if t.sector == "right"]

        # 3. Collision risk evaluation
        highest_risk = CollisionRisk.CLEAR
        critical_track: Optional[TrackedObject] = None
        approaching_objects: List[TrackedObject] = []
        path_intersecting_objects: List[TrackedObject] = []
        crossing_objects: List[TrackedObject] = []

        for track in confirmed:
            traj = getattr(track, "trajectory", None)
            if traj is not None:
                if traj.classification == TrajectoryClassification.PATH_INTERSECTION:
                    path_intersecting_objects.append(track)
                elif traj.classification == TrajectoryClassification.CROSSING:
                    crossing_objects.append(track)

            is_vehicle = track.class_name in VEHICLE_CLASSES
            is_approaching = track.movement == MovementDirection.APPROACHING
            is_path_intersecting = (
                traj is not None
                and traj.classification == TrajectoryClassification.PATH_INTERSECTION
            )

            if is_approaching:
                approaching_objects.append(track)

            # High threat: approaching vehicle anywhere, path-intersecting vehicle, or approaching object in center
            if (is_vehicle and (is_approaching or is_path_intersecting)) or (is_approaching and track.sector == "center"):
                highest_risk = CollisionRisk.CRITICAL
                critical_track = track
                break

            # Path-intersecting obstacle or pedestrian
            if is_path_intersecting and highest_risk != CollisionRisk.CRITICAL:
                highest_risk = CollisionRisk.WARNING
                if critical_track is None:
                    critical_track = track

            # Immediate proximity: object occupying bottom ground plane or large portion of viewport
            is_immediate = (
                track.box.y_max >= self.bottom_cutoff_ratio
                or track.height >= self.immediate_height_ratio
            )
            if is_immediate and track.sector == "center":
                if highest_risk != CollisionRisk.CRITICAL:
                    highest_risk = CollisionRisk.WARNING
                    if critical_track is None:
                        critical_track = track

            elif track.sector == "center" and highest_risk == CollisionRisk.CLEAR:
                highest_risk = CollisionRisk.INFORMATIONAL

        # 4. Walkable space estimation with honest confidence
        left_blocked = any(t.height > 0.25 or t.box.y_max > 0.75 for t in left_obstacles)
        center_blocked = any(t.height > 0.20 or t.box.y_max > 0.70 for t in center_obstacles)
        right_blocked = any(t.height > 0.25 or t.box.y_max > 0.75 for t in right_obstacles)

        left_clear = not left_blocked
        center_clear = not center_blocked
        right_clear = not right_blocked

        # Only recommend direction when evidence clearly supports it
        rec_dir: Optional[str] = None
        confidence = 0.5
        rationale = "Scene analyzed"

        if center_clear:
            rec_dir = "ahead"
            confidence = 0.85
            rationale = "Center path visually clear of tracked obstacles"
        elif left_clear and not right_clear:
            rec_dir = "left"
            confidence = 0.75
            rationale = "Center blocked, left side appears clear"
        elif right_clear and not left_clear:
            rec_dir = "right"
            confidence = 0.75
            rationale = "Center blocked, right side appears clear"
        elif left_clear and right_clear:
            # Both sides clear, default to left or remain neutral
            rec_dir = "left"
            confidence = 0.70
            rationale = "Center blocked, both flanks appear clear"
        else:
            # All sectors obstructed: do not fabricate a safe path!
            rec_dir = None
            confidence = 0.90
            rationale = "All directional sectors obstructed by obstacles"

        walkable_path = WalkablePath(
            left_clear=left_clear,
            center_clear=center_clear,
            right_clear=right_clear,
            recommended_direction=rec_dir,
            confidence=confidence,
            rationale=rationale
        )

        return SceneAssessment(
            frame_id=frame_id,
            timestamp=timestamp,
            confirmed_tracks=confirmed,
            crowd_count=crowd_count,
            is_crowded=is_crowded,
            highest_risk=highest_risk,
            critical_track=critical_track,
            path=walkable_path,
            approaching_objects=approaching_objects,
            path_intersecting_objects=path_intersecting_objects,
            crossing_objects=crossing_objects,
        )
