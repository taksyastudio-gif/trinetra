"""
Trinetra Priority 4.3 — Sensor-Health Gatekeeper Empirical Benchmark
Measures latency statistics across 1,000 frames under diverse visual conditions:
- Sharp native 640x480 BGR frames
- Compressed raw JPEG bytes (DCT 2x reduced decode)
- Motion blurred frames (camera shake)
- Defocused frames (severe optical blur)
- Pitch black / twilight frames
- Saturated / overexposed frames
- Uniform occluded frames (covered lens)
- Textureless flat surfaces

Calculates:
- Execution latency: Mean, Median (p50), p95, p99, Min, Max, StdDev
- Resolution scaling: Native 640x480 vs 320x240 downsampled vs 160x120
- Classification accuracy: False Rejection Rate (FRR) on sharp frames, Missed Degradation Rate (MDR)
"""

import json
import os
import sys
import time
from typing import Dict, List, Tuple

import cv2
import numpy as np

# Ensure vision-engine is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.camera.sensor_health import (
    ActionRecommendation,
    DegradationReason,
    HealthStatus,
    SensorHealthAssessment,
    SensorHealthGatekeeper,
    SensorHealthThresholds,
)


def generate_benchmark_dataset(num_samples: int = 100) -> Dict[str, List[np.ndarray]]:
    """Generates synthetic and fixture test frames across 8 operational regimes."""
    dataset: Dict[str, List[np.ndarray]] = {
        "sharp_natural": [],
        "motion_blur": [],
        "defocus_blur": [],
        "pitch_black": [],
        "twilight_dim": [],
        "overexposed": [],
        "occluded_lens": [],
        "low_texture_wall": [],
    }

    # Base image: Try loading real fixture, otherwise generate synthetic sharp scene
    fixture_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../apps/desktop/trinetra-frame.jpg"))
    if os.path.exists(fixture_path):
        base_img = cv2.imread(fixture_path)
    else:
        # Fallback synthetic scene
        base_img = np.full((480, 640, 3), 128, dtype=np.uint8)
        cv2.rectangle(base_img, (40, 40), (300, 300), (60, 60, 180), -1)
        cv2.putText(base_img, "KATHMANDU", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    h, w = base_img.shape[:2]

    # Motion blur kernel (walking camera shake)
    k_shake = np.zeros((35, 35), dtype=np.float32)
    cv2.line(k_shake, (2, 2), (32, 32), 1.0, 2)
    k_shake /= k_shake.sum()

    for i in range(num_samples):
        # 1. Sharp frames with slight synthetic perturbation/noise
        noise = np.random.normal(0, 1.5, base_img.shape).astype(np.int16)
        sharp = np.clip(base_img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        dataset["sharp_natural"].append(sharp)

        # 2. Motion blur
        blurred = cv2.filter2D(sharp, -1, k_shake)
        dataset["motion_blur"].append(blurred)

        # 3. Defocus blur (severe optical out-of-focus)
        defocused = cv2.GaussianBlur(sharp, (51, 51), sigmaX=11.0)
        dataset["defocus_blur"].append(defocused)

        # 4. Pitch black (<15 luminance)
        black = np.random.normal(5.0, 2.0, (h, w, 3)).clip(0, 255).astype(np.uint8)
        dataset["pitch_black"].append(black)

        # 5. Twilight / Dim (<40 luminance)
        dim = (sharp.astype(np.float32) * 0.25).clip(0, 255).astype(np.uint8)
        dataset["twilight_dim"].append(dim)

        # 6. Overexposed (>240 luminance)
        bright = np.random.normal(248.0, 3.0, (h, w, 3)).clip(0, 255).astype(np.uint8)
        dataset["overexposed"].append(bright)

        # 7. Fully occluded lens (finger/coat, near-zero contrast)
        occluded = np.full((h, w, 3), 18, dtype=np.uint8)
        occ_noise = np.random.normal(0, 1.0, (h, w, 3)).astype(np.int16)
        dataset["occluded_lens"].append(np.clip(occluded.astype(np.int16) + occ_noise, 0, 255).astype(np.uint8))

        # 8. Low texture wall (smooth beige surface with ambient gradient)
        wall = np.full((h, w), 140, dtype=np.float32)
        for x in range(w):
            wall[:, x] += (x - w // 2) * 0.025
        wall += np.random.normal(0, 1.0, wall.shape)
        wall_bgr = cv2.cvtColor(np.clip(wall, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        dataset["low_texture_wall"].append(wall_bgr)

    return dataset


def benchmark_latencies(
    gatekeeper: SensorHealthGatekeeper,
    dataset: Dict[str, List[np.ndarray]],
    warmup_runs: int = 50
) -> Dict[str, float]:
    """Runs high-precision timing loop across all benchmark conditions."""
    sharp_sample = dataset["sharp_natural"][0]

    # Warmup CPU caches, OpenCV SIMD dispatch, and threadpools
    for _ in range(warmup_runs):
        gatekeeper.assess_frame(sharp_sample)

    latencies_us: List[float] = []

    for category, frames in dataset.items():
        for frame in frames:
            t0 = time.perf_counter_ns()
            gatekeeper.assess_frame(frame)
            t1 = time.perf_counter_ns()
            latencies_us.append((t1 - t0) / 1000.0)

    latencies_ms = np.array(latencies_us) / 1000.0

    return {
        "count": len(latencies_ms),
        "mean_ms": float(np.mean(latencies_ms)),
        "std_ms": float(np.std(latencies_ms)),
        "min_ms": float(np.min(latencies_ms)),
        "p50_ms": float(np.percentile(latencies_ms, 50)),
        "p95_ms": float(np.percentile(latencies_ms, 95)),
        "p99_ms": float(np.percentile(latencies_ms, 99)),
        "max_ms": float(np.max(latencies_ms)),
        "fps_throughput": float(1000.0 / np.mean(latencies_ms)),
    }


def benchmark_jpeg_bytes_latency(
    gatekeeper: SensorHealthGatekeeper,
    dataset: Dict[str, List[np.ndarray]],
    warmup_runs: int = 50
) -> Dict[str, float]:
    """Measures latency when ingesting compressed raw JPEG bytes."""
    encoded_frames: List[bytes] = []
    for cat in ["sharp_natural", "motion_blur", "defocus_blur"]:
        for f in dataset[cat][:25]:
            _, enc = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 85])
            encoded_frames.append(enc.tobytes())

    for _ in range(warmup_runs):
        gatekeeper.assess_frame(encoded_frames[0])

    latencies_us: List[float] = []
    for b in encoded_frames:
        t0 = time.perf_counter_ns()
        gatekeeper.assess_frame(b)
        t1 = time.perf_counter_ns()
        latencies_us.append((t1 - t0) / 1000.0)

    lat_ms = np.array(latencies_us) / 1000.0
    return {
        "count": len(lat_ms),
        "mean_ms": float(np.mean(lat_ms)),
        "p50_ms": float(np.percentile(lat_ms, 50)),
        "p95_ms": float(np.percentile(lat_ms, 95)),
        "p99_ms": float(np.percentile(lat_ms, 99)),
    }


def benchmark_classification_accuracy(
    gatekeeper: SensorHealthGatekeeper,
    dataset: Dict[str, List[np.ndarray]]
) -> Dict[str, any]:
    """Evaluates False Rejection Rate (FRR) and Missed Degradation Rate (MDR)."""
    results: Dict[str, Dict[str, int]] = {}

    for category, frames in dataset.items():
        results[category] = {
            "total": len(frames),
            "NORMAL": 0,
            "DEGRADED": 0,
            "SEVERELY_DEGRADED": 0,
        }
        for frame in frames:
            ass = gatekeeper.assess_frame(frame)
            results[category][ass.status.value.upper()] += 1

    # False Rejection: sharp frames rejected as degraded
    sharp_total = results["sharp_natural"]["total"]
    sharp_rejected = results["sharp_natural"]["DEGRADED"] + results["sharp_natural"]["SEVERELY_DEGRADED"]
    frr = (sharp_rejected / sharp_total) * 100.0

    # Missed Degradation: degraded frames classified as NORMAL
    degraded_cats = ["motion_blur", "defocus_blur", "pitch_black", "twilight_dim", "overexposed", "occluded_lens"]
    total_degraded = sum(results[c]["total"] for c in degraded_cats)
    missed_degraded = sum(results[c]["NORMAL"] for c in degraded_cats)
    mdr = (missed_degraded / total_degraded) * 100.0

    return {
        "matrix": results,
        "false_rejection_rate_pct": frr,
        "missed_degradation_rate_pct": mdr,
    }


def main():
    print("=============================================================")
    print("TRINETRA PRIORITY 4.3 — SENSOR-HEALTH GATEKEEPER BENCHMARK")
    print("=============================================================")
    print("Generating 800 test frames across 8 operational conditions...")
    dataset = generate_benchmark_dataset(num_samples=100)

    # 1. Standard Gatekeeper (320x240 eval)
    gk_default = SensorHealthGatekeeper()
    print("\n[1/3] Benchmarking BGR Array Latency (Downsampled to 320x240)...")
    bgr_stats = benchmark_latencies(gk_default, dataset)
    print(f"  Frames Evaluated : {bgr_stats['count']}")
    print(f"  Mean Latency     : {bgr_stats['mean_ms']:.3f} ms (Std: {bgr_stats['std_ms']:.3f} ms)")
    print(f"  Median (p50)     : {bgr_stats['p50_ms']:.3f} ms")
    print(f"  95th Percentile  : {bgr_stats['p95_ms']:.3f} ms")
    print(f"  99th Percentile  : {bgr_stats['p99_ms']:.3f} ms")
    print(f"  Throughput       : {bgr_stats['fps_throughput']:.1f} FPS (single-threaded CPU)")

    # 2. Native Resolution (640x480 eval without downsampling)
    gk_native = SensorHealthGatekeeper(SensorHealthThresholds(target_eval_width=640, target_eval_height=480))
    print("\n[2/3] Benchmarking Native 640x480 Latency (No downsampling)...")
    native_stats = benchmark_latencies(gk_native, dataset)
    print(f"  Mean Latency     : {native_stats['mean_ms']:.3f} ms")
    print(f"  Median (p50)     : {native_stats['p50_ms']:.3f} ms")
    print(f"  95th Percentile  : {native_stats['p95_ms']:.3f} ms")

    # 3. Compressed Raw JPEG Ingestion
    print("\n[3/3] Benchmarking Compressed Raw JPEG Ingestion (DCT 2x reduced)...")
    jpeg_stats = benchmark_jpeg_bytes_latency(gk_default, dataset)
    print(f"  Mean Latency     : {jpeg_stats['mean_ms']:.3f} ms")
    print(f"  Median (p50)     : {jpeg_stats['p50_ms']:.3f} ms")
    print(f"  95th Percentile  : {jpeg_stats['p95_ms']:.3f} ms")

    # 4. Classification Accuracy & Error Rates
    print("\n[Accuracy] Evaluating Classification Confusion Matrix...")
    acc_stats = benchmark_classification_accuracy(gk_default, dataset)
    print(f"  False Rejection Rate (FRR)   : {acc_stats['false_rejection_rate_pct']:.2f}%")
    print(f"  Missed Degradation Rate (MDR): {acc_stats['missed_degradation_rate_pct']:.2f}%")
    print("\nCategory Distribution:")
    for cat, counts in acc_stats["matrix"].items():
        print(f"  {cat:20}: NORMAL={counts['NORMAL']}, DEGRADED={counts['DEGRADED']}, SEVERELY={counts['SEVERELY_DEGRADED']}")

    # Export benchmark report as JSON for documentation
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../docs/research/priority-4.3"))
    os.makedirs(out_dir, exist_ok=True)
    report_file = os.path.join(out_dir, "benchmark_data.json")
    with open(report_file, "w") as f:
        json.dump({
            "bgr_320x240": bgr_stats,
            "bgr_640x480": native_stats,
            "jpeg_bytes": jpeg_stats,
            "accuracy": acc_stats
        }, f, indent=2)
    print(f"\nBenchmark metrics exported to {report_file}")


if __name__ == "__main__":
    main()
