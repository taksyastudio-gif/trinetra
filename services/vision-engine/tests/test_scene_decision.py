"""
Tests for Trinetra Phase 1: Temporal Tracking, Scene Understanding & Decision Engine.
Validates object persistence, movement estimation, crowd summarization,
honest confidence bounds, and prioritized speech dispatch in English and Nepali.
"""

import time
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager, SpeechPriority
from app.detection.decision import SceneDecisionEngine
from app.detection.engine import PerceptionPipeline
from app.detection.scene import CollisionRisk, SceneAnalyzer, WalkablePath
from app.detection.tracking import (
    MovementDirection,
    TemporalTracker,
    TrackState,
    TrackedObject,
    compute_iou,
)
from app.detection.types import BoundingBox, Detection, DetectionResult, classify_sector
from app.localization import (
    format_announcement,
    format_approaching_announcement,
    format_crowd_announcement,
    format_path_advisory,
)


def test_iou_computation_precision():
    """Validates IoU computation across disjoint, overlapping, and identical bounding boxes."""
    b1 = BoundingBox(0.1, 0.1, 0.5, 0.5)
    b2 = BoundingBox(0.1, 0.1, 0.5, 0.5)
    assert compute_iou(b1, b2) == pytest.approx(1.0)

    # Disjoint boxes
    b3 = BoundingBox(0.6, 0.6, 0.9, 0.9)
    assert compute_iou(b1, b3) == 0.0

    # Partial overlap
    b4 = BoundingBox(0.3, 0.3, 0.7, 0.7)
    iou = compute_iou(b1, b4)
    assert 0.1 < iou < 0.3


def test_temporal_tracker_lifecycle_and_association():
    """Validates track creation, monotonic ID assignment, IoU matching, and track state transitions."""
    tracker = TemporalTracker(iou_threshold=0.2, min_hits=2, max_age=3)
    t0 = 100.0

    # Frame 1: Detection arrives -> Tentative track created
    d1 = Detection(class_name="person", confidence=0.85, box=BoundingBox(0.2, 0.2, 0.4, 0.8), sector="left")
    tracks = tracker.update([d1], timestamp=t0)
    assert len(tracks) == 1
    assert tracks[0].track_id == 1
    assert tracks[0].state == TrackState.TENTATIVE
    assert tracks[0].hit_streak == 1

    # Frame 2: Same object observed -> Track promoted to CONFIRMED
    d2 = Detection(class_name="person", confidence=0.88, box=BoundingBox(0.21, 0.2, 0.41, 0.8), sector="left")
    tracks = tracker.update([d2], timestamp=t0 + 0.1)
    assert len(tracks) == 1
    assert tracks[0].track_id == 1
    assert tracks[0].state == TrackState.CONFIRMED
    assert tracks[0].hit_streak == 2

    # Frame 3: Missing frame -> Track marked as LOST
    tracks = tracker.update([], timestamp=t0 + 0.2)
    assert len(tracks) == 1
    assert tracks[0].state == TrackState.LOST
    assert tracks[0].miss_streak == 1

    # Frame 4 & 5 & 6: Continued absence exceeds max_age -> Track pruned/deleted
    tracker.update([], timestamp=t0 + 0.3)
    tracker.update([], timestamp=t0 + 0.4)
    tracks = tracker.update([], timestamp=t0 + 0.5)
    assert len(tracks) == 0


def test_temporal_tracker_approaching_movement_estimation():
    """Validates that expanding bounding box height over time correctly classifies movement as APPROACHING."""
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.15)
    t0 = 100.0

    # Step 1: Small bounding box in distance
    d1 = Detection("car", 0.90, BoundingBox(0.40, 0.35, 0.60, 0.55), sector="center")
    tracker.update([d1], timestamp=t0)

    # Step 2: Car gets significantly larger (approaching)
    d2 = Detection("car", 0.92, BoundingBox(0.35, 0.30, 0.65, 0.65), sector="center")
    tracker.update([d2], timestamp=t0 + 0.2)

    # Step 3: Car gets even larger
    d3 = Detection("car", 0.94, BoundingBox(0.30, 0.25, 0.70, 0.80), sector="center")
    tracks = tracker.update([d3], timestamp=t0 + 0.4)

    assert len(tracks) == 1
    track = tracks[0]
    assert track.track_id == 1
    assert track.state == TrackState.CONFIRMED
    assert track.movement == MovementDirection.APPROACHING


def test_scene_analyzer_crowd_detection():
    """Validates that scenes with 3 or more persons trigger crowd summarization."""
    analyzer = SceneAnalyzer(crowd_threshold=3)
    t0 = 100.0

    t1 = TrackedObject(1, "person", 0.9, BoundingBox(0.1, 0.2, 0.25, 0.8), "left", t0, t0, state=TrackState.CONFIRMED)
    t2 = TrackedObject(2, "person", 0.85, BoundingBox(0.4, 0.2, 0.55, 0.8), "center", t0, t0, state=TrackState.CONFIRMED)
    t3 = TrackedObject(3, "person", 0.88, BoundingBox(0.7, 0.2, 0.85, 0.8), "right", t0, t0, state=TrackState.CONFIRMED)

    assessment = analyzer.analyze_scene([t1, t2, t3], frame_id=1, timestamp=t0)
    assert assessment.is_crowded is True
    assert assessment.crowd_count == 3


