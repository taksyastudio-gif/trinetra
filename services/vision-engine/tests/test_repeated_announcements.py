"""
Trinetra Repeated Announcement Prevention & Event-Based Filtering Verification Suite.
Simulates:
1. Unchanged scene over many consecutive frames (stationary user & stationary objects).
2. Object appearing for the first time (immediate announcement on confirmation).
3. Object remaining visible over extended time (suppression of repetitive announcements).
4. Object disappearing (graceful pruning after track expiration).
5. Object changing position / sector (immediate position update announcement).
6. Object escalating to approaching (immediate hazard escalation alert).
7. Multiple objects appearing simultaneously (prioritized sequencing, announced once, then silence).
8. Crowd stability (crowd summary announced once, not repeated on every cycle).
9. Path advisory stability (directional advisory announced once, updates on change).
10. Full PerceptionPipeline integration test over 50 consecutive frames.
"""

import time
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager, SpeechPriority
from app.camera.adapter import FramePacket
from app.detection.decision import SceneDecisionEngine
from app.detection.engine import PerceptionPipeline
from app.detection.scene import CollisionRisk, SceneAnalyzer, WalkablePath
from app.detection.tracking import (
    MovementDirection,
    TemporalTracker,
    TrackState,
    TrackedObject,
)
from app.detection.types import BoundingBox, Detection, DetectionResult


# -----------------------------------------------------------------------------
# Test 1: Unchanged scene over 50 consecutive frames
# -----------------------------------------------------------------------------
def test_unchanged_scene_over_50_consecutive_frames():
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend, language="ne")
    tracker = TemporalTracker(min_hits=1, max_age=15)
    analyzer = SceneAnalyzer()
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne", min_announcement_interval=0.0)

    # Stationary person directly ahead in center
    det = Detection(
        class_name="person",
        confidence=0.89,
        box=BoundingBox(0.40, 0.20, 0.60, 0.80),
        sector="center"
    )

    t0 = 1000.0
    dispatched_events = []

    # Simulate 50 consecutive frames (5 seconds at 10 FPS)
    for frame_id in range(1, 51):
        timestamp = t0 + (frame_id * 0.1)
        tracks = tracker.update([det], timestamp=timestamp)
        assessment = analyzer.analyze_scene(tracks, frame_id=frame_id, timestamp=timestamp)
        event = decision.process_scene(assessment, current_time=timestamp)
        if event:
            dispatched_events.append((frame_id, event))

    time.sleep(0.05)

    # Frame 1: stationary_obstacle (person ahead)
    # Frame 2: path_advisory (center blocked, flank clear)
    # Frames 3-50: ZERO events! Exactly 0 repeated announcements!
    assert len(dispatched_events) in (1, 2)
    assert dispatched_events[0] == (1, "stationary_obstacle")
    subsequent_events = [(f_id, ev) for f_id, ev in dispatched_events if f_id > 2]
    assert len(subsequent_events) == 0, f"Expected zero chatter after initial perception, got: {subsequent_events}"

    # Spoken history has at most 2 initial announcements, 0 repeats
    assert len(backend.spoken_history) == len(dispatched_events)
    assert "मान्छे" in backend.spoken_history[0]
    speech_mgr.shutdown()


