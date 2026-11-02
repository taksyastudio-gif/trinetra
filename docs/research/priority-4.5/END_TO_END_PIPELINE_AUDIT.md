# TRINETRA — PRIORITY 4.5
## End-to-End Perception Pipeline Trace & Architecture Audit

---

### 1. End-to-End Runtime Pipeline Architecture

Trinetra's assistive perception system operates as a decoupled, multi-threaded pipeline designed to guarantee responsive camera capture, deterministic inference latency, and prioritized speech arbitration.

```
[ Camera Hardware / UVC Driver ]
              │
              ▼
[ Stage 1: Camera Acquisition ] (Camera Thread)
              │
              ▼ FramePacket (JPEG, Monotonic frame_id, captured_at)
[ Stage 2: Bounded Capacity-1 Ingestion Slot ] (_pending_packet O(1) overwrite)
              │
              ▼ Worker Wakeup (_new_frame_event)
[ Stage 3: Sensor Health Gatekeeper ] (PerceptionWorkerThread)
       ┌──────┴──────┐
       │             │
  Nominal Frame    Degraded / Occluded
       │             │
       ▼             ▼
[ Stage 4: DNN ]   Bypass Inference (0.0 ms)
(YOLOX + YuNet)    Coast / Purge Tracks
       │             │
       ▼             │
[ Stage 5: Temporal Tracking ] (Kalman Filters)
       │
       ▼
[ Stage 6: Ego-Motion Estimation ] (Sparse Optical Flow)
       │
       ▼
[ Stage 7: Scene Decision Engine ] (Hazard Arbitration & Deduplication)
       │
       ▼ Prioritized SpeechItem
[ Stage 8: Speech Subsystem ] (_speech_worker Daemon Thread)
       │
       ▼
[ Audio Hardware / SAPI / Piper TTS ]
```

---

### 2. Detailed Transition Contracts & Interface Audit

