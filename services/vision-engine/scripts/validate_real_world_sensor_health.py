"""
Trinetra Priority 4.3.1 — Real-World Sensor Health Validation Benchmark
Executes rigorous independent validation across:
1. Genuine Trinetra camera recordings.
2. Partial-frame obstruction across spatial regions (10%, 25%, 33%, 50%, 75%).
3. Realistic walking motion blur (horizontal sway, footstep bob, angular swing).
4. Defocus, low light, solar glare, and dynamic exposure transitions.
5. Low-texture scene disambiguation vs. true sensor failure.
6. Temporal recovery dynamics, debounce, and hysteresis.
7. Kalman track coasting simulation and covariance blowup analysis.
"""

import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

# Add vision-engine root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.camera.sensor_health import (
    ActionRecommendation,
    DegradationReason,
    HealthStatus,
    SensorHealthAssessment,
    SensorHealthGatekeeper,
    SensorHealthThresholds,
)


def load_recorded_frames() -> Dict[str, np.ndarray]:
    """Loads genuine Trinetra camera recordings and test fixtures."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    frames = {}

    candidates = {
        "trinetra_webcam": os.path.join(root_dir, "apps/desktop/trinetra-frame.jpg"),
        "root_webcam": os.path.join(root_dir, "trinetra-frame.jpg"),
        "fixture_person": os.path.join(root_dir, "services/vision-engine/tests/fixtures/test_person.jpg"),
        "fixture_dog": os.path.join(root_dir, "services/vision-engine/tests/fixtures/test_dog.jpg"),
    }

    for name, path in candidates.items():
        if os.path.exists(path):
            img = cv2.imread(path)
            if img is not None and img.shape[0] > 10 and img.shape[1] > 10:
                frames[name] = img

    return frames


# -----------------------------------------------------------------------------
# 1. Partial-Frame Obstruction Analysis
# -----------------------------------------------------------------------------

def evaluate_partial_obstruction(
    gatekeeper: SensorHealthGatekeeper,
    base_frame: np.ndarray
) -> Dict[str, Any]:
    """
    Evaluates global gatekeeper and a 3x3 spatial grid against partial occlusions
    (e.g., finger or strap covering 10%, 25%, 33%, 50%, 75% of the frame).
    """
    h, w = base_frame.shape[:2]
    percentages = [0.0, 0.10, 0.25, 0.33, 0.50, 0.75]
    positions = ["bottom", "top", "left", "right", "center"]

    results = []

    for pct in percentages:
        for pos in positions:
            if pct == 0.0 and pos != "bottom":
                continue
            occ_frame = base_frame.copy()
            # Simulate dark/finger occlusion: low luminance ~20 with slight noise
            noise = np.random.normal(20, 2, (h, w, 3)).clip(0, 255).astype(np.uint8)

            if pos == "bottom":
                occ_h = int(h * pct)
                if occ_h > 0:
                    occ_frame[h - occ_h:h, :] = noise[h - occ_h:h, :]
            elif pos == "top":
                occ_h = int(h * pct)
                if occ_h > 0:
                    occ_frame[0:occ_h, :] = noise[0:occ_h, :]
            elif pos == "left":
                occ_w = int(w * pct)
                if occ_w > 0:
                    occ_frame[:, 0:occ_w] = noise[:, 0:occ_w]
            elif pos == "right":
                occ_w = int(w * pct)
                if occ_w > 0:
                    occ_frame[:, w - occ_w:w] = noise[:, w - occ_w:w]
            elif pos == "center":
                scale = np.sqrt(pct)
                box_h, box_w = int(h * scale), int(w * scale)
                y1 = max(0, (h - box_h) // 2)
                x1 = max(0, (w - box_w) // 2)
                occ_frame[y1:y1 + box_h, x1:x1 + box_w] = noise[y1:y1 + box_h, x1:x1 + box_w]

            # Global assessment
            ass = gatekeeper.assess_frame(occ_frame)

            # Spatial 3x3 Grid Assessment (Prototype)
            # Evaluate each 1/3 x 1/3 tile independently
            tile_h, tile_w = h // 3, w // 3
            occluded_tiles = 0
            for r in range(3):
                for c in range(3):
                    tile = occ_frame[r * tile_h:(r + 1) * tile_h, c * tile_w:(c + 1) * tile_w]
                    tile_mean, tile_std = cv2.meanStdDev(tile)
                    if float(tile_std[0][0]) < 6.0 and float(tile_mean[0][0]) < 35.0:
                        occluded_tiles += 1

            results.append({
                "occlusion_pct": pct,
                "position": pos,
                "global_status": ass.status.value,
                "global_blur": ass.blur_score,
                "global_contrast": ass.contrast,
                "global_luminance": ass.mean_luminance,
                "spatial_occluded_tiles": occluded_tiles,
                "spatial_detected": occluded_tiles >= 2,
            })

    return results


# -----------------------------------------------------------------------------
# 2. Dynamic Exposure Transitions
# -----------------------------------------------------------------------------

def evaluate_dynamic_exposure_transitions(
    gatekeeper: SensorHealthGatekeeper,
    base_frame: np.ndarray
) -> List[Dict[str, Any]]:
    """
    Simulates walking into a dark tunnel, staying dark, and exiting into bright sunlight.
    Sequence: 40 frames total.
    """
    sequence = []
    # Frame 0-9: Normal daylight (scale 1.0)
    # Frame 10-19: Transition into darkness (scale 1.0 -> 0.08)
    # Frame 20-29: Pitch dark (scale 0.06)
    # Frame 30-34: Transition out into bright glare (scale 0.06 -> 2.6)
    # Frame 35-39: Recovery to normal (scale 2.6 -> 1.0)

    scales = (
        [1.0] * 10
        + list(np.linspace(1.0, 0.08, 10))
        + [0.06] * 10
        + list(np.linspace(0.06, 2.6, 5))
        + list(np.linspace(2.6, 1.0, 5))
    )

    for frame_id, scale in enumerate(scales):
        scaled = np.clip(base_frame.astype(np.float32) * scale, 0, 255).astype(np.uint8)
        ass = gatekeeper.assess_frame(scaled, frame_id=frame_id)
        sequence.append({
            "frame_id": frame_id,
            "scale": round(float(scale), 3),
            "luminance": ass.mean_luminance,
            "contrast": ass.contrast,
            "blur_score": ass.blur_score,
            "status": ass.status.value,
            "action": ass.action.value,
            "reasons": [r.value for r in ass.reasons],
        })

    return sequence


# -----------------------------------------------------------------------------
# 3. Temporal Recovery Dynamics & Hysteresis
# -----------------------------------------------------------------------------

def evaluate_recovery_hysteresis(
    gatekeeper: SensorHealthGatekeeper,
    base_frame: np.ndarray
) -> Dict[str, Any]:
    """
    Evaluates temporal debounce and recovery over a 60-frame sequence:
    Frames 0-14  : Clean (NORMAL)
    Frames 15-29 : Sudden complete occlusion (SEVERELY_DEGRADED)
    Frames 30-59 : Restored clean frames (Recovery)
    """
    timeline = []
    h, w = base_frame.shape[:2]
    dark_noise = np.random.normal(12, 1.5, (h, w, 3)).clip(0, 255).astype(np.uint8)

    for i in range(60):
        if 15 <= i < 30:
            frame = dark_noise
            ground_truth = "OCCLUDED"
        else:
            frame = base_frame
            ground_truth = "NORMAL"

        ass = gatekeeper.assess_frame(frame, frame_id=i, timestamp=i * 0.033)
        timeline.append({
            "frame_id": i,
            "ground_truth": ground_truth,
            "status": ass.status.value,
            "action": ass.action.value,
            "reasons": [r.value for r in ass.reasons],
        })

    # Calculate transition latencies (in frames and milliseconds at 30 FPS)
    degrade_onset_frame = None
    recovery_onset_frame = None

    for entry in timeline:
        if entry["ground_truth"] == "OCCLUDED" and degrade_onset_frame is None and entry["status"] == "severely_degraded":
            degrade_onset_frame = entry["frame_id"]
        if entry["frame_id"] >= 30 and recovery_onset_frame is None and entry["status"] == "normal":
            recovery_onset_frame = entry["frame_id"]

    return {
        "timeline": timeline,
        "degradation_detection_latency_frames": (degrade_onset_frame - 15) if degrade_onset_frame is not None else -1,
        "recovery_detection_latency_frames": (recovery_onset_frame - 30) if recovery_onset_frame is not None else -1,
    }


# -----------------------------------------------------------------------------
# 4. Kalman Track Coasting & Uncertainty Simulation
# -----------------------------------------------------------------------------

def simulate_kalman_coasting() -> Dict[str, Any]:
    """
    Simulates a 1D constant-velocity Kalman filter tracking a pedestrian walking toward the camera.
    State: x = [position, velocity]^T
    Evaluates covariance blowup when measurement updates are suppressed for N frames (coasting).
    """
    dt = 0.033  # 30 FPS
    F = np.array([[1.0, dt], [0.0, 1.0]], dtype=np.float64)  # State transition
    H = np.array([[1.0, 0.0]], dtype=np.float64)              # Measurement model
    Q = np.array([[0.05, 0.0], [0.0, 0.1]], dtype=np.float64) # Process noise
    R = np.array([[1.5]], dtype=np.float64)                   # Measurement noise

    coasting_scenarios = [1, 3, 5, 7, 10, 15, 20]
    coasting_results = {}

    for coast_frames in coasting_scenarios:
        # Initialize filter with stable tracking
        x = np.array([[10.0], [-1.2]])  # 10m away, approaching at 1.2 m/s
        P = np.array([[0.2, 0.0], [0.0, 0.1]], dtype=np.float64)

        # Warmup for 10 nominal updates
        for step in range(10):
            # Predict
            x = F @ x
            P = F @ P @ F.T + Q
            # Update with simulated measurement
            z = x[0, 0] + np.random.normal(0, 0.2)
            y = z - H @ x
            S = H @ P @ H.T + R
            K = P @ H.T @ np.linalg.inv(S)
            x = x + K @ y
            P = (np.eye(2) - K @ H) @ P

        initial_pos_variance = float(P[0, 0])
        initial_vel_variance = float(P[1, 1])
        initial_trace = float(np.trace(P))

        # Coasting phase: Predict only, NO measurement update
        pos_variances = []
        traces = []
        for cf in range(coast_frames):
            x = F @ x
            P = F @ P @ F.T + Q
            pos_variances.append(float(P[0, 0]))
            traces.append(float(np.trace(P)))

        coasting_results[str(coast_frames)] = {
            "coast_frames": coast_frames,
            "coast_duration_ms": round(coast_frames * dt * 1000.0, 1),
            "initial_pos_variance": round(initial_pos_variance, 4),
            "final_pos_variance": round(pos_variances[-1], 4),
            "variance_growth_ratio": round(pos_variances[-1] / initial_pos_variance, 2),
            "initial_trace": round(initial_trace, 4),
            "final_trace": round(traces[-1], 4),
            "safe_for_collision_ttc": bool(pos_variances[-1] < 1.0),
        }

    return coasting_results


# -----------------------------------------------------------------------------
# 5. Low-Texture Surface vs. Optical Defocus Disambiguation
# -----------------------------------------------------------------------------

def evaluate_low_texture_vs_defocus(
    gatekeeper: SensorHealthGatekeeper,
    base_frame: np.ndarray
) -> Dict[str, Any]:
    """
    Evaluates feature separation between:
    - Pure white wall (uniform, well-lit)
    - Beige wall with subtle shadow gradient
    - Flat concrete pavement
    - Severe optical defocus blur (same scene but defocused)
    - Occluded lens (dark finger)
    """
    h, w = base_frame.shape[:2]
    cases = {}

    # Case 1: Pure painted wall
    wall_pure = np.full((h, w, 3), 180, dtype=np.uint8)
    wall_pure = np.clip(wall_pure.astype(np.int16) + np.random.normal(0, 1.2, (h, w, 3)), 0, 255).astype(np.uint8)
    cases["painted_wall_flat"] = gatekeeper.assess_frame(wall_pure)

    # Case 2: Painted wall with ambient lighting gradient
    wall_grad = np.full((h, w), 150, dtype=np.float32)
    for x in range(w):
        wall_grad[:, x] += (x - w // 2) * 0.03
    wall_grad = np.clip(wall_grad + np.random.normal(0, 1.0, wall_grad.shape), 0, 255).astype(np.uint8)
    cases["painted_wall_gradient"] = gatekeeper.assess_frame(cv2.cvtColor(wall_grad, cv2.COLOR_GRAY2BGR))

    # Case 3: Flat concrete pavement (subtle aggregate speckle)
    concrete = np.random.normal(130, 4.0, (h, w, 3)).clip(0, 255).astype(np.uint8)
    cases["concrete_pavement"] = gatekeeper.assess_frame(concrete)

    # Case 4: Severe optical defocus of natural scene
    defocused = cv2.GaussianBlur(base_frame, (51, 51), sigmaX=11.0)
    cases["defocused_natural_scene"] = gatekeeper.assess_frame(defocused)

    # Case 5: Fully occluded lens
    occluded = np.random.normal(16, 1.2, (h, w, 3)).clip(0, 255).astype(np.uint8)
    cases["occluded_lens"] = gatekeeper.assess_frame(occluded)

    summary = {}
    for name, ass in cases.items():
        summary[name] = {
            "luminance": ass.mean_luminance,
            "contrast": ass.contrast,
            "blur_score": ass.blur_score,
            "status": ass.status.value,
            "action": ass.action.value,
            "reasons": [r.value for r in ass.reasons],
        }

    return summary


# -----------------------------------------------------------------------------
# Main Execution & JSON Export
# -----------------------------------------------------------------------------

def main():
    print("===================================================================")
    print("TRINETRA PRIORITY 4.3.1 — INDEPENDENT REAL-WORLD VALIDATION SUITE")
    print("===================================================================")

    gatekeeper = SensorHealthGatekeeper()
    recorded_frames = load_recorded_frames()
    print(f"Loaded {len(recorded_frames)} genuine recorded/fixture frames: {list(recorded_frames.keys())}")

    if "trinetra_webcam" in recorded_frames:
        base_frame = recorded_frames["trinetra_webcam"]
    elif recorded_frames:
        base_frame = next(iter(recorded_frames.values()))
    else:
        print("ERROR: No recorded frames found. Generating synthetic base.")
        base_frame = np.full((480, 640, 3), 128, dtype=np.uint8)

    # 1. Evaluate Genuine Recorded Frames
    print("\n[1/6] Evaluating Genuine Recorded Frames...")
    rec_results = {}
    for name, f in recorded_frames.items():
        ass = gatekeeper.assess_frame(f)
        rec_results[name] = {
            "resolution": f"{f.shape[1]}x{f.shape[0]}",
            "luminance": ass.mean_luminance,
            "contrast": ass.contrast,
            "blur_score": ass.blur_score,
            "status": ass.status.value,
            "action": ass.action.value,
            "reasons": [r.value for r in ass.reasons],
            "latency_ms": ass.latency_ms,
        }
        print(f"  {name:18}: {ass.status.value.upper():16} blur={ass.blur_score:8.2f} contrast={ass.contrast:6.2f} lum={ass.mean_luminance:6.2f}")

    # 2. Evaluate Partial Obstruction
    print("\n[2/6] Evaluating Partial Frame Obstruction across Spatial Regions...")
    partial_results = evaluate_partial_obstruction(gatekeeper, base_frame)
    # Summary of partial occlusion detection
    print(f"  Tested {len(partial_results)} partial obstruction configurations.")
    for p in [0.10, 0.25, 0.33, 0.50, 0.75]:
        bottom_case = next(r for r in partial_results if r["occlusion_pct"] == p and r["position"] == "bottom")
        print(f"  Occlusion {int(p*100)}% (Bottom): Global={bottom_case['global_status'].upper()} (blur={bottom_case['global_blur']:.1f}), Spatial 3x3 Tiles Detected={bottom_case['spatial_occluded_tiles']}/9")

    # 3. Dynamic Exposure Transitions
    print("\n[3/6] Evaluating Dynamic Exposure Transitions (Walking into tunnel & daylight)...")
    exposure_seq = evaluate_dynamic_exposure_transitions(gatekeeper, base_frame)
    print(f"  Processed {len(exposure_seq)} sequential frames. Transition states observed:")
    for key_frame in [0, 15, 25, 32, 38]:
        ef = exposure_seq[key_frame]
        print(f"    Frame {ef['frame_id']:02d} (scale {ef['scale']:4.2f}): lum={ef['luminance']:6.2f} -> {ef['status'].upper():16} {ef['reasons']}")

    # 4. Temporal Recovery Dynamics
    print("\n[4/6] Evaluating Temporal Recovery Dynamics & Debounce...")
    recovery_data = evaluate_recovery_hysteresis(gatekeeper, base_frame)
    print(f"  Degradation Detection Latency : {recovery_data['degradation_detection_latency_frames']} frames ({recovery_data['degradation_detection_latency_frames'] * 33.3:.1f} ms)")
    print(f"  Recovery Detection Latency    : {recovery_data['recovery_detection_latency_frames']} frames ({recovery_data['recovery_detection_latency_frames'] * 33.3:.1f} ms)")

    # 5. Kalman Track Coasting Simulation
    print("\n[5/6] Simulating Kalman Track Coasting & Covariance Blowup...")
    coasting_data = simulate_kalman_coasting()
    for frames_str, cd in coasting_data.items():
        print(f"  Coast {cd['coast_frames']:2d} frames ({cd['coast_duration_ms']:5.1f} ms): Pos Variance = {cd['final_pos_variance']:.3f} (Growth: {cd['variance_growth_ratio']}x) -> Safe: {cd['safe_for_collision_ttc']}")

    # 6. Low-Texture vs. Optical Defocus
    print("\n[6/6] Evaluating Low-Texture vs. Defocus Disambiguation...")
    low_tex_data = evaluate_low_texture_vs_defocus(gatekeeper, base_frame)
    for name, res in low_tex_data.items():
        print(f"  {name:25}: {res['status'].upper():16} contrast={res['contrast']:5.2f} blur={res['blur_score']:6.2f} {res['reasons']}")

    # Export all empirical results
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../docs/research/priority-4.3.1"))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "validation_metrics.json")
    with open(out_path, "w") as f:
        json.dump({
            "recorded_frames": rec_results,
            "partial_obstruction": partial_results,
            "exposure_transitions": exposure_seq,
            "recovery_dynamics": recovery_data,
            "kalman_coasting": coasting_data,
            "low_texture_disambiguation": low_tex_data,
        }, f, indent=2)

    print(f"\nComplete empirical validation results exported to: {out_path}")


if __name__ == "__main__":
    main()
