"""
Trinetra Priority 3: Crossing Vector & Path-Intersection Classification Tests.
Validates:
1. Object crossing left-to-right.
2. Object crossing right-to-left.
3. Object moving parallel to the projected path.
4. Object approaching.
5. Object moving away.
6. Stationary object.
7. Predicted trajectory intersecting the walking corridor.
8. Predicted trajectory missing the corridor.
9. Low-confidence tracking.
10. Unreliable ego-motion.
11. Missing detections / coasting uncertainty.
12. Repeated announcement suppression.
13. Safety constraints (no 'path is safe' or 'nothing ahead' fabrications).
"""

import time
import pytest
import numpy as np

from app.audio.speaker import FakeSpeechBackend, SpeechManager
from app.detection.decision import SceneDecisionEngine
from app.detection.ego_motion import EgoMotionEstimate
from app.detection.scene import CollisionRisk, SceneAnalyzer
from app.detection.tracking import (
    MovementDirection,
    TemporalTracker,
    TrackState,
    TrackedObject,
)
from app.detection.trajectory import (
    CrossingDirection,
    TrajectoryClassification,
    TrajectoryClassifier,
    TrajectoryEstimate,
    WalkingCorridor,
)
from app.detection.types import BoundingBox, Detection
from app.localization import (
    format_crossing_announcement,
    format_moving_away_announcement,
    format_parallel_announcement,
    format_path_intersection_announcement,
)


def _simulate_track_trajectory(
    start_box: BoundingBox,
    dx_per_sec: float,
    dy_per_sec: float = 0.0,
    dh_per_sec: float = 0.0,
    frames: int = 10,
    dt: float = 0.033,
    class_name: str = "person",
    confidence: float = 0.90,
    ego_motion: any = None,
) -> TrackedObject:
    """Helper to simulate a smooth, deterministic Kalman track over multiple frames."""
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.20)
    t0 = 100.0

    w0 = start_box.x_max - start_box.x_min
    h0 = start_box.y_max - start_box.y_min
    xc0 = start_box.center_x
    yc0 = start_box.center_y

    final_tracks = []
    for f in range(frames):
        t = t0 + f * dt
        xc = xc0 + dx_per_sec * (f * dt)
        yc = yc0 + dy_per_sec * (f * dt)
        w = w0
        h = max(0.01, h0 + dh_per_sec * (f * dt))
        box = BoundingBox(xc - w/2, yc - h/2, xc + w/2, yc + h/2)
        det = Detection(class_name, confidence, box, "center" if 0.35 <= xc <= 0.65 else ("left" if xc < 0.35 else "right"))
        final_tracks = tracker.update([det], timestamp=t, ego_motion=ego_motion)

    assert len(final_tracks) == 1
    return final_tracks[0]


# =============================================================================
# 1. Crossing Left to Right
# =============================================================================
def test_crossing_left_to_right():
    """1. Object crossing left to right with positive lateral velocity."""
    start_box = BoundingBox(0.05, 0.30, 0.20, 0.70)
    track = _simulate_track_trajectory(start_box, dx_per_sec=0.15, frames=8)

    classifier = TrajectoryClassifier()
    est = classifier.classify(track)

    assert est.crossing_direction == CrossingDirection.LEFT_TO_RIGHT
    # In Part 1, moving from 0.125 towards center at 0.15/s projects intersection with [0.35, 0.65] in ~1.5s
    assert est.classification in (TrajectoryClassification.CROSSING, TrajectoryClassification.PATH_INTERSECTION)
    assert est.confidence >= 0.70

    # Localization check
    ne_text = format_crossing_announcement("person", "left_to_right", language="ne")
    en_text = format_crossing_announcement("person", "left_to_right", language="en")
    assert "मान्छे दायाँतिर बाटो काट्दै छ।" in ne_text
    assert "Person crossing to the right." in en_text


# =============================================================================
# 2. Crossing Right to Left
# =============================================================================
def test_crossing_right_to_left():
    """2. Object crossing right to left with negative lateral velocity."""
    start_box = BoundingBox(0.80, 0.30, 0.95, 0.70)
    track = _simulate_track_trajectory(start_box, dx_per_sec=-0.15, frames=8)

    classifier = TrajectoryClassifier()
    est = classifier.classify(track)

    assert est.crossing_direction == CrossingDirection.RIGHT_TO_LEFT
    assert est.classification in (TrajectoryClassification.CROSSING, TrajectoryClassification.PATH_INTERSECTION)
    assert est.confidence >= 0.70

    # Localization check
    ne_text = format_crossing_announcement("person", "right_to_left", language="ne")
    en_text = format_crossing_announcement("person", "right_to_left", language="en")
    assert "मान्छे बायाँतिर बाटो काट्दै छ।" in ne_text
    assert "Person crossing to the left." in en_text


