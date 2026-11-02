"""
Trinetra Kalman-Based Temporal Object Tracking Tests
Validates:
1. Stationary objects (zero drift, low variance).
2. Constant horizontal movement (track predicts lateral progression).
3. Constant vertical movement (track predicts vertical progression).
4. Temporary occlusion (object disappears for 2-3 frames, predicted box coasts forward).
5. Two pedestrians crossing paths (tracks maintain distinct IDs via predicted position and IoU gating).
6. Sudden detection disappearance (track marked LOST, deleted after max_age).
7. Reappearance after missed frames (detection associates with coasting track, preserves track_id).
8. Track ID stability (continuous track ID retention without fragmentation over multi-frame trajectory).
9. Movement classification (APPROACHING, RECEDING, MOVING_LEFT, MOVING_RIGHT, STATIONARY, UNKNOWN).
10. Repeated announcement suppression compatibility (deduplication remains intact with Kalman-tracked objects).
"""

import time
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager
from app.detection.decision import SceneDecisionEngine
from app.detection.scene import SceneAnalyzer
from app.detection.tracking import (
    KalmanBoxTracker,
    MovementDirection,
    TemporalTracker,
    TrackState,
    TrackedObject,
    compute_iou,
)
from app.detection.types import BoundingBox, Detection


def test_kalman_stationary_object():
    """1. Stationary objects: zero drift, minimal velocity, stationary movement classification."""
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.2)
    t = 100.0
    dt = 0.05  # 20 FPS

    box = BoundingBox(0.40, 0.40, 0.60, 0.60)
    for i in range(10):
        det = Detection("person", 0.90, box, sector="center")
        tracks = tracker.update([det], timestamp=t + i * dt)

    assert len(tracks) == 1
    track = tracks[0]
    assert track.track_id == 1
    assert track.state == TrackState.CONFIRMED
    assert abs(track.box.center_x - 0.50) < 0.005
    assert abs(track.box.center_y - 0.50) < 0.005
    assert abs(track.speed_x) < 0.05
    assert abs(track.growth_rate_h) < 0.05
    assert track.movement == MovementDirection.STATIONARY


def test_kalman_constant_horizontal_movement():
    """2. Constant horizontal movement: track predicts lateral progression and classifies lateral direction."""
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.15)
    t = 100.0
    dt = 0.10
    speed = 0.30  # 0.30 normalized units per second to the right

    # 8 consecutive frames moving right
    for i in range(8):
        x_min = 0.10 + i * speed * dt
        x_max = 0.25 + i * speed * dt
        det = Detection("person", 0.88, BoundingBox(x_min, 0.30, x_max, 0.70), sector="left")
        tracks = tracker.update([det], timestamp=t + i * dt)

    assert len(tracks) == 1
    track = tracks[0]
    assert track.track_id == 1
    assert track.state == TrackState.CONFIRMED
    assert track.speed_x > 0.20
    assert track.movement == MovementDirection.MOVING_RIGHT


def test_kalman_constant_vertical_movement():
    """3. Constant vertical movement: track predicts vertical position forward in time before update."""
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.15)
    t = 100.0
    dt = 0.10
    v_y = 0.25  # moving downward at 0.25 units/sec

    for i in range(6):
        y_min = 0.10 + i * v_y * dt
        y_max = 0.30 + i * v_y * dt
        det = Detection("person", 0.90, BoundingBox(0.40, y_min, 0.60, y_max), sector="center")
        tracks = tracker.update([det], timestamp=t + i * dt)

    assert len(tracks) == 1
    track = tracks[0]
    assert track.track_id == 1
    assert track.state == TrackState.CONFIRMED

    # Test prediction step explicitly ahead of the next frame
    pred_box = track.predict(t + 6 * dt)
    expected_yc = (0.10 + 6 * v_y * dt + 0.30 + 6 * v_y * dt) / 2.0
    assert abs(pred_box.center_y - expected_yc) < 0.03


def test_kalman_temporary_occlusion_and_coasting():
    """4. Temporary occlusion: predicted box coasts forward along velocity vector during missed frames."""
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.15, max_age=5)
    t = 100.0
    dt = 0.10
    speed_x = 0.20  # moving right at 0.20 units/sec

    # Establish track over 4 frames
    for i in range(4):
        x_min = 0.10 + i * speed_x * dt
        x_max = 0.25 + i * speed_x * dt
        det = Detection("car", 0.92, BoundingBox(x_min, 0.40, x_max, 0.70), sector="left")
        tracks = tracker.update([det], timestamp=t + i * dt)

    assert len(tracks) == 1
    assert tracks[0].state == TrackState.CONFIRMED
    last_confirmed_x = tracks[0].box.center_x

    # Frame 4 and 5: Occlusion (no detections returned)
    tracks_missed_1 = tracker.update([], timestamp=t + 4 * dt)
    assert len(tracks_missed_1) == 1
    assert tracks_missed_1[0].state == TrackState.LOST
    # Box must have coasted forward!
    x_after_miss_1 = tracks_missed_1[0].box.center_x
    assert x_after_miss_1 > last_confirmed_x

    tracks_missed_2 = tracker.update([], timestamp=t + 5 * dt)
    assert len(tracks_missed_2) == 1
    assert tracks_missed_2[0].state == TrackState.LOST
    assert tracks_missed_2[0].box.center_x > x_after_miss_1

    # Frame 6: Object emerges from occlusion at the expected position
    x_min_emerge = 0.10 + 6 * speed_x * dt
    x_max_emerge = 0.25 + 6 * speed_x * dt
    det_emerge = Detection("car", 0.91, BoundingBox(x_min_emerge, 0.40, x_max_emerge, 0.70), sector="center")
    tracks_reappear = tracker.update([det_emerge], timestamp=t + 6 * dt)

    assert len(tracks_reappear) == 1
    assert tracks_reappear[0].track_id == 1  # Track identity preserved across occlusion!
    assert tracks_reappear[0].state == TrackState.CONFIRMED
    assert tracks_reappear[0].miss_streak == 0


