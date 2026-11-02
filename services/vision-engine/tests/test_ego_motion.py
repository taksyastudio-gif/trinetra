"""
Trinetra Camera Ego-Motion Estimator & Kalman Compensation Tests
Validates all 17 requirements specified in Implementation Priority 2:
1. Stationary camera with stationary background.
2. Horizontal camera movement.
3. Vertical camera movement.
4. Camera rotation.
5. Approximate scale changes.
6. Camera movement with independently moving objects (foreground exclusion).
7. Low-texture or featureless frames.
8. Insufficient feature points.
9. Motion blur or inconsistent optical flow.
10. Sudden scene changes (scene cuts / severe shaking).
11. Incorrect or irregular timestamps.
12. Resolution changes.
13. Noisy feature tracking and RANSAC outlier rejection.
14. Ego-motion compensation preserving genuine object movement.
15. Kalman covariance remaining numerically stable.
16. Existing track ID stability across camera motion.
17. Existing announcement deduplication compatibility with ego-motion compensation.
"""

import math
import time
import cv2
import numpy as np
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager
from app.camera.adapter import FramePacket
from app.detection.decision import SceneDecisionEngine
from app.detection.ego_motion import EgoMotionEstimate, SparseOpticalFlowEgoMotionEstimator
from app.detection.engine import FakeDetectionEngine, PerceptionPipeline
from app.detection.scene import SceneAnalyzer
from app.detection.tracking import (
    KalmanBoxTracker,
    MovementDirection,
    TemporalTracker,
    TrackState,
    TrackedObject,
)
from app.detection.types import BoundingBox, Detection, DetectionResult


def _create_textured_background(width: int = 320, height: int = 240) -> np.ndarray:
    """Generates a rich, synthetic background with high corner density."""
    np.random.seed(42)
    img = np.zeros((height, width), dtype=np.uint8)

    # Base gradient
    for y in range(height):
        img[y, :] = int((y / height) * 60)

    # Grid of textured geometric shapes and corners
    for x in range(20, width - 20, 25):
        for y in range(20, height - 20, 25):
            cv2.rectangle(img, (x, y), (x + 12, y + 12), 200, -1)
            cv2.circle(img, (x + 6, y + 6), 3, 50, -1)
            cv2.line(img, (x, y + 12), (x + 12, y), 255, 1)

    return img


def _warp_affine_transform(
    img: np.ndarray,
    dx_px: float,
    dy_px: float,
    rot_deg: float = 0.0,
    scale: float = 1.0
) -> np.ndarray:
    """Warps an image using known ground-truth affine parameters."""
    h, w = img.shape[:2]
    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, rot_deg, scale)
    M[0, 2] += dx_px
    M[1, 2] += dy_px
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)


# =============================================================================
# 1. Stationary Camera with Stationary Background
# =============================================================================
def test_stationary_camera_stationary_background():
    """1. Stationary camera: near-zero translation, rotation, and scale drift; marked reliable."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg = _create_textured_background()

    # Frame 1
    est1 = estimator.estimate(bg, timestamp=100.0)
    assert not est1.is_reliable
    assert est1.error_reason == "first_frame"

    # Frame 2 (identical stationary image)
    est2 = estimator.estimate(bg, timestamp=100.1)
    assert est2.is_reliable
    assert abs(est2.dx) < 0.005
    assert abs(est2.dy) < 0.005
    assert abs(est2.rotation_rad) < 0.02
    assert abs(est2.scale - 1.0) < 0.02
    assert est2.confidence > 0.60
    assert est2.num_inliers >= 15


# =============================================================================
# 2. Horizontal Camera Movement
# =============================================================================
def test_horizontal_camera_movement():
    """2. Horizontal camera movement: accurately recovers pure horizontal translation."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg1 = _create_textured_background(320, 240)
    dx_px = 12.0  # Shift 12 pixels right
    bg2 = _warp_affine_transform(bg1, dx_px=dx_px, dy_px=0.0)

    estimator.estimate(bg1, timestamp=100.0)
    est = estimator.estimate(bg2, timestamp=100.1)

    assert est.is_reliable
    expected_norm_dx = dx_px / 320.0  # 0.0375
    assert abs(est.dx - expected_norm_dx) < 0.006
    assert abs(est.dy) < 0.005
    assert abs(est.scale - 1.0) < 0.02
    assert est.inlier_ratio >= 0.70