# =============================================================================
# 3. Object Moving Parallel to Projected Path
# =============================================================================
def test_moving_parallel_to_projected_path():
    """3. Object moving along the left flank without intersecting the walking corridor."""
    # Stays on flank x in [0.10, 0.25], moving forward (dy > 0)
    start_box = BoundingBox(0.10, 0.20, 0.25, 0.50)
    track = _simulate_track_trajectory(start_box, dx_per_sec=0.00, dy_per_sec=0.12, frames=8)

    classifier = TrajectoryClassifier(corridor=WalkingCorridor(x_min=0.35, x_max=0.65))
    est = classifier.classify(track)

    assert est.classification == TrajectoryClassification.PARALLEL
    assert not est.intersects_path
    assert est.time_to_corridor is None

    # Localization check
    ne_text = format_parallel_announcement("person", "left", language="ne")
    en_text = format_parallel_announcement("person", "left", language="en")
    assert "समानान्तर जाँदै छ।" in ne_text
    assert "Person moving alongside, left." in en_text


# =============================================================================
# 4. Object Approaching
# =============================================================================
def test_object_approaching():
    """4. Object expanding significantly in height (approaching user)."""
    start_box = BoundingBox(0.10, 0.30, 0.25, 0.55)
    # Flank object expanding rapidly without entering center corridor
    track = _simulate_track_trajectory(start_box, dx_per_sec=0.0, dh_per_sec=0.25, frames=8)

    classifier = TrajectoryClassifier(corridor=WalkingCorridor(x_min=0.35, x_max=0.65))
    est = classifier.classify(track)

    assert est.classification == TrajectoryClassification.APPROACHING
    assert est.confidence >= 0.60


# =============================================================================
# 5. Object Moving Away
# =============================================================================
def test_object_moving_away():
    """5. Object shrinking in size (moving away from user)."""
    start_box = BoundingBox(0.40, 0.30, 0.60, 0.80)
    track = _simulate_track_trajectory(start_box, dx_per_sec=0.0, dh_per_sec=-0.20, frames=8)

    classifier = TrajectoryClassifier()
    est = classifier.classify(track)

    assert est.classification == TrajectoryClassification.MOVING_AWAY
    assert not est.intersects_path

    # Localization check
    ne_text = format_moving_away_announcement("person", "center", language="ne")
    en_text = format_moving_away_announcement("person", "center", language="en")
    assert "टाढिँदै छ।" in ne_text
    assert "Person moving away, ahead." in en_text


# =============================================================================
# 6. Stationary Object
# =============================================================================
def test_stationary_object():
    """6. Object with near-zero velocities classified as stationary."""
    start_box = BoundingBox(0.40, 0.40, 0.60, 0.70)
    track = _simulate_track_trajectory(start_box, dx_per_sec=0.001, dy_per_sec=0.001, frames=8)

    classifier = TrajectoryClassifier()
    est = classifier.classify(track)

    assert est.classification == TrajectoryClassification.STATIONARY
    assert est.crossing_direction == CrossingDirection.NONE
    assert est.confidence >= 0.70


# =============================================================================
# 7. Predicted Trajectory Intersecting Corridor
# =============================================================================
def test_predicted_trajectory_intersecting_corridor():
    """7. Object starting on flank whose short-horizon trajectory enters the corridor."""
    # Starts at xc=0.18, moving right at 0.15/s. Reaches corridor x_min=0.35 in ~1.1s.
    start_box = BoundingBox(0.10, 0.30, 0.26, 0.70)
    track = _simulate_track_trajectory(start_box, dx_per_sec=0.15, frames=8)

    classifier = TrajectoryClassifier(prediction_horizon_sec=2.0)
    est = classifier.classify(track)

    assert est.classification == TrajectoryClassification.PATH_INTERSECTION
    assert est.intersects_path is True
    assert est.time_to_corridor is not None
    assert 0.2 <= est.time_to_corridor <= 1.8
    assert est.crossing_direction == CrossingDirection.LEFT_TO_RIGHT

    # Localization check
    ne_text = format_path_intersection_announcement("person", "left_to_right", language="ne")
    en_text = format_path_intersection_announcement("person", "left_to_right", language="en")
    assert "दायाँतिरबाट बाटोमा आउँदै छ।" in ne_text
    assert "Person crossing into path from left." in en_text


# =============================================================================
# 8. Predicted Trajectory Missing Corridor
# =============================================================================
def test_predicted_trajectory_missing_corridor():
    """8. Object whose trajectory moves away from the corridor and never intersects it."""
    # Starts at xc=0.15, moving further left at -0.10/s
    start_box = BoundingBox(0.08, 0.30, 0.22, 0.70)
    track = _simulate_track_trajectory(start_box, dx_per_sec=-0.10, frames=8)

    classifier = TrajectoryClassifier(prediction_horizon_sec=2.0)
    est = classifier.classify(track)

    assert est.classification != TrajectoryClassification.PATH_INTERSECTION
    assert est.intersects_path is False
    assert est.time_to_corridor is None


