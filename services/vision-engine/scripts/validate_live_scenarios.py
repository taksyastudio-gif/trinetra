"""
Trinetra Real-World Camera & Pipeline Validation Tool (Priority 3.5)
Executes end-to-end hardware validation on Camera 0 using the production ONNX detector,
optical-flow ego-motion estimator, Kalman tracker, trajectory/path-intersection classifier,
scene analyzer, decision engine, and bilingual speech synthesizer.
Logs real-time telemetry without persisting identifiable camera footage.
"""

import argparse
import logging
import os
import sys
import time
from typing import Dict, List, Optional

# Ensure vision-engine is on path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVICE_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _SERVICE_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np

from app.audio.piper_backend import PiperSpeechBackend, is_piper_available
from app.audio.speaker import FakeSpeechBackend, SpeechManager
from app.camera.adapter import FramePacket, OpenCVCameraAdapter
from app.detection.decision import SceneDecisionEngine
from app.detection.ego_motion import SparseOpticalFlowEgoMotionEstimator
from app.detection.engine import PerceptionPipeline
from app.detection.onnx_engine import OnnxDetectionEngine
from app.detection.scene import SceneAnalyzer
from app.detection.tracking import TemporalTracker
from app.detection.trajectory import TrajectoryClassifier

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def run_live_validation(
    duration_sec: float = 10.0,
    camera_index: int = 0,
    language: str = "ne",
    use_real_tts: bool = False,
    scenario_label: str = "General Live Observation"
):
    print("=" * 80)
    print(f"TRINETRA REAL-WORLD VALIDATION: {scenario_label.upper()}")
    print("=" * 80)
    print(f"Target Camera Index:  {camera_index}")
    print(f"Target Language:      {language}")
    print(f"TTS Backend:          {'Piper Neural TTS' if use_real_tts else 'Telemetry Logging (Fake Speech)'}")
    print(f"Test Duration:        {duration_sec:.1f} seconds")
    print("-" * 80)

    # 1. Initialize Camera
    print("[1/5] Initializing Camera Hardware...")
    adapter = OpenCVCameraAdapter(camera_index=camera_index, width=640, height=480)
    try:
        adapter.start()
        print("  -> Camera claimed and active.")
    except Exception as exc:
        print(f"  -> BLOCKED: Failed to open camera hardware: {exc}")
        return {"status": "BLOCKED", "error": str(exc)}

    # 2. Initialize ONNX Detection Engine
    print("[2/5] Initializing ONNX YOLOX-Nano Detection Engine...")
    model_path = os.path.join(_SERVICE_ROOT, "models", "yolox_nano.onnx")
    if not os.path.isfile(model_path):
        print(f"  -> BLOCKED: Model file not found at {model_path}")
        adapter.stop()
        return {"status": "BLOCKED", "error": "model_missing"}
    
    engine = OnnxDetectionEngine(model_path=model_path, confidence_threshold=0.35)
    print("  -> ONNX Engine ready on CPU.")

    # 3. Initialize Speech Backend
    print("[3/5] Initializing Audio/Speech Manager...")
    if use_real_tts and is_piper_available():
        speech_backend = PiperSpeechBackend()
    else:
        speech_backend = FakeSpeechBackend(supported_languages=["ne", "en"])
    speech_mgr = SpeechManager(backend=speech_backend)

    # 4. Construct Integrated Perception Pipeline
    print("[4/5] Initializing Integrated Perception Pipeline...")
    pipeline = PerceptionPipeline(
        engine=engine,
        speech_manager=speech_mgr,
        target_fps=30
    )
    pipeline.language = language

    # 5. Capture Loop and Telemetry Collection
    print(f"[5/5] Streaming and analyzing frames for {duration_sec:.1f}s...\n")
    
    frame_latencies = []
    det_latencies = []
    track_records = []
    dispatched_announcements = []
    start_time = time.time()
    frame_count = 0

    try:
        while (time.time() - start_time) < duration_sec:
            pkt = adapter.capture_packet()
            if pkt is None:
                time.sleep(0.005)
                continue

            frame_count += 1
            t0 = time.perf_counter()
            res = pipeline.process_frame(pkt)
            t1 = time.perf_counter()

            loop_ms = (t1 - t0) * 1000.0
            frame_latencies.append(loop_ms)
            if res:
                det_latencies.append(res.inference_time_ms)

            # Record telemetry of active tracks
            tracks = pipeline.tracker.tracks
            for tr in tracks:
                traj = getattr(tr, "trajectory", None)
                record = {
                    "frame": frame_count,
                    "time": round(time.time() - start_time, 2),
                    "id": tr.track_id,
                    "class": tr.class_name,
                    "conf": round(tr.confidence, 2),
                    "streak": tr.hit_streak,
                    "state": tr.state.value,
                    "sector": tr.sector,
                    "speed_x": tr.compensated_speed_x,
                    "growth_h": tr.compensated_growth_rate_h,
                    "trajectory": traj.classification.value if traj else "none",
                    "intersects_path": traj.intersects_path if traj else False,
                    "time_to_corridor": traj.time_to_corridor if traj else None,
                }
                track_records.append(record)

            time.sleep(0.015)

    except KeyboardInterrupt:
        print("\n[!] Validation interrupted by user.")
    finally:
        adapter.stop()
        speech_mgr.shutdown()
        print("\nCamera hardware successfully released.")

    # Telemetry Compilation
    duration_actual = time.time() - start_time
    fps = frame_count / duration_actual if duration_actual > 0 else 0.0

    if hasattr(speech_backend, "spoken_history"):
        dispatched_announcements = list(speech_backend.spoken_history)

    print("\n" + "=" * 80)
    print("TELEMETRY RESULTS:")
    print("=" * 80)
    print(f"Scenario:                    {scenario_label}")
    print(f"Total Frames Processed:      {frame_count}")
    print(f"Effective Frame Rate:        {fps:.1f} FPS")
    print(f"Mean Pipeline Loop Latency:  {np.mean(frame_latencies):.2f} ms")
    print(f"P95 Pipeline Loop Latency:   {np.percentile(frame_latencies, 95):.2f} ms")
    if det_latencies:
        print(f"Mean YOLOX Detector Latency: {np.mean(det_latencies):.2f} ms")
    
    unique_ids = set(r["id"] for r in track_records)
    print(f"Unique Track IDs Observed:   {len(unique_ids)} (IDs: {sorted(list(unique_ids))})")
    print(f"Total Announcements Spoken:  {len(dispatched_announcements)}")
    for idx, ann in enumerate(dispatched_announcements, 1):
        print(f"  [{idx}] {ann}")

    # Sample trajectory breakdown
    if track_records:
        print("\nTracked Entities Sample (first 10 records):")
        for rec in track_records[:10]:
            print(f"  t={rec['time']}s | ID={rec['id']} {rec['class']} | Sector={rec['sector']} | Trajectory={rec['trajectory']} (intersects={rec['intersects_path']})")

    return {
        "status": "PASS" if frame_count > 0 else "FAIL",
        "fps": round(fps, 1),
        "mean_latency_ms": round(float(np.mean(frame_latencies)), 2) if frame_latencies else 0.0,
        "det_latency_ms": round(float(np.mean(det_latencies)), 2) if det_latencies else 0.0,
        "frame_count": frame_count,
        "announcements": dispatched_announcements,
        "unique_tracks": len(unique_ids)
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trinetra Real-World Hardware Validation")
    parser.add_argument("--duration", type=float, default=6.0, help="Test duration in seconds (default: 6.0)")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--lang", type=str, default="ne", choices=["ne", "en"], help="Target language (ne/en)")
    parser.add_argument("--tts", action="store_true", help="Enable audible Piper neural speech")
    parser.add_argument("--scenario", type=str, default="Stationary Live Validation", help="Scenario description")
    args = parser.parse_args()

    run_live_validation(
        duration_sec=args.duration,
        camera_index=args.camera,
        language=args.lang,
        use_real_tts=args.tts,
        scenario_label=args.scenario
    )