# =============================================================================
# 3. Vertical Camera Movement
# =============================================================================
def test_vertical_camera_movement():
    """3. Vertical camera movement: accurately recovers pure vertical translation."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg1 = _create_textured_background(320, 240)
    dy_px = -9.0  # Shift 9 pixels up
    bg2 = _warp_affine_transform(bg1, dx_px=0.0, dy_px=dy_px)

    estimator.estimate(bg1, timestamp=100.0)
    est = estimator.estimate(bg2, timestamp=100.1)

    assert est.is_reliable
    expected_norm_dy = dy_px / 240.0  # -0.0375
    assert abs(est.dy - expected_norm_dy) < 0.006
    assert abs(est.dx) < 0.005
    assert abs(est.scale - 1.0) < 0.02


# =============================================================================
# 4. Camera Rotation
# =============================================================================
def test_camera_rotation():
    """4. Camera rotation: accurately estimates small camera rotations in radians."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg1 = _create_textured_background(320, 240)
    rot_deg = 3.5
    bg2 = _warp_affine_transform(bg1, dx_px=0.0, dy_px=0.0, rot_deg=rot_deg)

    estimator.estimate(bg1, timestamp=100.0)
    est = estimator.estimate(bg2, timestamp=100.1)

    assert est.is_reliable
    est_deg = abs(math.degrees(est.rotation_rad))
    assert abs(est_deg - rot_deg) < 0.8
    assert abs(est.scale - 1.0) < 0.03


# =============================================================================
# 5. Approximate Scale Changes
# =============================================================================
def test_approximate_scale_changes():
    """5. Approximate scale changes: tracks uniform scale change (approaching/receding camera)."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg1 = _create_textured_background(320, 240)
    true_scale = 1.04  # 4% zoom in / step forward
    bg2 = _warp_affine_transform(bg1, dx_px=0.0, dy_px=0.0, scale=true_scale)

    estimator.estimate(bg1, timestamp=100.0)
    est = estimator.estimate(bg2, timestamp=100.1)

    assert est.is_reliable
    assert abs(est.scale - true_scale) < 0.02


# =============================================================================
# 6. Camera Movement with Independently Moving Objects (Foreground Masking)
# =============================================================================
def test_camera_movement_with_independently_moving_objects():
    """6. Moving objects: foreground bounding-box masking prevents foreground motion from corrupting ego-motion."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg1 = _create_textured_background(320, 240)

    # Add a large independently moving foreground object at (0.35, 0.30, 0.65, 0.70)
    fg_box1 = BoundingBox(0.35, 0.30, 0.65, 0.70)
    # In frame 1, draw object
    cv2.rectangle(bg1, (int(0.35*320), int(0.30*240)), (int(0.65*320), int(0.70*240)), 255, -1)

    # Camera moves right by 8 pixels
    cam_dx_px = 8.0
    bg2 = _warp_affine_transform(bg1, dx_px=cam_dx_px, dy_px=0.0)

    # But the foreground object moves INDEPENDENTLY to the left by 25 pixels
    cv2.rectangle(bg2, (int(0.35*320), int(0.30*240)), (int(0.65*320), int(0.70*240)), 0, -1)
    fg_box2 = BoundingBox(0.25, 0.30, 0.55, 0.70)
    cv2.rectangle(bg2, (int(0.25*320), int(0.30*240)), (int(0.55*320), int(0.70*240)), 255, -1)

    # Estimate ego-motion providing the detected bounding box to mask out foreground!
    estimator.estimate(bg1, timestamp=100.0, detected_boxes=[fg_box1])
    est = estimator.estimate(bg2, timestamp=100.1, detected_boxes=[fg_box2])

    assert est.is_reliable
    # Ego-motion must reflect the CAMERA's 8px shift (0.025 norm), NOT the object's -25px shift!
    expected_norm_dx = cam_dx_px / 320.0
    assert abs(est.dx - expected_norm_dx) < 0.008