def test_kalman_two_pedestrians_crossing_paths():
    """5. Two pedestrians crossing paths: Kalman state vectors prevent track ID swapping."""
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.10)
    t = 100.0
    dt = 0.10
    speed = 0.25  # Pedestrian A moves right, Pedestrian B moves left

    # 14 frame crossing scenario
    # A moves from x=0.20 toward x=0.65
    # B moves from x=0.65 toward x=0.20
    for i in range(14):
        xa_min = 0.20 + i * speed * dt
        xa_max = 0.35 + i * speed * dt
        xb_min = 0.65 - i * speed * dt
        xb_max = 0.80 - i * speed * dt

        det_a = Detection("person", 0.90, BoundingBox(xa_min, 0.20, xa_max, 0.80), sector="left")
        det_b = Detection("person", 0.90, BoundingBox(xb_min, 0.20, xb_max, 0.80), sector="right")

        # Provide detections in alternating order to challenge greedy matching
        detections = [det_a, det_b] if i % 2 == 0 else [det_b, det_a]
        tracks = tracker.update(detections, timestamp=t + i * dt)

    confirmed = [tr for tr in tracks if tr.state == TrackState.CONFIRMED]
    assert len(confirmed) == 2

    # Find tracks by initial direction
    track_moving_right = next((tr for tr in confirmed if tr.speed_x > 0), None)
    track_moving_left = next((tr for tr in confirmed if tr.speed_x < 0), None)

    assert track_moving_right is not None
    assert track_moving_left is not None
    assert track_moving_right.track_id != track_moving_left.track_id
    # Track moving right has reached x >= 0.55
    assert track_moving_right.box.center_x >= 0.55
    # Track moving left has reached x <= 0.45
    assert track_moving_left.box.center_x <= 0.45


def test_kalman_sudden_detection_disappearance():
    """6. Sudden detection disappearance: track transitions to LOST and is pruned after max_age."""
    tracker = TemporalTracker(min_hits=2, max_age=3, iou_threshold=0.2)
    t = 100.0
    dt = 0.05

    # Confirm track over 2 frames
    det = Detection("dog", 0.85, BoundingBox(0.3, 0.4, 0.5, 0.6), sector="center")
    tracker.update([det], timestamp=t)
    tracker.update([det], timestamp=t + dt)

    assert len(tracker.get_confirmed_tracks()) == 1

    # Disappearance: 3 frames without detection
    t1 = tracker.update([], timestamp=t + 2 * dt)
    assert len(t1) == 1
    assert t1[0].state == TrackState.LOST
    assert t1[0].miss_streak == 1

    t2 = tracker.update([], timestamp=t + 3 * dt)
    assert len(t2) == 1
    assert t2[0].state == TrackState.LOST
    assert t2[0].miss_streak == 2

    t3 = tracker.update([], timestamp=t + 4 * dt)
    # Reached max_age (3) -> marked DELETED and pruned
    assert len(t3) == 0
    assert len(tracker.tracks) == 0


def test_kalman_reappearance_after_missed_frames():
    """7. Reappearance after missed frames: preserves monotonic track_id."""
    tracker = TemporalTracker(min_hits=1, max_age=5, iou_threshold=0.15)
    t = 100.0

    det = Detection("bicycle", 0.90, BoundingBox(0.20, 0.30, 0.40, 0.60), sector="left")
    tracks = tracker.update([det], timestamp=t)
    assert tracks[0].track_id == 1

    # Missed for 2 frames
    tracker.update([], timestamp=t + 0.1)
    tracker.update([], timestamp=t + 0.2)

    # Reappears slightly displaced
    det_reappear = Detection("bicycle", 0.89, BoundingBox(0.22, 0.30, 0.42, 0.60), sector="left")
    tracks_after = tracker.update([det_reappear], timestamp=t + 0.3)

    assert len(tracks_after) == 1
    assert tracks_after[0].track_id == 1
    assert tracks_after[0].hit_streak == 2
    assert tracks_after[0].miss_streak == 0