| Stage | Subsystem & File Location | Input Contract | Output Contract | Thread Ownership | Failure Behavior | Recovery Behavior | Current Test Coverage |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Camera Acquisition** | `app/camera/adapter.py` (`OpenCVCameraAdapter`, `FakeCameraAdapter`) | Physical UVC sensor stream or simulated pattern | `FramePacket`: `frame_id`, `captured_at`, `jpeg_bytes`, `width`, `height`, `session_id` | Dedicated capture thread (`_capture_loop`) | Frame capture failure increments `dropped_frames`; device loss sets status inactive. | Auto-reconnect retry loop or user device switch via `/api/camera/device`. | Unit tests in `test_api.py`. |
| **2. Frame Ingestion Slot** | `app/detection/engine.py` (`PerceptionPipeline.submit_frame`) | `FramePacket` | Enqueued in `_pending_packet` (bounded capacity-1) | Main HTTP / Camera thread | Slow inference drops older unconsumed frames in O(1) time without blocking camera. | Fresh frame immediately overwrites stale slot; zero queue backlog. | `test_controlled_sensor_health_integration.py`. |
| **3. Sensor Health Gatekeeper** | `app/camera/health_controller.py` (`SensorHealthController`) | Raw `jpeg_bytes`, `frame_id`, `captured_at` | `(SensorHealthAssessment, StateActionPacket)`: `state`, `should_run_dnn`, `kalman_action` | `PerceptionWorkerThread` | Corrupt JPEG returns empty fallback; degraded scene triggers debounce ($N=2$). | 2 consecutive clean frames trigger `RECOVERY_TRANSITION` $\rightarrow$ `VALID_OBSERVATION`. | `test_sensor_health.py` (11), `test_health_controller.py` (9). |
| **4. Object Detection** | `app/detection/onnx_engine.py`, `face_detector.py`, `fusion.py` | `jpeg_bytes`, `frame_id` | `DetectionResult`: `detections: List[Detection]`, `inference_time_ms`, `model_name` | `PerceptionWorkerThread` | Corrupt model raises `InferenceRuntimeError`; degraded frame bypasses DNN (`0.0 ms`). | Resumes normal ONNX execution upon receiving `should_run_dnn = True`. | `test_onnx_inference.py`, `test_detection_fusion.py`. |
| **5. Temporal Tracking** | `app/detection/engine.py` (`TemporalTracker`, `KalmanBoxTracker`) | `List[Detection]`, `timestamp` | `List[TrackedObject]`: smoothed bounding boxes, velocity vectors, hit streak | `PerceptionWorkerThread` | Missed detections increment `miss_streak`. During outage, coasts up to $0.20\text{ s}$ / $4\text{ frames}$. | Prolonged outage purges tracks; fresh detections instantiate new tracks with monotonic IDs. | `test_kalman_tracking.py` (10). |
| **6. Ego-Motion Compensation** | `app/detection/ego_motion.py` (`EgoMotionEstimator`) | Consecutive grayscale frames ($320 \times 240$), `dt` | Affine transform matrix ($2 \times 3$), rotation $\Delta\theta$, translation $(\Delta x, \Delta y)$ | `PerceptionWorkerThread` | Feature point loss / motion blur returns identity matrix (bypasses compensation). | Features re-acquired on sharp frame; covariance matrix remains positive semi-definite. | `test_ego_motion.py` (21). |
| **7. Scene Decision Engine** | `app/detection/decision.py` (`SceneDecisionEngine`) | `SceneAssessment`: `highest_risk`, `confirmed_tracks`, `is_crowded` | Prioritized announcement dispatch to `SpeechManager` | `PerceptionWorkerThread` | Outage delivers 0 detections $\rightarrow$ suppresses announcements; prevents false chatter. | Fresh hazard triggers announcement subject to category cooldown (2.0s – 6.0s). | `test_scene_decision.py` (8). |
| **8. Speech Arbitration** | `app/audio/speaker.py` (`SpeechManager`) | Spoken text, `SpeechPriority`, `message_key`, `interrupt`, `language` | Audio waveform synthesized and dispatched to speaker | Dispatched to `_speech_worker` daemon thread via `PriorityQueue` | TTS unavailable suppresses audio without crashing; queue overflow drops lowest priority. | Unmute / resume restores playback; interrupt drains lower priority items immediately. | `test_speech_engine.py`, `test_piper_backend.py`. |

---

### 3. Thread Ownership and Inter-Thread Synchronization

1. **Camera Thread:** Exclusively owns the OpenCV `VideoCapture` object. Never executes computer vision algorithms or DNN inference. Communicates with perception solely by writing to the atomic `_pending_packet` pointer under `_pending_lock`.
2. **Perception Worker Thread:** Runs a continuous event-driven loop (`_worker_loop`). Wakes on `_new_frame_event`. Performs sensor health assessment, ONNX inference, Kalman updates, ego-motion estimation, and scene arbitration in a single sequential thread. This eliminates race conditions between detection, tracking, and hazard assessment.
3. **Speech Worker Thread:** Pulls prioritized announcements from `queue.PriorityQueue(maxsize=10)` with a 0.20s timeout. Operates asynchronously from perception so slow audio synthesis (TTS) never blocks frame processing.

---

### 4. Identified Missing Integration Tests

While unit test coverage across individual modules is high (61 passing tests), the audit identified the following integration gaps:
1. **End-to-End Pipeline Stress Test (Camera to Speech without TestClient):**
   A test feeding 100 continuous camera frames through `submit_frame`, simulating a hardware disconnect after frame 30, verifying that speech halts cleanly, and confirming that camera resumption on frame 50 restores perception without memory leaks.
2. **Multi-Session Track Monotonicity Test:**
   A test verifying that when a camera session stops and restarts via `/api/camera/stop` and `/api/camera/start`, track IDs reset cleanly across sessions, whereas in-session outages preserve monotonic progression.
3. **Rapid Language Switch under High Perception Load:**
   A test verifying that switching languages while 10 objects are being actively tracked updates all pending track announcement keys without audio stutter.