# =============================================================================
# 7. Low-Texture or Featureless Frames
# =============================================================================
def test_low_texture_or_featureless_frames():
    """7. Low-texture frames: completely flat image cleanly flagged as unreliable without exception."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    flat_frame = np.full((240, 320), 128, dtype=np.uint8)

    estimator.estimate(flat_frame, timestamp=100.0)
    est = estimator.estimate(flat_frame, timestamp=100.1)

    assert not est.is_reliable
    assert est.error_reason == "insufficient_features"
    assert est.confidence == 0.0


# =============================================================================
# 8. Insufficient Feature Points
# =============================================================================
def test_insufficient_feature_points():
    """8. Insufficient features: image with only 2 corner points fails confidence gate safely."""
    estimator = SparseOpticalFlowEgoMotionEstimator(min_inliers=12)
    sparse_frame = np.zeros((240, 320), dtype=np.uint8)
    cv2.circle(sparse_frame, (50, 50), 5, 255, -1)
    cv2.circle(sparse_frame, (100, 100), 5, 255, -1)

    estimator.estimate(sparse_frame, timestamp=100.0)
    est = estimator.estimate(sparse_frame, timestamp=100.1)

    assert not est.is_reliable
    assert est.error_reason in ("insufficient_features", "insufficient_tracked_features")


# =============================================================================
# 9. Motion Blur or Inconsistent Optical Flow
# =============================================================================
def test_motion_blur_or_inconsistent_optical_flow():
    """9. Motion blur / corrupt flow: extreme Gaussian blur destroys feature tracking and is marked unreliable."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg1 = _create_textured_background(320, 240)
    # Severe motion blur: 45x45 blur kernel
    blurred = cv2.GaussianBlur(bg1, (45, 45), 20)

    estimator.estimate(bg1, timestamp=100.0)
    est = estimator.estimate(blurred, timestamp=100.1)

    assert not est.is_reliable


# =============================================================================
# 10. Sudden Scene Changes (Scene Cuts / Wild Jolt)
# =============================================================================
def test_sudden_scene_changes():
    """10. Scene change: completely uncorrelated scene change cleanly rejected by inlier ratio or motion limit."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg1 = _create_textured_background(320, 240)
    # Completely different image
    np.random.seed(999)
    bg2 = np.random.randint(0, 256, (240, 320), dtype=np.uint8)

    estimator.estimate(bg1, timestamp=100.0)
    est = estimator.estimate(bg2, timestamp=100.1)

    assert not est.is_reliable
    assert est.error_reason in (
        "low_inlier_ratio",
        "insufficient_inliers",
        "extreme_motion_or_scene_cut",
        "insufficient_tracked_features",
        "affine_estimation_failed",
        "poor_spatial_spread"
    )


# =============================================================================
# 11. Incorrect or Irregular Timestamps
# =============================================================================
def test_incorrect_or_irregular_timestamps():
    """11. Timestamp checks: negative, zero, or excessive dt (> 1.0s) marked as unreliable."""
    estimator = SparseOpticalFlowEgoMotionEstimator(max_dt_sec=1.0)
    bg = _create_textured_background(320, 240)

    estimator.estimate(bg, timestamp=100.0)

    # Negative dt
    est_neg = estimator.estimate(bg, timestamp=99.0)
    assert not est_neg.is_reliable
    assert est_neg.error_reason == "irregular_timestamp"

    # Excessive dt (2.5 seconds gap)
    est_gap = estimator.estimate(bg, timestamp=102.5)
    assert not est_gap.is_reliable
    assert est_gap.error_reason == "irregular_timestamp"


# =============================================================================
# 12. Resolution Changes
# =============================================================================
def test_resolution_changes():
    """12. Resolution change: handles camera switching resolution gracefully without crash."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg_small = _create_textured_background(320, 240)
    bg_large = _create_textured_background(640, 480)

    estimator.estimate(bg_small, timestamp=100.0)
    # Immediate switch to different resolution
    est = estimator.estimate(bg_large, timestamp=100.1)

    # Successfully handled; marked as resolution_changed (or resets frame)
    assert not est.is_reliable
    # Next frame at new resolution then succeeds!
    est_next = estimator.estimate(bg_large, timestamp=100.2)
    assert est_next.is_reliable