# -----------------------------------------------------------------------------
# Test 2: Object appearing for first time -> Prompt announcement on confirmation
# -----------------------------------------------------------------------------
def test_object_appearing_for_first_time():
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend, language="en")
    tracker = TemporalTracker(min_hits=2, max_age=15)
    analyzer = SceneAnalyzer()
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="en", min_announcement_interval=0.0)

    det = Detection(
        class_name="chair",
        confidence=0.92,
        box=BoundingBox(0.10, 0.40, 0.30, 0.85),
        sector="left"
    )

    t0 = 100.0
    # Frame 1: Tentative track (min_hits=2) -> no announcement
    tracks = tracker.update([det], timestamp=t0)
    assert tracks[0].state == TrackState.TENTATIVE
    assessment = analyzer.analyze_scene(tracks, frame_id=1, timestamp=t0)
    event1 = decision.process_scene(assessment, current_time=t0)
    assert event1 is None

    # Frame 2: Confirmed track -> immediate announcement
    tracks = tracker.update([det], timestamp=t0 + 0.1)
    assert tracks[0].state == TrackState.CONFIRMED
    assessment = analyzer.analyze_scene(tracks, frame_id=2, timestamp=t0 + 0.1)
    event2 = decision.process_scene(assessment, current_time=t0 + 0.1)
    assert event2 == "stationary_obstacle"

    time.sleep(0.05)
    assert len(backend.spoken_history) == 1
    assert backend.spoken_history[0] == "Chair, left."
    speech_mgr.shutdown()


# -----------------------------------------------------------------------------
# Test 3: Object remaining visible -> Stays announced, suppresses subsequent
# -----------------------------------------------------------------------------
def test_object_remaining_visible_suppresses_subsequent_frames():
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend, language="ne")
    tracker = TemporalTracker(min_hits=1, max_age=15)
    analyzer = SceneAnalyzer()
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne", min_announcement_interval=0.0)

    # Obstacle on left (center remains clear, so no path advisory triggered)
    det = Detection(
        class_name="door",
        confidence=0.95,
        box=BoundingBox(0.05, 0.10, 0.30, 0.90),
        sector="left"
    )

    t0 = 500.0
    # Frame 1: Announced
    tracks = tracker.update([det], timestamp=t0)
    assessment = analyzer.analyze_scene(tracks, frame_id=1, timestamp=t0)
    event1 = decision.process_scene(assessment, current_time=t0)
    assert event1 == "stationary_obstacle"
    assert tracks[0].announced is True

    # Frames 2 to 20: Stays visible with minor jitter -> 0 announcements
    for i in range(2, 21):
        jittered_box = BoundingBox(0.05 + (i * 0.001), 0.10, 0.30, 0.90)
        det_jitter = Detection("door", 0.95, jittered_box, "left")
        tracks = tracker.update([det_jitter], timestamp=t0 + (i * 0.1))
        assessment = analyzer.analyze_scene(tracks, frame_id=i, timestamp=t0 + (i * 0.1))
        event = decision.process_scene(assessment, current_time=t0 + (i * 0.1))
        assert event is None

    time.sleep(0.05)
    assert len(backend.spoken_history) == 1
    assert "ढोका" in backend.spoken_history[0]
    speech_mgr.shutdown()


# -----------------------------------------------------------------------------
# Test 4: Object disappearing -> Track deleted after max_age frames
# -----------------------------------------------------------------------------
def test_object_disappearing_and_track_cleanup():
    tracker = TemporalTracker(min_hits=1, max_age=5)
    det = Detection("person", 0.9, BoundingBox(0.4, 0.2, 0.6, 0.8), "center")
    t0 = 100.0

    # Object present
    tracks = tracker.update([det], timestamp=t0)
    assert len(tracks) == 1
    assert tracks[0].state == TrackState.CONFIRMED

    # Object disappears for 4 frames -> LOST
    for i in range(1, 5):
        tracks = tracker.update([], timestamp=t0 + (i * 0.1))
        assert len(tracks) == 1
        assert tracks[0].state == TrackState.LOST

    # Frame 5 of absence (reaches max_age=5) -> DELETED and pruned
    tracks = tracker.update([], timestamp=t0 + 0.5)
    assert len(tracks) == 0