# =============================================================================
# 9. Low-Confidence Tracking Gate
# =============================================================================
def test_low_confidence_tracking_gate():
    """9. Detections with low confidence return UNCERTAIN rather than false motion alerts."""
    start_box = BoundingBox(0.10, 0.30, 0.25, 0.70)
    track = _simulate_track_trajectory(start_box, dx_per_sec=0.15, frames=8, confidence=0.25)

    classifier = TrajectoryClassifier(min_detection_confidence=0.40)
    est = classifier.classify(track)

    assert est.classification == TrajectoryClassification.UNCERTAIN
    assert "confidence below minimum threshold" in est.rationale


# =============================================================================
# 10. Unreliable Ego-Motion Gate
# =============================================================================
def test_unreliable_ego_motion_gate():
    """10. Unreliable camera ego-motion forces UNCERTAIN classification."""
    start_box = BoundingBox(0.10, 0.30, 0.25, 0.70)
    unreliable_ego = EgoMotionEstimate(
        dx=0.05, dy=0.0, rotation_rad=0.0, scale=1.0,
        is_reliable=False, confidence=0.10, dt=0.033, timestamp=100.0
    )
    track = _simulate_track_trajectory(start_box, dx_per_sec=0.15, frames=8, ego_motion=unreliable_ego)

    classifier = TrajectoryClassifier()
    est = classifier.classify(track, ego_motion=unreliable_ego)

    assert est.classification == TrajectoryClassification.UNCERTAIN
    assert "Unreliable camera ego-motion" in est.rationale


# =============================================================================
# 11. Missing Detections & Coasting Uncertainty
# =============================================================================
def test_missing_detections_uncertainty():
    """11. Excessive missed frames degrade classification to UNCERTAIN."""
    start_box = BoundingBox(0.40, 0.30, 0.60, 0.70)
    track = _simulate_track_trajectory(start_box, dx_per_sec=0.10, frames=8)

    # Simulate 3 consecutive missed frames (coasting)
    track.mark_missed()
    track.mark_missed()
    track.mark_missed()

    classifier = TrajectoryClassifier(max_miss_streak=2)
    est = classifier.classify(track)

    assert est.classification == TrajectoryClassification.UNCERTAIN
    assert "Missing detections exceed tolerance" in est.rationale


# =============================================================================
# 12. Repeated Announcement Suppression for Crossing Objects
# =============================================================================
def test_repeated_announcement_suppression_for_crossing_object():
    """
    12. A crossing object over 20 consecutive frames triggers an alert once,
    and is suppressed on subsequent frames without chattering.
    """
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=fake_backend)
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne")
    analyzer = SceneAnalyzer()
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.20)

    t0 = 100.0
    dt = 0.033

    for f in range(20):
        t = t0 + f * dt
        # Person crossing left to right: starting x=0.20 + 0.012*f
        xc = 0.20 + 0.012 * f
        box = BoundingBox(xc - 0.07, 0.30, xc + 0.07, 0.70)
        det = Detection("person", 0.90, box, "center" if 0.35 <= xc <= 0.65 else "left")
        tracks = tracker.update([det], timestamp=t)
        assessment = analyzer.analyze_scene(tracks, frame_id=f + 1, timestamp=t)
        decision.process_scene(assessment, current_time=t)

    time.sleep(0.05)
    # At most 2 events: initial detection + trajectory escalation to crossing path; zero repeat chattering across remaining frames
    assert 1 <= len(fake_backend.spoken_history) <= 2
    assert any("बाटो" in s for s in fake_backend.spoken_history)
    speech_mgr.shutdown()


# =============================================================================
# 13. Safety: Never Fabricates "Path is Safe" or "Nothing Ahead"
# =============================================================================
def test_safety_constraints_no_fabricated_safety():
    """13. Verified that no speech output ever claims 'safe' or 'nothing ahead'."""
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=fake_backend)
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne")
    analyzer = SceneAnalyzer()
    tracker = TemporalTracker()

    # Empty frame (no detections at all)
    tracks = tracker.update([], timestamp=100.0)
    assessment = analyzer.analyze_scene(tracks, frame_id=1, timestamp=100.0)
    decision.process_scene(assessment, current_time=100.0)

    # Empty scene does not produce false assurances
    assert len(fake_backend.spoken_history) == 0

    # Path advisory only uses honest 'appears clear'
    ne_adv = analyzer.analyze_scene(tracks, frame_id=1, timestamp=100.0).path.rationale
    assert "safe" not in ne_adv.lower()
    assert "nothing ahead" not in ne_adv.lower()
    speech_mgr.shutdown()