def test_scene_analyzer_walkable_path_honest_confidence():
    """Validates honest confidence bounds when evaluating walkable sectors."""
    analyzer = SceneAnalyzer()
    t0 = 100.0

    # Case A: Center clear, flanks open -> recommend center with clear rationale
    assessment_clear = analyzer.analyze_scene([], frame_id=1, timestamp=t0)
    assert assessment_clear.path.center_clear is True
    assert assessment_clear.path.recommended_direction == "ahead"

    # Case B: Center blocked by large obstacle, left clear, right clear -> suggests flank
    t_obstacle = TrackedObject(
        1, "table", 0.95,
        BoundingBox(0.35, 0.4, 0.65, 0.85),
        "center", t0, t0, state=TrackState.CONFIRMED
    )
    assessment_blocked = analyzer.analyze_scene([t_obstacle], frame_id=2, timestamp=t0)
    assert assessment_blocked.path.center_clear is False
    assert assessment_blocked.path.recommended_direction == "left"
    assert assessment_blocked.path.confidence >= 0.70

    # Case C: All sectors blocked -> rec_dir must be None, never fabricate a clear path
    t_left = TrackedObject(2, "car", 0.9, BoundingBox(0.05, 0.2, 0.3, 0.9), "left", t0, t0, state=TrackState.CONFIRMED)
    t_right = TrackedObject(3, "bus", 0.9, BoundingBox(0.68, 0.2, 0.95, 0.9), "right", t0, t0, state=TrackState.CONFIRMED)
    assessment_all_blocked = analyzer.analyze_scene([t_obstacle, t_left, t_right], frame_id=3, timestamp=t0)
    assert assessment_all_blocked.path.center_clear is False
    assert assessment_all_blocked.path.left_clear is False
    assert assessment_all_blocked.path.right_clear is False
    assert assessment_all_blocked.path.recommended_direction is None


def test_decision_engine_crowd_summary_priority():
    """Validates that a crowd scene triggers crowd summary instead of announcing every individual."""
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend)
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne")

    analyzer = SceneAnalyzer(crowd_threshold=3)
    t0 = 100.0
    tracks = [
        TrackedObject(1, "person", 0.9, BoundingBox(0.1, 0.2, 0.25, 0.7), "left", t0, t0, state=TrackState.CONFIRMED),
        TrackedObject(2, "person", 0.85, BoundingBox(0.4, 0.2, 0.55, 0.7), "center", t0, t0, state=TrackState.CONFIRMED),
        TrackedObject(3, "person", 0.88, BoundingBox(0.7, 0.2, 0.85, 0.7), "right", t0, t0, state=TrackState.CONFIRMED),
    ]

    assessment = analyzer.analyze_scene(tracks, frame_id=10, timestamp=t0)
    event_dispatched = decision.process_scene(assessment)

    assert event_dispatched == "crowd_summary"
    time.sleep(0.05)
    assert len(backend.spoken_history) == 1
    # Spoken output must be the crowd summary, not individual announcements
    assert "भीड" in backend.spoken_history[0] or "मान्छे" in backend.spoken_history[0]
    speech_mgr.shutdown()


def test_decision_engine_critical_hazard_preemption():
    """Validates that an approaching vehicle triggers immediate critical hazard preemption."""
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend)
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne")

    analyzer = SceneAnalyzer()
    t0 = 100.0
    fast_car = TrackedObject(
        track_id=42,
        class_name="car",
        confidence=0.95,
        box=BoundingBox(0.35, 0.2, 0.65, 0.85),
        sector="center",
        first_seen=t0,
        last_seen=t0,
        state=TrackState.CONFIRMED,
        movement=MovementDirection.APPROACHING
    )

    assessment = analyzer.analyze_scene([fast_car], frame_id=20, timestamp=t0)
    event_dispatched = decision.process_scene(assessment)

    assert event_dispatched == "critical_hazard"
    time.sleep(0.05)
    assert len(backend.spoken_history) == 1
    # Must announce approaching car in Nepali
    assert "गाडी" in backend.spoken_history[0] or "सावधान" in backend.spoken_history[0]
    speech_mgr.shutdown()


def test_decision_engine_deduplication_cooldown():
    """Validates that stationary objects are not continuously announced on every frame."""
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend)
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="en", default_cooldown=3.0)

    analyzer = SceneAnalyzer()
    t0 = 100.0
    chair = TrackedObject(
        track_id=5,
        class_name="chair",
        confidence=0.90,
        box=BoundingBox(0.4, 0.5, 0.6, 0.9),
        sector="center",
        first_seen=t0,
        last_seen=t0,
        state=TrackState.CONFIRMED,
        movement=MovementDirection.STATIONARY
    )

    assessment = analyzer.analyze_scene([chair], frame_id=1, timestamp=t0)
    # First frame -> announced
    event1 = decision.process_scene(assessment)
    assert event1 == "stationary_obstacle"
    time.sleep(0.05)
    assert len(backend.spoken_history) == 1
    assert backend.spoken_history[0] == "Chair, ahead."

    # Immediate next frame (within cooldown) -> suppressed!
    assessment2 = analyzer.analyze_scene([chair], frame_id=2, timestamp=t0 + 0.1)
    event2 = decision.process_scene(assessment2)
    assert event2 != "stationary_obstacle"
    assert len(backend.spoken_history) == 1  # No duplicate speech added!
    speech_mgr.shutdown()
