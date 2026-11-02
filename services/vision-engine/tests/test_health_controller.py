"""
Trinetra SensorHealthController Unit Test Suite
Validates feature gating, spatial 3x3 quality checks, boundary inflation rejection,
luminance-coupled white wall disambiguation, 5-state perception lifecycle,
temporal debounce, coasting ceilings, and audio cooldown enforcement.
"""

import time
import cv2
import numpy as np
import pytest

from app.camera.health_controller import (
    PerceptionState,
    SensorHealthController,
    StateActionPacket,
)
from app.camera.sensor_health import (
    ActionRecommendation,
    DegradationReason,
    HealthStatus,
)


def create_synthetic_scene(width: int = 640, height: int = 480) -> np.ndarray:
    """Creates realistic natural street scene with sidewalk pavers and building window grids."""
    img = np.full((height, width, 3), 128, dtype=np.uint8)
    tile_size = 32
    for y in range(height // 2, height, tile_size):
        for x in range(0, width, tile_size):
            if (x // tile_size + y // tile_size) % 2 == 0:
                img[y:y + tile_size, x:x + tile_size] = [90, 95, 100]
            else:
                img[y:y + tile_size, x:x + tile_size] = [140, 145, 150]
    cv2.rectangle(img, (40, 40), (260, 240), (60, 60, 180), -1)
    cv2.line(img, (0, 420), (640, 420), (240, 240, 240), 3)
    cv2.putText(img, "KATHMANDU", (60, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return cv2.GaussianBlur(img, (3, 3), 0.8)


def test_feature_flag_disabled_by_default(monkeypatch):
    """Verifies that the controller is disabled by default and runs in pass-through mode."""
    monkeypatch.delenv("TRINETRA_ENABLE_SENSOR_HEALTH", raising=False)
    ctrl = SensorHealthController()
    assert ctrl.is_enabled() is False

    scene = create_synthetic_scene()
    ass, action = ctrl.evaluate_frame(scene, frame_id=1, timestamp=100.0)

    # Pass-through guarantees nominal execution and zero interference
    assert action.state == PerceptionState.VALID_OBSERVATION
    assert action.should_run_dnn is True
    assert action.kalman_action == "MEASUREMENT_UPDATE"
    assert action.audio_chime is None
    assert ass.status == HealthStatus.NORMAL


def test_feature_flag_dynamic_enable():
    """Verifies that enabling controller dynamically activates full diagnostics."""
    ctrl = SensorHealthController(enabled=False)
    assert ctrl.is_enabled() is False
    ctrl.set_enabled(True)
    assert ctrl.is_enabled() is True

    scene = create_synthetic_scene()
    ass, action = ctrl.evaluate_frame(scene, frame_id=1, timestamp=100.0)
    assert action.state == PerceptionState.VALID_OBSERVATION
    assert action.should_run_dnn is True
    assert ass.latency_ms > 0.0


def test_spatial_3x3_partial_occlusion_intercepted():
    """Verifies that a 50% bottom lens obstruction is intercepted via the 3x3 spatial grid."""
    ctrl = SensorHealthController(enabled=True)
    scene = create_synthetic_scene()
    # 50% bottom occluded by dark cloth
    scene[240:, :] = 15

    ass, action = ctrl.evaluate_frame(scene, frame_id=1, timestamp=100.0)
    assert ass.is_occluded is True
    assert DegradationReason.OCCLUDED_LENS in ass.reasons
    assert ass.status == HealthStatus.SEVERELY_DEGRADED


def test_white_wall_luminance_coupling():
    """Verifies that a well-lit white wall is classified as LOW_TEXTURE rather than OCCLUDED_LENS."""
    ctrl = SensorHealthController(enabled=True)
    # Bright white wall (mean 180, contrast 1.5)
    wall = np.full((480, 640, 3), 180, dtype=np.uint8)
    wall = np.clip(wall.astype(np.int16) + np.random.normal(0, 1.0, (480, 640, 3)), 0, 255).astype(np.uint8)

    ass, action = ctrl.evaluate_frame(wall, frame_id=1, timestamp=100.0)
    assert not ass.is_occluded
    assert DegradationReason.LOW_TEXTURE in ass.reasons
    assert ass.status == HealthStatus.DEGRADED
    assert action.state == PerceptionState.TEMPORARILY_DEGRADED
    assert action.should_run_dnn is True  # still executes with caution


def test_dappled_sunlight_debounce():
    """Verifies that rapid exposure oscillation under dappled sunlight emits ZERO chimes."""
    ctrl = SensorHealthController(enabled=True, chime_cooldown_seconds=5.0)
    scene = create_synthetic_scene()

    chimes = []
    for i in range(30):
        t = i * 0.033
        # Alternate between shadow and sunbeam
        scale = 0.25 if (i % 2 == 0) else 2.5
        frame = np.clip(scene.astype(np.float32) * scale, 0, 255).astype(np.uint8)
        ass, action = ctrl.evaluate_frame(frame, frame_id=i, timestamp=t)
        if action.audio_chime:
            chimes.append(action.audio_chime)

    # 3-frame debounce prevents single-frame glare spikes from entering SENSOR_UNAVAILABLE
    assert len(chimes) == 0


def test_5_state_lifecycle_transitions():
    """Verifies all 5 formal state transitions in sequence."""
    ctrl = SensorHealthController(
        enabled=True,
        degrade_debounce_frames=3,
        recovery_debounce_frames=3,
        max_coasting_frames=5,
        max_coasting_duration_seconds=0.25
    )
    clean_scene = create_synthetic_scene()
    dark_frame = np.full((480, 640, 3), 5, dtype=np.uint8)

    # Phase 1: Nominal
    ass, act = ctrl.evaluate_frame(clean_scene, frame_id=1, timestamp=0.0)
    assert act.state == PerceptionState.VALID_OBSERVATION
    assert act.should_run_dnn is True

    # Phase 2: Enter darkness (frame 1 and 2: debouncing)
    ass, act = ctrl.evaluate_frame(dark_frame, frame_id=2, timestamp=0.033)
    assert act.state == PerceptionState.VALID_OBSERVATION  # debouncing
    ass, act = ctrl.evaluate_frame(dark_frame, frame_id=3, timestamp=0.066)
    assert act.state == PerceptionState.VALID_OBSERVATION  # debouncing

    # Frame 3: Debounce satisfied -> SENSOR_UNAVAILABLE
    ass, act = ctrl.evaluate_frame(dark_frame, frame_id=4, timestamp=0.100)
    assert act.state == PerceptionState.SENSOR_UNAVAILABLE
    assert act.should_run_dnn is False
    assert act.audio_chime == "CHIME_UNAVAILABLE"
    assert act.kalman_action == "COAST_ONLY"

    # Phase 3: Coasting for 5 frames
    for i in range(5):
        t = 0.133 + i * 0.033
        ass, act = ctrl.evaluate_frame(dark_frame, frame_id=5 + i, timestamp=t)

    # Frame 10: Coasting ceiling exceeded -> STALE_TERMINATED
    assert act.state == PerceptionState.STALE_TERMINATED
    assert act.tracks_purged is True
    assert act.kalman_action == "PURGE_TRACKS"

    # Phase 4: Recovery (Frames 1-2 clean: debouncing recovery)
    ass, act = ctrl.evaluate_frame(clean_scene, frame_id=11, timestamp=0.350)
    assert act.state == PerceptionState.STALE_TERMINATED  # waiting for 3 clean frames
    ass, act = ctrl.evaluate_frame(clean_scene, frame_id=12, timestamp=0.383)
    assert act.state == PerceptionState.STALE_TERMINATED

    # Frame 3 clean: Recovery confirmed -> RECOVERY_TRANSITION
    ass, act = ctrl.evaluate_frame(clean_scene, frame_id=13, timestamp=0.416)
    assert act.state == PerceptionState.RECOVERY_TRANSITION
    assert act.audio_chime == "CHIME_RECOVERY"
    assert act.kalman_action == "INIT_FRESH"

    # Frame 4 clean: Seamless handoff to VALID_OBSERVATION
    ass, act = ctrl.evaluate_frame(clean_scene, frame_id=14, timestamp=0.450)
    assert act.state == PerceptionState.VALID_OBSERVATION
    assert act.should_run_dnn is True


def test_coasting_ceiling_elapsed_time_limit():
    """Verifies that coasting expires on elapsed time (>0.20s) even with low frame count (variable FPS)."""
    ctrl = SensorHealthController(
        enabled=True,
        degrade_debounce_frames=1,
        max_coasting_duration_seconds=0.20,
        max_coasting_frames=10
    )
    dark_frame = np.full((480, 640, 3), 5, dtype=np.uint8)

    # Step 1: Immediate outage
    ctrl.evaluate_frame(dark_frame, frame_id=1, timestamp=1.000)
    assert ctrl.state == PerceptionState.SENSOR_UNAVAILABLE

    # Step 2: Second frame arrives 0.25s later (e.g. camera driver lag)
    # Even though coast_frames=2 (< 10), elapsed time 0.25s > 0.20s ceiling
    ass, act = ctrl.evaluate_frame(dark_frame, frame_id=2, timestamp=1.250)
    assert act.state == PerceptionState.STALE_TERMINATED
    assert act.tracks_purged is True


def test_chime_cooldown_enforcement():
    """Verifies that non-exempt audio chimes strictly honor the 5.0-second cooldown."""
    ctrl = SensorHealthController(
        enabled=True,
        degrade_debounce_frames=1,
        chime_cooldown_seconds=5.0
    )
    dark_frame = np.full((480, 640, 3), 5, dtype=np.uint8)

    # Outage 1 at t=1.0
    _, act1 = ctrl.evaluate_frame(dark_frame, frame_id=1, timestamp=1.0)
    assert act1.audio_chime == "CHIME_UNAVAILABLE"

    # Outage 2 at t=2.5 (1.5s later, cooldown active)
    ctrl.state = PerceptionState.VALID_OBSERVATION  # force re-test
    _, act2 = ctrl.evaluate_frame(dark_frame, frame_id=2, timestamp=2.5)
    assert act2.audio_chime is None  # blocked by cooldown

    # Outage 3 at t=6.5 (5.5s later, cooldown expired)
    ctrl.state = PerceptionState.VALID_OBSERVATION
    _, act3 = ctrl.evaluate_frame(dark_frame, frame_id=3, timestamp=6.5)
    assert act3.audio_chime == "CHIME_UNAVAILABLE"


def test_empty_or_corrupted_input_safety():
    """Verifies safe fallback without unhandled exceptions on corrupt/empty inputs."""
    ctrl = SensorHealthController(enabled=True)
    ass_bytes, act_bytes = ctrl.evaluate_frame(b"", frame_id=99)
    assert ass_bytes.status == HealthStatus.SEVERELY_DEGRADED

    ass_arr, act_arr = ctrl.evaluate_frame(np.array([]), frame_id=100)
    assert ass_arr.status == HealthStatus.SEVERELY_DEGRADED