# -----------------------------------------------------------------------------
# Test 5: Object changing position/sector -> Immediate position update announcement
# -----------------------------------------------------------------------------
def test_object_changing_position_triggers_update():
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend, language="ne")
    tracker = TemporalTracker(min_hits=1, max_age=15)
    analyzer = SceneAnalyzer()
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne", min_announcement_interval=0.0)

    t0 = 100.0
    # Step 1: Person in center
    det_center = Detection("person", 0.9, BoundingBox(0.40, 0.2, 0.60, 0.8), "center")
    tracks = tracker.update([det_center], timestamp=t0)
    assessment = analyzer.analyze_scene(tracks, frame_id=1, timestamp=t0)
    event1 = decision.process_scene(assessment, current_time=t0)
    assert event1 == "stationary_obstacle"

    time.sleep(0.05)
    assert "मान्छे" in backend.spoken_history[0] and "अगाडि" in backend.spoken_history[0]

    # Step 2: Person shifts to left sector
    # Match tracker with IoU or update track sector
    det_left = Detection("person", 0.9, BoundingBox(0.10, 0.2, 0.30, 0.8), "left")
    # Directly update track to simulate lateral movement
    tracks[0].sector = "left"
    tracks[0].box = det_left.box
    assessment = analyzer.analyze_scene(tracks, frame_id=8, timestamp=t0 + 0.8)
    event_shift = decision.process_scene(assessment, current_time=t0 + 0.8)
    assert event_shift == "stationary_obstacle"

    time.sleep(0.05)
    assert any("बायाँतिर" in s for s in backend.spoken_history)

    # Step 3: Person remains stationary on left -> silenced
    for i in range(9, 15):
        assessment = analyzer.analyze_scene(tracks, frame_id=i, timestamp=t0 + (i * 0.1))
        event = decision.process_scene(assessment, current_time=t0 + (i * 0.1))
        assert event is None

    speech_mgr.shutdown()


# -----------------------------------------------------------------------------
# Test 6: Object escalating to approaching -> Immediate hazard warning
# -----------------------------------------------------------------------------
def test_object_escalating_to_approaching_overrides_cooldown():
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend, language="en")
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="en", min_announcement_interval=0.0)
    analyzer = SceneAnalyzer()

    t0 = 200.0
    # Track originally stationary
    car_track = TrackedObject(
        track_id=1,
        class_name="car",
        confidence=0.92,
        box=BoundingBox(0.40, 0.40, 0.60, 0.60),
        sector="center",
        first_seen=t0,
        last_seen=t0,
        state=TrackState.CONFIRMED,
        movement=MovementDirection.STATIONARY
    )

    assessment1 = analyzer.analyze_scene([car_track], frame_id=1, timestamp=t0)
    event1 = decision.process_scene(assessment1, current_time=t0)
    assert event1 == "stationary_obstacle"
    assert car_track.announced is True

    time.sleep(0.05)
    assert len(backend.spoken_history) == 1
    assert backend.spoken_history[0] == "Car, ahead."

    # Car escalates to approaching
    car_track.movement = MovementDirection.APPROACHING
    car_track.box = BoundingBox(0.30, 0.20, 0.70, 0.85)

    assessment2 = analyzer.analyze_scene([car_track], frame_id=2, timestamp=t0 + 0.3)
    event2 = decision.process_scene(assessment2, current_time=t0 + 0.3)
    # Approaches trigger approaching obstacle or critical hazard
    assert event2 in ("approaching_obstacle", "critical_hazard")

    time.sleep(0.05)
    assert len(backend.spoken_history) == 2
    assert "approaching" in backend.spoken_history[1].lower() or "caution" in backend.spoken_history[1].lower()
    speech_mgr.shutdown()