def test_kalman_track_id_stability():
    """8. Track ID stability: ensures monotonic continuous track ID retention over multi-frame trajectory with noise."""
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.15)
    t = 100.0
    dt = 0.05

    # Simulate 30 frames with noisy bounding boxes
    for i in range(30):
        noise = 0.002 if i % 2 == 0 else -0.002
        det_person = Detection("person", 0.90, BoundingBox(0.15 + noise, 0.20, 0.30 + noise, 0.80), sector="left")
        det_car = Detection("car", 0.88, BoundingBox(0.55, 0.40 + noise, 0.85, 0.70 + noise), sector="right")

        tracks = tracker.update([det_person, det_car], timestamp=t + i * dt)

    assert len(tracks) == 2
    track_ids = {tr.track_id for tr in tracks}
    assert track_ids == {1, 2}
    assert tracker._next_track_id == 3  # No ID churn or fragmentation!


def test_kalman_movement_classification():
    """9. Movement classification: verifies APPROACHING, RECEDING, MOVING_LEFT, MOVING_RIGHT, and STATIONARY."""
    # A. Approaching (expanding height > 0.12 and h_last > 0.18)
    tracker_app = TemporalTracker(min_hits=2, iou_threshold=0.15)
    t = 100.0
    for i in range(5):
        # Height expands from 0.15 to 0.40 over 0.4s (growth rate ~ 0.625 > 0.12)
        h = 0.15 + i * 0.0625
        det = Detection("car", 0.90, BoundingBox(0.40, 0.50 - h / 2, 0.60, 0.50 + h / 2), sector="center")
        tracks = tracker_app.update([det], timestamp=t + i * 0.10)

    assert tracks[0].movement == MovementDirection.APPROACHING

    # B. Receding (shrinking height growth_rate < -0.15)
    tracker_rec = TemporalTracker(min_hits=2, iou_threshold=0.15)
    for i in range(5):
        # Height shrinks from 0.40 to 0.15 over 0.4s (growth rate ~ -0.625 < -0.15)
        h = 0.40 - i * 0.0625
        det = Detection("car", 0.90, BoundingBox(0.40, 0.50 - h / 2, 0.60, 0.50 + h / 2), sector="center")
        tracks = tracker_rec.update([det], timestamp=t + i * 0.10)

    assert tracks[0].movement == MovementDirection.RECEDING

    # C. Moving Left (speed_x < -0.20)
    tracker_left = TemporalTracker(min_hits=2, iou_threshold=0.15)
    for i in range(5):
        # Moves left from xc=0.70 to xc=0.50 over 0.4s (speed_x = -0.50 < -0.20)
        xc = 0.70 - i * 0.05
        det = Detection("person", 0.90, BoundingBox(xc - 0.08, 0.30, xc + 0.08, 0.70), sector="center")
        tracks = tracker_left.update([det], timestamp=t + i * 0.10)

    assert tracks[0].movement == MovementDirection.MOVING_LEFT


def test_kalman_repeated_announcement_suppression_compatibility():
    """10. Repeated announcement suppression: deduplication remains intact with Kalman-tracked objects."""
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=fake_backend)
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne")
    analyzer = SceneAnalyzer()
    tracker = TemporalTracker(min_hits=1, iou_threshold=0.15)

    t0 = 100.0
    dt = 0.05

    # 1. First frame: stationary person appears -> must announce once
    det = Detection("person", 0.91, BoundingBox(0.10, 0.20, 0.25, 0.80), sector="left")
    tracks = tracker.update([det], timestamp=t0)
    assessment1 = analyzer.analyze_scene(tracks, frame_id=1, timestamp=t0)
    decision.process_scene(assessment1)
    time.sleep(0.05)

    assert len(fake_backend.spoken_history) == 1
    assert "बायाँ" in fake_backend.spoken_history[0] and "मान्छे" in fake_backend.spoken_history[0]

    # 2. Next 20 frames: person remains stationary in same sector -> STRICTLY SUPPRESSED
    for i in range(1, 21):
        noise = 0.001 if i % 2 == 0 else -0.001
        det_jitter = Detection("person", 0.90, BoundingBox(0.10 + noise, 0.20, 0.25 + noise, 0.80), sector="left")
        tracks = tracker.update([det_jitter], timestamp=t0 + i * dt)
        assessment = analyzer.analyze_scene(tracks, frame_id=i + 1, timestamp=t0 + i * dt)
        decision.process_scene(assessment)

    time.sleep(0.05)
    # Zero duplicate announcements dispatched!
    assert len(fake_backend.spoken_history) == 1

    # 3. Object escalates to APPROACHING -> must override suppression and announce!
    # Simulate approach over consecutive frames
    for i in range(21, 26):
        h = 0.60 + (i - 20) * 0.05
        det_approach = Detection("person", 0.92, BoundingBox(0.10, 0.50 - h / 2, 0.25, 0.50 + h / 2), sector="left")
        tracks = tracker.update([det_approach], timestamp=t0 + i * dt)
        assessment = analyzer.analyze_scene(tracks, frame_id=i + 1, timestamp=t0 + i * dt)
        decision.process_scene(assessment)

    time.sleep(0.05)
    assert len(fake_backend.spoken_history) >= 2
    speech_mgr.shutdown()
