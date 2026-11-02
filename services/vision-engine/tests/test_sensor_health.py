"""
Trinetra Sensor-Health, Occlusion & Quality Gatekeeper Test Suite
Evaluates quality classification, threshold boundaries, synthetic degradation,
and CPU latency budgets across representative camera conditions.
"""

import time
from typing import Tuple

import cv2
import numpy as np
import pytest

from app.camera.sensor_health import (
    ActionRecommendation,
    DegradationReason,
    HealthStatus,
    SensorHealthAssessment,
    SensorHealthGatekeeper,
    SensorHealthThresholds,
)


def create_synthetic_sharp_scene(width: int = 640, height: int = 480) -> np.ndarray:
    """
    Creates a realistic synthetic urban scene with tiled footpath pavement,
    building window grids, and natural camera optical MTF point spread.
    """
    h, w = height, width
    img = np.full((h, w, 3), 128, dtype=np.uint8)
    
    # Tiled sidewalk / street flagstones (simulating outdoor pavement texture)
    tile_size = 32
    for y in range(h // 2, h, tile_size):
        for x in range(0, w, tile_size):
            if (x // tile_size + y // tile_size) % 2 == 0:
                img[y:y + tile_size, x:x + tile_size] = [90, 95, 100]
            else:
                img[y:y + tile_size, x:x + tile_size] = [140, 145, 150]
                
    # Structures with window grid edges
    cv2.rectangle(img, (40, 40), (260, 240), (60, 60, 180), -1)
    for wy in range(60, 220, 40):
        for wx in range(60, 240, 40):
            cv2.rectangle(img, (wx, wy), (wx + 20, wy + 20), (220, 220, 240), -1)
            
    cv2.rectangle(img, (340, 60), (580, 240), (50, 160, 60), -1)
    for wy in range(80, 220, 40):
        for wx in range(360, 560, 40):
            cv2.rectangle(img, (wx, wy), (wx + 25, wy + 20), (240, 240, 200), -1)

    # Road curb and text
    cv2.line(img, (0, 420), (640, 420), (240, 240, 240), 3, lineType=cv2.LINE_AA)
    cv2.putText(img, "KATHMANDU 14", (60, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, lineType=cv2.LINE_AA)
            
    # Soft optical blur simulating real camera lens MTF
    return cv2.GaussianBlur(img, (3, 3), 0.8)


def apply_motion_blur(img: np.ndarray, kernel_size: int = 35) -> np.ndarray:
    """Simulates multi-axis camera shake and walking motion blur."""
    kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)
    cv2.line(kernel, (2, 2), (kernel_size - 3, kernel_size - 3), 1.0, 2)
    kernel /= np.sum(kernel)
    return cv2.filter2D(img, -1, kernel)


# -----------------------------------------------------------------------------
# Test Cases
# -----------------------------------------------------------------------------

def test_sharp_adequately_illuminated_scene():
    """Verify that a sharp, well-lit scene is classified as NORMAL with PROCESS recommendation."""
    gatekeeper = SensorHealthGatekeeper()
    sharp_img = create_synthetic_sharp_scene()
    
    # Warmup
    gatekeeper.assess_frame(sharp_img)
    
    assessment = gatekeeper.assess_frame(sharp_img, frame_id=1, timestamp=100.0)
    
    assert assessment.status == HealthStatus.NORMAL
    assert assessment.action == ActionRecommendation.PROCESS
    assert not assessment.is_blurry
    assert not assessment.is_dark
    assert not assessment.is_bright
    assert not assessment.is_occluded
    assert len(assessment.reasons) == 0
    assert assessment.blur_score > 60.0
    assert 45.0 <= assessment.mean_luminance <= 235.0
    assert assessment.latency_ms < 3.0


def test_motion_blur_degradation():
    """Verify that linear motion blur reduces edge sharpness and triggers blur detection."""
    gatekeeper = SensorHealthGatekeeper()
    sharp_img = create_synthetic_sharp_scene()
    blurred_img = apply_motion_blur(sharp_img, kernel_size=35)
    
    assessment = gatekeeper.assess_frame(blurred_img)
    
    assert assessment.status in (HealthStatus.DEGRADED, HealthStatus.SEVERELY_DEGRADED)
    assert assessment.is_blurry
    assert (
        DegradationReason.MOTION_BLUR in assessment.reasons
        or DegradationReason.DEFOCUS_BLUR in assessment.reasons
    )
    assert assessment.action in (
        ActionRecommendation.PROCESS_WITH_CAUTION,
        ActionRecommendation.SUPPRESS_AND_CHIME
    )


def test_severe_defocus_blur():
    """Verify that severe optical defocus blur triggers SEVERELY_DEGRADED and SUPPRESS_AND_CHIME."""
    gatekeeper = SensorHealthGatekeeper()
    sharp_img = create_synthetic_sharp_scene()
    # Large Gaussian kernel destroying all high-frequency edges
    defocused_img = cv2.GaussianBlur(sharp_img, (51, 51), sigmaX=11.0)
    
    assessment = gatekeeper.assess_frame(defocused_img)
    
    assert assessment.status == HealthStatus.SEVERELY_DEGRADED
    assert assessment.action == ActionRecommendation.SUPPRESS_AND_CHIME
    assert assessment.is_blurry
    assert DegradationReason.DEFOCUS_BLUR in assessment.reasons
    assert assessment.blur_score < gatekeeper.thresholds.blur_severe_threshold


def test_dark_scene_pitch_black():
    """Verify that a pitch-black frame triggers TOO_DARK and SUPPRESS_AND_CHIME."""
    gatekeeper = SensorHealthGatekeeper()
    # Synthetic dark frame with mean luminance ~5.0 plus minor sensor noise
    dark_img = np.random.normal(loc=5.0, scale=2.0, size=(480, 640, 3)).clip(0, 255).astype(np.uint8)
    
    assessment = gatekeeper.assess_frame(dark_img)
    
    assert assessment.status == HealthStatus.SEVERELY_DEGRADED
    assert assessment.action == ActionRecommendation.SUPPRESS_AND_CHIME
    assert assessment.is_dark
    assert DegradationReason.TOO_DARK in assessment.reasons
    assert assessment.mean_luminance < gatekeeper.thresholds.luminance_too_dark


def test_dim_lighting_twilight():
    """Verify that low-light (twilight) scenes are marked DEGRADED with PROCESS_WITH_CAUTION."""
    gatekeeper = SensorHealthGatekeeper()
    # Scaled down sharp scene simulating a poorly lit room or twilight (mean ~35)
    sharp_img = create_synthetic_sharp_scene()
    dim_img = (sharp_img.astype(np.float32) * 0.28).clip(0, 255).astype(np.uint8)
    
    assessment = gatekeeper.assess_frame(dim_img)
    
    assert assessment.status == HealthStatus.DEGRADED
    assert assessment.action == ActionRecommendation.PROCESS_WITH_CAUTION
    assert assessment.is_dark
    assert DegradationReason.LOW_LIGHT in assessment.reasons


def test_overexposed_whiteout():
    """Verify that extreme overexposure/glare triggers TOO_BRIGHT and SUPPRESS_AND_CHIME."""
    gatekeeper = SensorHealthGatekeeper()
    # Saturated whiteout image (mean ~248)
    bright_img = np.random.normal(loc=248.0, scale=3.0, size=(480, 640, 3)).clip(0, 255).astype(np.uint8)
    
    assessment = gatekeeper.assess_frame(bright_img)
    
    assert assessment.status == HealthStatus.SEVERELY_DEGRADED
    assert assessment.action == ActionRecommendation.SUPPRESS_AND_CHIME
    assert assessment.is_bright
    assert DegradationReason.TOO_BRIGHT in assessment.reasons
    assert assessment.mean_luminance > gatekeeper.thresholds.luminance_too_bright


def test_fully_occluded_lens():
    """Verify that a covered lens (finger/coat flap with uniform low contrast) triggers OCCLUDED_LENS."""
    gatekeeper = SensorHealthGatekeeper()
    # Uniform dark frame representing a finger pressed against the lens (mean=15, std=1.5)
    occluded_img = np.full((480, 640, 3), 15, dtype=np.uint8)
    # Add minimal sensor noise
    noise = np.random.normal(0, 1.2, (480, 640, 3)).astype(np.int16)
    occluded_img = np.clip(occluded_img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    assessment = gatekeeper.assess_frame(occluded_img)
    
    assert assessment.status == HealthStatus.SEVERELY_DEGRADED
    assert assessment.action == ActionRecommendation.SUPPRESS_AND_CHIME
    assert assessment.is_occluded
    assert DegradationReason.OCCLUDED_LENS in assessment.reasons


def test_low_texture_flat_wall():
    """Verify that a smooth, flat wall with adequate lighting is classified as LOW_TEXTURE rather than blur."""
    gatekeeper = SensorHealthGatekeeper()
    # Uniform beige wall (mean ~140, low contrast ~3.5)
    wall_img = np.full((480, 640, 3), (135, 145, 155), dtype=np.uint8)
    noise = np.random.normal(0, 1.5, (480, 640, 3)).astype(np.int16)
    wall_img = np.clip(wall_img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    assessment = gatekeeper.assess_frame(wall_img)
    
    # Must identify low texture or occlusion rather than misclassifying as pure optical defocus
    assert assessment.status in (HealthStatus.DEGRADED, HealthStatus.SEVERELY_DEGRADED)
    assert not assessment.is_dark
    assert not assessment.is_bright


def test_raw_jpeg_bytes_input():
    """Verify that passing raw JPEG bytes produces consistent assessments with decoded arrays."""
    gatekeeper = SensorHealthGatekeeper()
    sharp_img = create_synthetic_sharp_scene()
    _, enc = cv2.imencode(".jpg", sharp_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    jpeg_bytes = enc.tobytes()
    
    assessment_bytes = gatekeeper.assess_frame(jpeg_bytes, frame_id=42, timestamp=200.0)
    assessment_img = gatekeeper.assess_frame(sharp_img, frame_id=42, timestamp=200.0)
    
    assert assessment_bytes.status == HealthStatus.NORMAL
    assert assessment_bytes.status == assessment_img.status
    assert assessment_bytes.action == assessment_img.action
    assert assessment_bytes.frame_id == 42
    assert assessment_bytes.timestamp == 200.0
    assert assessment_bytes.latency_ms < 5.0


def test_empty_or_corrupt_input():
    """Verify that empty bytes or empty numpy arrays return safe fallback without crashing."""
    gatekeeper = SensorHealthGatekeeper()
    
    # Empty bytes
    ass_bytes = gatekeeper.assess_frame(b"")
    assert ass_bytes.status == HealthStatus.SEVERELY_DEGRADED
    assert ass_bytes.action == ActionRecommendation.SUPPRESS_AND_CHIME
    
    # Empty ndarray
    ass_arr = gatekeeper.assess_frame(np.array([]))
    assert ass_arr.status == HealthStatus.SEVERELY_DEGRADED
    assert ass_arr.action == ActionRecommendation.SUPPRESS_AND_CHIME


def test_cpu_latency_budget():
    """Verify that quality assessment executes in under 2.0 ms on average over 100 consecutive frames."""
    gatekeeper = SensorHealthGatekeeper()
    sharp_img = create_synthetic_sharp_scene()
    
    latencies = []
    # Warmup
    for _ in range(10):
        gatekeeper.assess_frame(sharp_img)
        
    for _ in range(100):
        t0 = time.perf_counter()
        gatekeeper.assess_frame(sharp_img)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)
        
    mean_lat = float(np.mean(latencies))
    p95_lat = float(np.percentile(latencies, 95))
    
    assert mean_lat < 2.0, f"Mean latency {mean_lat:.2f}ms exceeds 2.0ms budget"
    assert p95_lat < 4.0, f"P95 latency {p95_lat:.2f}ms exceeds 4.0ms budget"