# -----------------------------------------------------------------------------
# Test 7: Multiple objects appearing simultaneously -> Paced sequence, then silence
# -----------------------------------------------------------------------------
def test_multiple_objects_appearing_simultaneously():
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend, language="ne")
    tracker = TemporalTracker(min_hits=1, max_age=15)
    analyzer = SceneAnalyzer(crowd_threshold=5)  # threshold 5 so 2 persons don't trigger crowd
    decision = SceneDecisionEngine(
        speech_manager=speech_mgr,
        language="ne",
        min_announcement_interval=1.0  # 1.0s pacing interval between announcements
    )

    det_center = Detection("person", 0.90, BoundingBox(0.40, 0.20, 0.60, 0.80), "center")
    det_left = Detection("chair", 0.88, BoundingBox(0.10, 0.40, 0.30, 0.80), "left")
    det_right = Detection("table", 0.85, BoundingBox(0.70, 0.40, 0.90, 0.80), "right")
    all_detections = [det_center, det_left, det_right]

    t0 = 100.0

    # Frame 1 (t=100.0): Center object announced first
    tracks = tracker.update(all_detections, timestamp=t0)
    assessment = analyzer.analyze_scene(tracks, frame_id=1, timestamp=t0)
    e1 = decision.process_scene(assessment, current_time=t0)
    assert e1 == "stationary_obstacle"

    time.sleep(0.05)
    assert len(backend.spoken_history) == 1
    assert "मान्छे" in backend.spoken_history[0]  # Center person prioritized

    # Frame 2-5 (t=100.1 to 100.5): Within pacing interval (< 1.0s) -> None
    for i in range(1, 6):
        t = t0 + (i * 0.1)
        tracks = tracker.update(all_detections, timestamp=t)
        assessment = analyzer.analyze_scene(tracks, frame_id=i + 1, timestamp=t)
        e = decision.process_scene(assessment, current_time=t)
        assert e is None

    # Frame 11 (t=101.1): Pacing interval elapsed -> Second object announced
    t = t0 + 1.1
    tracks = tracker.update(all_detections, timestamp=t)
    assessment = analyzer.analyze_scene(tracks, frame_id=11, timestamp=t)
    e2 = decision.process_scene(assessment, current_time=t)
    assert e2 == "stationary_obstacle"

    time.sleep(0.05)
    assert len(backend.spoken_history) == 2

    # Frame 22 (t=102.2): Pacing interval elapsed -> Third object announced
    t = t0 + 2.2
    tracks = tracker.update(all_detections, timestamp=t)
    assessment = analyzer.analyze_scene(tracks, frame_id=22, timestamp=t)
    e3 = decision.process_scene(assessment, current_time=t)
    assert e3 == "stationary_obstacle"

    time.sleep(0.05)
    assert len(backend.spoken_history) == 3

    # Now all 3 objects are announced.
    # Simulate next 50 frames (from t=102.3 to t=107.3) with unchanged scene:
    for i in range(23, 73):
        t = t0 + (i * 0.1)
        tracks = tracker.update(all_detections, timestamp=t)
        assessment = analyzer.analyze_scene(tracks, frame_id=i, timestamp=t)
        e = decision.process_scene(assessment, current_time=t)
        assert e is None, f"Frame {i} should be silent but got {e}"

    # Verify zero additional announcements occurred!
    assert len(backend.spoken_history) == 3
    speech_mgr.shutdown()


# -----------------------------------------------------------------------------
# Test 8: Crowd stability across frames -> Exactly 1 crowd announcement
# -----------------------------------------------------------------------------
def test_crowd_stability_across_consecutive_frames():
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend, language="ne")
    analyzer = SceneAnalyzer(crowd_threshold=3)
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne", min_announcement_interval=0.0)

    t0 = 100.0
    # 3 confirmed persons
    persons = [
        TrackedObject(1, "person", 0.9, BoundingBox(0.1, 0.2, 0.25, 0.7), "left", t0, t0, state=TrackState.CONFIRMED),
        TrackedObject(2, "person", 0.85, BoundingBox(0.4, 0.2, 0.55, 0.7), "center", t0, t0, state=TrackState.CONFIRMED),
        TrackedObject(3, "person", 0.88, BoundingBox(0.7, 0.2, 0.85, 0.7), "right", t0, t0, state=TrackState.CONFIRMED),
    ]

    # Frame 1: Crowd entered -> announced
    assessment1 = analyzer.analyze_scene(persons, frame_id=1, timestamp=t0)
    event1 = decision.process_scene(assessment1, current_time=t0)
    assert event1 == "crowd_summary"

    time.sleep(0.05)
    assert len(backend.spoken_history) == 1

    # Next 30 frames: Same crowd count -> 0 announcements
    for i in range(2, 32):
        t = t0 + (i * 0.2)
        assessment = analyzer.analyze_scene(persons, frame_id=i, timestamp=t)
        event = decision.process_scene(assessment, current_time=t)
        assert event is None

    assert len(backend.spoken_history) == 1
    speech_mgr.shutdown()