# =============================================================================
# 13. Noisy Feature Tracking & RANSAC Outlier Rejection
# =============================================================================
def test_noisy_feature_tracking_and_outliers():
    """13. Outlier rejection: random localized motion noise rejected by RANSAC."""
    estimator = SparseOpticalFlowEgoMotionEstimator()
    bg1 = _create_textured_background(320, 240)
    bg2 = _warp_affine_transform(bg1, dx_px=10.0, dy_px=0.0)

    # Corrupt 20% of the image with localized noisy patches
    bg2[20:60, 20:60] = np.random.randint(0, 255, (40, 40), dtype=np.uint8)

    estimator.estimate(bg1, timestamp=100.0)
    est = estimator.estimate(bg2, timestamp=100.1)

    # RANSAC successfully filters corrupted region
    assert est.is_reliable
    assert abs(est.dx - (10.0 / 320.0)) < 0.008


# =============================================================================
# 14. Ego-Motion Compensation Preserving Genuine Object Movement
# =============================================================================
def test_ego_motion_compensation_preserving_genuine_object_movement():
    """
    14. Genuine object movement:
    When a person walks right (+0.35/s) while camera pans right (ego dx = -0.15/s):
    Apparent speed in image = +0.20/s.
    Ego-motion compensation computes: true speed = +0.20 - (-0.15) = +0.35/s.
    Movement is correctly classified as MOVING_RIGHT!
    """
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.10)
    t0 = 100.0
    dt = 0.10

    # Camera panning right: background moves left in image by dx = -0.015 per frame (-0.15/s)
    ego = EgoMotionEstimate(
        dx=-0.015,
        dy=0.0,
        rotation_rad=0.0,
        scale=1.0,
        is_reliable=True,
        confidence=0.90,
        dt=dt,
        timestamp=t0
    )

    # Person walking right in world at +0.35/s.
    # In camera frame, apparent displacement is (+0.35 - 0.15) * dt = +0.02 per frame (+0.20/s)
    for i in range(5):
        t = t0 + i * dt
        xc = 0.30 + i * 0.02
        det = Detection("person", 0.90, BoundingBox(xc - 0.08, 0.30, xc + 0.08, 0.70), sector="center")
        tracks = tracker.update([det], timestamp=t, ego_motion=ego)

    assert len(tracks) == 1
    track = tracks[0]
    assert track.state == TrackState.CONFIRMED
    assert track.ego_motion_compensated is True
    # Apparent speed is ~0.20
    assert abs(track.speed_x - 0.20) < 0.05
    # Compensated speed is ~0.35
    assert abs(track.compensated_speed_x - 0.35) < 0.05
    # Movement is MOVING_RIGHT
    assert track.movement == MovementDirection.MOVING_RIGHT


