"""
TRINETRA Spatial Positioning Logic
Computes horizontal zones (Left, Straight Ahead, Right), proximity estimations,
threat prioritization, and natural navigation guidance phrases.
"""

from enum import Enum
from typing import NamedTuple, Tuple


class Zone(str, Enum):
    """Horizontal spatial partition relative to the user's field of view."""
    LEFT = "Left"
    CENTER = "Straight Ahead"
    RIGHT = "Right"

    def get_speech_description(self) -> str:
        """Returns natural phrasing for speech synthesizer."""
        if self == Zone.LEFT:
            return "on your left"
        elif self == Zone.CENTER:
            return "straight ahead"
        elif self == Zone.RIGHT:
            return "on your right"
        return "nearby"


class Proximity(str, Enum):
    """Estimated physical distance category based on optical geometry."""
    IMMEDIATE = "Immediate"      # < 1.0 - 1.5m, urgent collision risk
    APPROACHING = "Approaching"  # 1.5 - 3.5m, upcoming obstacle
    DISTANT = "Distant"          # > 3.5m, peripheral awareness


class SpatialAssessment(NamedTuple):
    """Result of spatial calculation on a bounding box."""
    zone: Zone
    proximity: Proximity
    threat_level: int           # 1 (Highest/Urgent) to 5 (Lowest/Informational)
    norm_center_x: float        # Normalized center X [0.0, 1.0]
    norm_center_y: float        # Normalized center Y [0.0, 1.0]
    norm_height: float          # Normalized bbox height [0.0, 1.0]
    bottom_y_ratio: float       # Bottom edge Y ratio [0.0, 1.0]
    estimated_distance_m: float # Heuristic distance estimate in meters
    speech_phrase: str          # Concise audio warning message


class SpatialAnalyzer:
    """
    Analyzes visual bounding boxes within the camera frame to determine
    spatial placement, relative distance, and navigation urgency.
    """

    def __init__(
        self,
        left_zone_boundary: float = 0.35,
        right_zone_boundary: float = 0.65,
        immediate_height_ratio: float = 0.42,
        approaching_height_ratio: float = 0.22,
        bottom_proximity_ratio: float = 0.85
    ):
        self.left_boundary = left_zone_boundary
        self.right_boundary = right_zone_boundary
        self.immediate_height_ratio = immediate_height_ratio
        self.approaching_height_ratio = approaching_height_ratio
        self.bottom_proximity_ratio = bottom_proximity_ratio

    def calculate_spatial_position(
        self,
        bbox: Tuple[int, int, int, int],
        frame_width: int,
        frame_height: int,
        label: str = "Obstacle"
    ) -> SpatialAssessment:
        """
        Calculates spatial zone, proximity, and urgency for a given bounding box.

        Args:
            bbox: (x1, y1, x2, y2) pixel coordinates
            frame_width: Image width in pixels
            frame_height: Image height in pixels
            label: Detected object class label (e.g. 'chair', 'person')

        Returns:
            SpatialAssessment containing computed metrics and guidance phrase.
        """
        x1, y1, x2, y2 = bbox
        bbox_w = max(1, x2 - x1)
        bbox_h = max(1, y2 - y1)

        cx = x1 + (bbox_w / 2.0)
        cy = y1 + (bbox_h / 2.0)

        norm_cx = max(0.0, min(1.0, cx / float(frame_width)))
        norm_cy = max(0.0, min(1.0, cy / float(frame_height)))
        norm_h = max(0.0, min(1.0, bbox_h / float(frame_height)))
        bottom_ratio = max(0.0, min(1.0, y2 / float(frame_height)))

        # 1. Determine Horizontal Zone
        if norm_cx < self.left_boundary:
            zone = Zone.LEFT
        elif norm_cx > self.right_boundary:
            zone = Zone.RIGHT
        else:
            zone = Zone.CENTER

        # 2. Determine Proximity
        # Objects having tall bounding boxes or touching the bottom of the viewport
        # are physically closer to the user's feet/ground path.
        if norm_h >= self.immediate_height_ratio or bottom_ratio >= self.bottom_proximity_ratio:
            proximity = Proximity.IMMEDIATE
            # Approximate distance: 0.5m - 1.5m
            est_distance = max(0.5, 1.5 * (1.0 - norm_h))
        elif norm_h >= self.approaching_height_ratio or bottom_ratio >= 0.70:
            proximity = Proximity.APPROACHING
            # Approximate distance: 1.5m - 3.5m
            est_distance = 1.5 + (2.0 * (1.0 - (norm_h / self.immediate_height_ratio)))
        else:
            proximity = Proximity.DISTANT
            # Approximate distance: > 3.5m
            est_distance = 3.5 + (3.0 * (1.0 - (norm_h / self.approaching_height_ratio)))

        # 3. Determine Threat Urgency Level (1 = Urgent to 5 = Low)
        # Immediate hazard directly in the walking path is Priority 1
        if zone == Zone.CENTER and proximity == Proximity.IMMEDIATE:
            threat_level = 1
        elif zone == Zone.CENTER and proximity == Proximity.APPROACHING:
            threat_level = 2
        elif (zone in (Zone.LEFT, Zone.RIGHT)) and proximity == Proximity.IMMEDIATE:
            threat_level = 2
        elif (zone in (Zone.LEFT, Zone.RIGHT)) and proximity == Proximity.APPROACHING:
            threat_level = 3
        else:
            threat_level = 4

        # 4. Formulate Natural Speech Phrase
        clean_label = label.capitalize()
        if threat_level == 1:
            phrase = f"Caution! {clean_label} directly ahead, close."
        elif threat_level == 2:
            if zone == Zone.CENTER:
                phrase = f"{clean_label} ahead, approaching."
            else:
                phrase = f"{clean_label} close {zone.get_speech_description()}."
        elif threat_level == 3:
            phrase = f"{clean_label} {zone.get_speech_description()}."
        else:
            phrase = f"{clean_label} in distance {zone.get_speech_description()}."

        return SpatialAssessment(
            zone=zone,
            proximity=proximity,
            threat_level=threat_level,
            norm_center_x=norm_cx,
            norm_center_y=norm_cy,
            norm_height=norm_h,
            bottom_y_ratio=bottom_ratio,
            estimated_distance_m=round(est_distance, 1),
            speech_phrase=phrase
        )