# -----------------------------------------------------------------------------
# Test 9: Path advisory stability across frames -> Exactly 1 advisory
# -----------------------------------------------------------------------------
def test_path_advisory_stability_across_consecutive_frames():
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend, language="ne")
    analyzer = SceneAnalyzer()
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne", min_announcement_interval=0.0)

    t0 = 100.0
    # Large obstacle blocking center, flanks clear
    obstacle = TrackedObject(
        track_id=1,
        class_name="table",
        confidence=0.95,
        box=BoundingBox(0.35, 0.4, 0.65, 0.85),
        sector="center",
        first_seen=t0,
        last_seen=t0,
        state=TrackState.CONFIRMED,
        announced=True,  # Obstacle itself already announced
        last_announced_sector="center"
    )

    # Frame 1: Center blocked, left recommended
    assessment1 = analyzer.analyze_scene([obstacle], frame_id=1, timestamp=t0)
    assert assessment1.path.recommended_direction == "left"
    event1 = decision.process_scene(assessment1, current_time=t0)
    assert event1 == "path_advisory"

    time.sleep(0.05)
    assert len(backend.spoken_history) == 1
    assert "बायाँ" in backend.spoken_history[0] and "खुला" in backend.spoken_history[0]

    # Next 30 frames: Still recommended left -> 0 repetitions
    for i in range(2, 32):
        t = t0 + (i * 0.2)
        assessment = analyzer.analyze_scene([obstacle], frame_id=i, timestamp=t)
        event = decision.process_scene(assessment, current_time=t)
        assert event is None

    assert len(backend.spoken_history) == 1
    speech_mgr.shutdown()


# -----------------------------------------------------------------------------
# Test 10: Full PerceptionPipeline End-to-End Simulation over 50 Frames
# -----------------------------------------------------------------------------
def test_perception_pipeline_unchanged_scene_suppression():
    """
    Validates that a stationary camera view fed through PerceptionPipeline
    announces detected obstacles once, and does not chatter repeatedly
    over 50 consecutive frames.
    """
    from app.detection.engine import FakeDetectionEngine

    fake_engine = FakeDetectionEngine(
        mock_detections=[
            Detection("person", 0.91, BoundingBox(0.40, 0.20, 0.60, 0.80), "center")
        ]
    )
    backend = FakeSpeechBackend(supported_languages=["en", "ne"])
    speech_mgr = SpeechManager(backend=backend, language="ne")
    pipeline = PerceptionPipeline(
        engine=fake_engine,
        speech_manager=speech_mgr,
        language="ne"
    )

    t0 = 1000.0
    for frame_id in range(1, 51):
        packet = FramePacket(
            frame_id=frame_id,
            captured_at=t0 + (frame_id * 0.1),
            jpeg_bytes=b"fake_jpeg_frame",
            width=640,
            height=480,
            source_id="test_camera",
            session_id="session_test_1"
        )
        pipeline.process_frame(packet)

    time.sleep(0.05)
    # The initial frame or confirmation announces obstacle/path once
    # Spoken history must NOT contain 50 repeated announcements
    assert len(backend.spoken_history) <= 2
    assert any("मान्छे" in s for s in backend.spoken_history)

    pipeline.stop()
    speech_mgr.shutdown()