# =============================================================================
# 15. Stationary Obstacle Preserved as STATIONARY during Camera Pan
# =============================================================================
def test_stationary_obstacle_preserved_during_camera_pan():
    """
    When camera pans right (ego dx = -0.03 per frame, v_ego = -0.30/s):
    A stationary obstacle has apparent speed in image = -0.30/s.
    WITHOUT compensation, it would be misclassified as MOVING_LEFT.
    WITH compensation, true speed = -0.30 - (-0.30) = 0.0/s -> STATIONARY!
    """
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.10)
    t0 = 100.0
    dt = 0.10

    ego = EgoMotionEstimate(
        dx=-0.030,
        dy=0.0,
        rotation_rad=0.0,
        scale=1.0,
        is_reliable=True,
        confidence=0.88,
        dt=dt,
        timestamp=t0
    )

    # Obstacle appears to drift left in image solely due to camera pan
    for i in range(5):
        t = t0 + i * dt
        xc = 0.50 - i * 0.030
        det = Detection("chair", 0.88, BoundingBox(xc - 0.08, 0.40, xc + 0.08, 0.80), sector="center")
        tracks = tracker.update([det], timestamp=t, ego_motion=ego)

    track = tracks[0]
    assert track.ego_motion_compensated is True
    # Apparent speed is negative (-0.30)
    assert track.speed_x < -0.20
    # Compensated speed is ~0.0
    assert abs(track.compensated_speed_x) < 0.05
    # Correctly classified as STATIONARY!
    assert track.movement == MovementDirection.STATIONARY


def test_stationary_obstacle_with_full_affine_transform_matrix():
    """
    Validates that a stationary object remains stationary when the full affine transform matrix
    is applied to Kalman position prediction without double compensation.
    """
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.10)
    t0 = 100.0
    dt = 0.10
    dx = -0.030

    for i in range(6):
        t = t0 + i * dt
        M_norm = np.array([[1.0, 0.0, dx], [0.0, 1.0, 0.0]], dtype=np.float64)
        ego = EgoMotionEstimate(
            dx=dx, dy=0.0, rotation_rad=0.0, scale=1.0,
            transform_matrix=M_norm, is_reliable=True, confidence=0.92,
            dt=dt, timestamp=t
        )
        xc = 0.50 + i * dx
        det = Detection("chair", 0.90, BoundingBox(xc - 0.06, 0.40, xc + 0.06, 0.60), sector="center")
        tracks = tracker.update([det], timestamp=t, ego_motion=ego)

    track = tracks[0]
    assert track.ego_motion_compensated is True
    assert abs(track.compensated_speed_x) < 0.05
    assert abs(track.speed_x - (-0.30)) < 0.05
    assert track.movement == MovementDirection.STATIONARY


def test_moving_person_with_full_affine_transform_matrix():
    """
    Validates that a moving person (v_true = +0.35) undergoing camera pan (v_ego = -0.15)
    retains their genuine physical movement without double compensation.
    """
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.10)
    t0 = 100.0
    dt = 0.10
    v_true = 0.35
    v_ego = -0.15
    dx = v_ego * dt

    for i in range(6):
        t = t0 + i * dt
        M_norm = np.array([[1.0, 0.0, dx], [0.0, 1.0, 0.0]], dtype=np.float64)
        ego = EgoMotionEstimate(
            dx=dx, dy=0.0, rotation_rad=0.0, scale=1.0,
            transform_matrix=M_norm, is_reliable=True, confidence=0.92,
            dt=dt, timestamp=t
        )
        xc = 0.30 + i * (v_true + v_ego) * dt
        det = Detection("person", 0.90, BoundingBox(xc - 0.07, 0.30, xc + 0.07, 0.70), sector="center")
        tracks = tracker.update([det], timestamp=t, ego_motion=ego)

    track = tracks[0]
    assert track.ego_motion_compensated is True
    assert abs(track.compensated_speed_x - v_true) < 0.05
    assert abs(track.speed_x - (v_true + v_ego)) < 0.05
    assert track.movement == MovementDirection.MOVING_RIGHT


# =============================================================================
# 16. Kalman Covariance Remaining Numerically Stable
# =============================================================================
def test_kalman_covariance_remaining_numerically_stable():
    """15. Covariance stability: 50 consecutive ego-motion transform steps preserve positive semi-definiteness and no NaN/Inf."""
    initial_box = BoundingBox(0.4, 0.4, 0.6, 0.6)
    kf = KalmanBoxTracker(initial_box, initial_time=100.0)

    for i in range(50):
        t = 100.0 + i * 0.05
        # Alternating motion
        dx = 0.01 if i % 2 == 0 else -0.01
        M_norm = np.array([
            [1.0, 0.0, dx],
            [0.0, 1.0, 0.0]
        ], dtype=np.float64)
        ego = EgoMotionEstimate(
            dx=dx, dy=0.0, rotation_rad=0.0, scale=1.0,
            transform_matrix=M_norm, is_reliable=True, confidence=0.85,
            dt=0.05, timestamp=t
        )
        kf.predict(t, ego_motion=ego)

    # Check state vector and covariance
    assert not np.isnan(kf.x).any()
    assert not np.isinf(kf.x).any()
    assert not np.isnan(kf.P).any()
    assert not np.isinf(kf.P).any()

    # Covariance diagonal must be positive and bounded
    diag = np.diag(kf.P)
    assert (diag > 0).all()
    assert (diag < 10.0).all()

    # Matrix symmetry
    assert np.allclose(kf.P, kf.P.T, atol=1e-6)


# =============================================================================
# 17. Track ID Stability Across Camera Motion
# =============================================================================
def test_track_id_stability_across_camera_motion():
    """16. Track ID stability: continuous track ID retention without fragmentation during camera pan."""
    tracker = TemporalTracker(min_hits=2, iou_threshold=0.10)
    t0 = 100.0
    dt = 0.05

    for i in range(25):
        t = t0 + i * dt
        dx = 0.008
        M_norm = np.array([[1.0, 0.0, dx], [0.0, 1.0, 0.0]], dtype=np.float64)
        ego = EgoMotionEstimate(
            dx=dx, dy=0.0, rotation_rad=0.0, scale=1.0,
            transform_matrix=M_norm, is_reliable=True, confidence=0.90,
            dt=dt, timestamp=t
        )
        # Person shifts right in frame with camera
        xc = 0.20 + i * dx
        det = Detection("person", 0.90, BoundingBox(xc - 0.07, 0.30, xc + 0.07, 0.70), sector="left")
        tracks = tracker.update([det], timestamp=t, ego_motion=ego)

    assert len(tracks) == 1
    assert tracks[0].track_id == 1
    assert tracker._next_track_id == 2  # Zero track ID churn!


# =============================================================================
# 18. Announcement Deduplication Compatibility with Ego-Motion Compensation
# =============================================================================
def test_announcement_deduplication_compatibility_with_ego_motion():
    """
    17. Deduplication compatibility:
    A stationary obstacle undergoing camera jitter does NOT trigger duplicate announcements.
    """
    fake_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=fake_backend)
    decision = SceneDecisionEngine(speech_manager=speech_mgr, language="ne")
    analyzer = SceneAnalyzer()
    tracker = TemporalTracker(min_hits=1, iou_threshold=0.15)

    t0 = 100.0
    dt = 0.05

    for i in range(20):
        t = t0 + i * dt
        # Camera has slight jitter dx = 0.003
        jitter = 0.003 if i % 2 == 0 else -0.003
        ego = EgoMotionEstimate(
            dx=jitter, dy=0.0, rotation_rad=0.0, scale=1.0,
            is_reliable=True, confidence=0.85,
            dt=dt, timestamp=t
        )
        det = Detection("chair", 0.90, BoundingBox(0.40 + jitter, 0.40, 0.60 + jitter, 0.80), sector="center")
        tracks = tracker.update([det], timestamp=t, ego_motion=ego)
        assessment = analyzer.analyze_scene(tracks, frame_id=i + 1, timestamp=t)
        decision.process_scene(assessment, current_time=t)

    time.sleep(0.05)
    # Exactly ONE initial announcement; zero repeat announcements dispatched
    assert len(fake_backend.spoken_history) == 1
    speech_mgr.shutdown()


# =============================================================================
# 19. Full Covariance Jacobian with Rotation, Scaling, and PSD Verification
# =============================================================================
def test_full_covariance_jacobian_rotation_scale_psd():
    """
    19. Full covariance Jacobian:
    Verifies that under non-zero rotation and scaling:
    - Center coordinates and velocity vectors are transformed by affine rotation R.
    - Width and height scale by s.
    - Full 8x8 covariance matrix P remains strictly symmetric.
    - All eigenvalues remain strictly positive (positive semi-definite / positive definite).
    - Position, velocity, and cross-covariance blocks rotate consistently.
    """
    initial_box = BoundingBox(0.30, 0.20, 0.50, 0.60)
    kf = KalmanBoxTracker(initial_box, initial_time=100.0)

    # Induce initial non-zero velocities and anisotropic cross-covariance
    kf.x[4] = 0.10  # vx = +0.10
    kf.x[5] = -0.05 # vy = -0.05
    kf.P[0, 1] = 0.001
    kf.P[1, 0] = 0.001
    kf.P[0, 4] = 0.002
    kf.P[4, 0] = 0.002
    kf.P = 0.5 * (kf.P + kf.P.T)

    theta_deg = 15.0
    theta_rad = math.radians(theta_deg)
    s = 1.05
    cos_t = math.cos(theta_rad)
    sin_t = math.sin(theta_rad)

    # 2x2 rotation-scaling matrix
    R = np.array([
        [s * cos_t, -s * sin_t],
        [s * sin_t,  s * cos_t]
    ], dtype=np.float64)

    dx = 0.02
    dy = -0.01
    M_norm = np.array([
        [R[0, 0], R[0, 1], dx],
        [R[1, 0], R[1, 1], dy]
    ], dtype=np.float64)

    ego = EgoMotionEstimate(
        dx=dx,
        dy=dy,
        rotation_rad=theta_rad,
        scale=s,
        transform_matrix=M_norm,
        is_reliable=True,
        confidence=0.95,
        dt=0.05,
        timestamp=100.05
    )

    xc_init, yc_init = kf.x[0], kf.x[1]
    vx_init, vy_init = kf.x[4], kf.x[5]

    # Predict with ego-motion
    pred_box = kf.predict(timestamp=100.05, ego_motion=ego)

    # 1. Verify symmetry of full 8x8 covariance
    assert np.allclose(kf.P, kf.P.T, atol=1e-12), "Covariance matrix must be strictly symmetric"

    # 2. Verify positive definiteness (all eigenvalues > 0)
    eigenvalues = np.linalg.eigvalsh(kf.P)
    assert (eigenvalues > 0).all(), f"All eigenvalues must be positive, min was {np.min(eigenvalues)}"

    # 3. Verify positive diagonal variances
    diag_vars = np.diag(kf.P)
    assert (diag_vars > 0).all(), "All diagonal variances must be positive"

    # 4. Verify center coordinate transformation
    expected_xc = R[0, 0] * (xc_init + vx_init * 0.05) + R[0, 1] * (yc_init + vy_init * 0.05) + dx
    expected_yc = R[1, 0] * (xc_init + vx_init * 0.05) + R[1, 1] * (yc_init + vy_init * 0.05) + dy
    assert abs(kf.x[0] - expected_xc) < 1e-5
    assert abs(kf.x[1] - expected_yc) < 1e-5

    # 5. Verify velocity vector rotation
    expected_vx = R[0, 0] * vx_init + R[0, 1] * vy_init
    expected_vy = R[1, 0] * vx_init + R[1, 1] * vy_init
    assert abs(kf.x[4] - expected_vx) < 1e-5
    assert abs(kf.x[5] - expected_vy) < 1e-5

    # 6. Verify width and height scaling
    assert abs(kf.x[2] - 0.20 * s) < 1e-5
    assert abs(kf.x[3] - 0.40 * s) < 1e-5

