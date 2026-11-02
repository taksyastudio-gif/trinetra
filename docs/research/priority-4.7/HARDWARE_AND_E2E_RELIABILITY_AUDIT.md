# TRINETRA — PRIORITY 4.7 (PHASE 0)
## Read-Only Hardware & End-to-End Reliability Audit Report

**Audit Mode:** STRICT READ-ONLY INVESTIGATION  
**Execution Timestamp:** 2026-11-01  
**Target Environment:** Windows x64, AMD Ryzen 7 6800H, 8 GB RAM, NVIDIA RTX 3050 Ti 4 GB  
**Git Baseline:** Branch `master`, HEAD `8b9222402cc8cdba58a393377234faa8b92f9b1d` (Zero modifications to existing code, zero commits)  

---

### 1. Executive Summary

Trinetra's software architecture demonstrates disciplined design: 124 unit and integration tests pass cleanly, language normalization is strictly enforced, and the multi-threaded bounded-queue perception loop handles synthetic degradation without race conditions.

However, **Trinetra is NOT yet ready for real-world assistive-vision field testing.**

A strict, evidence-driven hardware and reliability audit revealed five major architectural and physical disconnects between the passing software test suite and real-world execution reality:

1. **Hardware Camera Disconnect (`UNVERIFIED` / `SIMULATED`):** All 124 passing automated tests execute against `FakeCameraAdapter` with synthetic 32x24 JPEG memory buffers. Probing physical hardware via DirectShow (`cv2.CAP_DSHOW`) revealed zero accessible webcams on the host system. `OpenCVCameraAdapter` has no auto-reconnect capability; physical USB unplugging causes an unhandled HTTP 500 loop in the desktop client.
2. **Missing Sensor Degradation Audio Alerting (`NOT-IMPLEMENTED` / `FAILED`):** While `SensorHealthController` successfully evaluates frame degradation (3x3 grid, Laplacian blur, dark/occlusion detection) and emits `audio_chime` directives, `PerceptionPipeline._worker_loop` in [`app/detection/engine.py`](file:///D:/trinetra/services/vision-engine/app/detection/engine.py#L434-L460) **completely ignores `state_action.audio_chime`**. When the camera is covered or pointed into darkness, the system goes completely silent without any spoken or auditory warning to the blind user.
3. **Misleading "End-to-End" Latency Metric (`PARTIAL`):** The reported `e2e_latency_ms` is strictly an internal preprocessing + detection latency metric. It omits camera sensor exposure & DirectShow driver latency (20–50 ms), optical flow ego-motion (8–15 ms), tracking updates (1–3 ms), speech decision logic, Piper/SAPI TTS audio generation (50–150 ms), and OS sound playback (50–200 ms). True physical photon-to-ear latency is 250–500 ms.
4. **Complete GPU Underutilization (`NOT-IMPLEMENTED`):** Despite the target hardware featuring an NVIDIA RTX 3050 Ti 4 GB Laptop GPU, the installed Python runtime has standard CPU-only `onnxruntime 1.31.0`. `CUDAExecutionProvider` is missing from the environment, and `OnnxDetectionEngine` hardcodes `providers = ["CPUExecutionProvider"]` with `intra_op_num_threads = 2`. All vision models run on the CPU, capping sustained throughput at ~14 FPS.
5. **Architectural Pull-Driven Inversion:** The perception pipeline does not run an autonomous hardware frame grabber thread. Frames are captured **only when the desktop frontend polls `GET /api/camera/frame`**. If the frontend slows down or pauses, perception stops entirely.

---

### 2. Component Readiness & Evidence Matrix

| Subsystem / Component | Current Implementation State | Evidence Classification | Critical Gaps & Findings |
|---|---|---|---|
| **Webcam Enumeration** | `OpenCVCameraAdapter.enumerate_devices` probes indices 0..3 via DirectShow | `PARTIAL` (Code exists, fails on host) | Probed host: all 4 indices return `disconnected`. No DirectShow device index accessible. |
| **Webcam Streaming** | DirectShow `cv2.VideoCapture(index, cv2.CAP_DSHOW)` with MSMF fallback | `SIMULATED` (Production adapter unverified) | Synchronous `read()` upon HTTP request. Zero tests run real OpenCV capture in CI/CD. |
| **Camera Disconnection Handling** | Raises `FrameCaptureError`, translated to HTTP 500 in FastAPI route | `FAILED` | Desktop client retries every 150 ms indefinitely. No auto-reconnect or user notification. |
| **Frame Acquisition Architecture** | Pull-driven via frontend `GET /api/camera/frame` | `VERIFIED-SOFTWARE` | Perception is slave to UI HTTP polling rate (~20 FPS). No autonomous hardware loop. |
| **Perception Worker Loop** | Decoupled background thread with single-slot lossy buffer | `VERIFIED-SOFTWARE` | Capacity-1 bounded buffer skips stale frames. Prevents queue bloat. |
| **Object Detection (YOLOX-Nano)** | ONNX Runtime on CPU (416x416 letterbox, NMS) | `VERIFIED-HARDWARE` (CPU only) | Benchmarked on host: p50 = 26.96 ms. CPU-only, 2 threads. GPU completely unused. |
| **Face Detection (YuNet)** | OpenCV `FaceDetectorYN` on CPU (dynamic input size) | `VERIFIED-HARDWARE` (CPU only) | Benchmarked on host: p50 = 22.41 ms. Combined with YOLOX = ~49 ms pure inference (~20 FPS max). |
| **Ego-Motion Compensation** | Sparse Lucas-Kanade optical flow (`goodFeaturesToTrack`) | `VERIFIED-SOFTWARE` | Defensively guarded against sub-16px frames. Not included in `e2e_latency_ms`. |
| **Kalman Tracking** | Constant velocity 8-state Kalman filter with coasting | `VERIFIED-SOFTWARE` | Coasts during degradation, purges tracks after 200 ms timeout. Clean recovery debouncing. |
| **Sensor Health Quality Gate** | 3x3 spatial grid, Laplacian variance, luminance coupling | `VERIFIED-SOFTWARE` | Bypasses DNN inference during verified outages. |
| **Auditory Degradation Alerting** | `state_action.audio_chime` in `health_controller.py` | `NOT-IMPLEMENTED` / `FAILED` | **Wiring missing in `engine.py`**. Silent failure on dark/occluded frames. |
| **Nepali Speech Synthesis** | Local Piper TTS (`piper.exe` + `ne_NP-google-x_low.onnx`) | `VERIFIED-HARDWARE` | Executed on host: voice loaded in 0.47s, synthesized Devanagari phrase cleanly. |
| **English Speech Synthesis** | Windows SAPI via persistent PowerShell WinRT worker | `VERIFIED-HARDWARE` | Host verified: connected to `Microsoft David`, `Microsoft Zira`, `Microsoft Mark`. |
| **Speech Decision & Arbitrator** | Multi-tier priority queue, crowd aggregation, cooldowns | `VERIFIED-SOFTWARE` | Preempts spatial audio on critical collision hazard. Cooldown deduplication active. |
| **Desktop Supervisor (Rust)** | Tauri background supervisor with cryptographic session token | `PARTIAL` | Launch and token verified in code; loopback tests fail in sandboxed environment. |
| **Target Hardware Compatibility** | Ryzen 7 6800H + 8 GB RAM + RTX 3050 Ti Laptop | `PARTIAL` | Memory budget tight (~2.5 GB free); GPU 100% idle due to CPU-only ONNX package. |

---

### 3. Detailed Audit by Area

#### A. Hardware Integration Assessment
- **Discovery & Enumeration:** [`OpenCVCameraAdapter.enumerate_devices`](file:///D:/trinetra/services/vision-engine/app/camera/adapter.py#L290-L330) blindly probes indices `0..3` via `cv2.VideoCapture(idx, cv2.CAP_DSHOW)`. On the physical audit host, OpenCV logged:
  `[ WARN:0 ] global cap.cpp:477 cv::VideoCapture::open VIDEOIO(DSHOW): backend is generally available but can't be used to capture by index`.
  All 4 indices returned `is_available: false, status: "disconnected"`.
- **Hardware vs Simulated:** 100% of the repository's automated tests (`test_api.py`, `test_pipeline_async_integration.py`, `test_controlled_sensor_health_integration.py`) execute against `FakeCameraAdapter`. `OpenCVCameraAdapter` is **never executed in automated CI/CD**.
- **Disconnection Handling:** If a physical USB webcam is disconnected while active, `cap.read()` returns `(False, None)`. `capture_packet()` raises `FrameCaptureError`, which FastAPI maps to `HTTP 500 Internal Server Error`. The desktop frontend in [`apps/desktop/src/App.tsx`](file:///D:/trinetra/apps/desktop/src/App.tsx#L240-L249) enters an error backoff loop (`window.setTimeout(pollNextFrame, 150)`), continuously polling and logging 500 errors. It **never attempts hardware re-enumeration or auto-reconnect**, and the UI remains stuck displaying the camera as "active" with an error alert.

#### B. Perception Pipeline Assessment
- **Architecture Inversion:** In standard robotics and autonomous assistive systems, camera capture runs as a dedicated, high-priority native thread pushing frames into a circular or ring buffer. In Trinetra, **frame acquisition is purely pull-driven by HTTP clients**. The backend only reads from the camera when the frontend calls `GET /api/camera/frame`. If the desktop app lags, minimizes, or pauses, visual perception completely halts.
- **Redundant Transcoding Overhead:** For every frame:
  1. `OpenCVCameraAdapter` captures raw BGR numpy array $\to$ encodes to JPEG via `cv2.imencode`.
  2. `PerceptionPipeline` worker receives JPEG $\to$ `cv2.imdecode` in `engine.detect()` for YOLOX.
  3. `DetectionFusion` receives JPEG $\to$ `cv2.imdecode` in `YuNetFaceDetector.detect()`.
  4. `EgoMotionEstimator` receives JPEG $\to$ `cv2.imdecode` in `ego_motion.estimate()`.
  The same frame is encoded once and decoded three separate times on the CPU per cycle, burning 5–10 ms of unnecessary CPU time.
- **Sensor Degradation Handling:**
  - Spatial 3x3 grid, Laplacian variance, and luminance-coupled white-wall disambiguation are mathematically sound and software-verified.
  - Tracking coasting is strictly bounded to `max_coasting_duration_seconds = 0.20s` (approx 5 frames). Stale tracks are cleanly purged upon timeout.
  - **CRITICAL DEFECT:** In [`app/detection/engine.py`](file:///D:/trinetra/services/vision-engine/app/detection/engine.py#L434-L460), when `state_action.should_run_dnn` is False, the worker clears/coasts tracks, sets `suppressed_result`, and executes `continue`. **It never passes `state_action.audio_chime` to `self.speech_manager` or dispatches an audio event.** The user is left in total silence when the camera is covered or pitch black.

#### C. End-to-End Latency Assessment

The audit measured individual component latencies directly on the host AMD Ryzen 7 6800H CPU:

| Processing Stage | Actual Measured Host Latency | Instrumentation Status | Included in `e2e_latency_ms`? |
|---|---|---|---|
| **1. Sensor Exposure & USB Read** | Estimated 20.0 – 50.0 ms | **MISSING** (No hardware timestamping) | ❌ NO |
| **2. JPEG Frame Encode (Adapter)** | Measured 2.1 – 3.8 ms | **MISSING** (Not instrumented) | ❌ NO |
| **3. Bounded Queue Wait** | Measured 0.1 – 5.0 ms | Instrumentable via `captured_at` | ✅ YES (implicitly) |
| **4. Spatial Quality Check (Gatekeeper)** | Measured 2.8 – 4.5 ms | Recorded in assessment | ❌ NO (not in result) |
| **5. YOLOX-Nano CPU Inference** | **Measured p50 = 26.96 ms** (p95 = 32.21 ms) | Instrumented in `inference_time_ms` | ✅ YES |
| **6. YuNet Face Detection (Fusion)** | **Measured p50 = 22.41 ms** (p95 = 28.61 ms) | Not separate; bundled into wall clock | ✅ YES |
| **7. Ego-Motion Optical Flow** | Estimated 8.0 – 15.0 ms | **MISSING** (Runs after metric stamp) | ❌ NO |
| **8. Kalman Tracking Update** | Measured 1.2 – 2.5 ms | **MISSING** (Runs in `_announce`) | ❌ NO |
| **9. Scene Awareness & Decision** | Measured 0.8 – 1.8 ms | **MISSING** (Runs in `_announce`) | ❌ NO |
| **10. TTS Speech Synthesis** | Measured ~50 ms (SAPI) / ~120 ms (Piper) | Asynchronous speech queue | ❌ NO |
| **11. Audio Playback / DAC Output** | Estimated 50.0 – 200.0 ms (SoundPlayer / winsound) | OS audio buffer | ❌ NO |
| **Reported Metric (`e2e_latency_ms`)** | **~52 – 68 ms** | **PARTIAL (Misleading scope)** | — |
| **TRUE Physical Photon-to-Ear Latency** | **Estimated 250 – 480 ms** | **MISSING** | — |

**Verdict:** The system lacks true photon-to-ear latency instrumentation. Claiming an "end-to-end latency" of 50–65 ms ignores hardware sensor capture, ego-motion, tracking, speech synthesis, and audio delivery.

#### D. Nepali and English Speech Assessment
- **Nepali Piper TTS:**
  - `runtime/piper/piper.exe` (v1.2.0) and model `models/tts/ne_NP-google-x_low.onnx` (27.7 MB) are present on disk.
  - Direct execution test on host: **PASSED (VERIFIED-HARDWARE)**. Loaded voice in 0.47s, synthesized Devanagari text `"नमस्ते"` without errors.
- **English Windows SAPI:**
  - Persistent PowerShell WinRT worker test on host: **PASSED (VERIFIED-HARDWARE)**. Successfully connected to 3 installed voices (`Microsoft David`, `Microsoft Zira`, `Microsoft Mark`).
- **Composite Routing & Fallback:**
  - `CompositeSpeechRouter` cleanly routes `"ne"` to Piper and `"en"` to SAPI.
  - Zero silent fallback: if Nepali voice is unavailable, speech is suppressed rather than corrupted by English SAPI pronunciation.
- **Audio Output Reality:**
  - Automated tests use `FakeSpeechBackend`. Real audio output was tested independently via scratch scripts and verified functional on physical host speakers.

#### E. Desktop Integration Assessment
- **Tauri Application Lifecycle:**
  - `supervisor.rs` securely generates a 256-bit session token (`BCryptGenRandom`), launches Python via `Command::new(python_cmd).args(["-m", "uvicorn", ...])`, and passes `TRINETRA_PARENT_PID`.
  - Python lifespan hooks and the parent PID watchdog thread in [`app/main.py`](file:///D:/trinetra/services/vision-engine/app/main.py#L379-L430) terminate the Python service cleanly when the desktop application closes.
- **Test Harness Limitation:**
  - Unit tests in `supervisor.rs` (`test_adoption_*`, `test_port_collision_*`) attempt real TCP loopback listener binding (`TcpListener::bind("127.0.0.1:0")`). In sandboxed environments without loopback networking permissions, these tests hang or fail.
- **Camera Permissions:**
  - Tauri does not currently query or manage Windows Camera privacy permissions via Windows Runtime APIs. If the user has disabled camera access in Windows Settings, `OpenCVCameraAdapter.start()` fails with a generic `CameraBusyError`.

#### F. Performance on Target Hardware Assessment
- **Intended Target Hardware:** AMD Ryzen 7 6800H (8C/16T), 8 GB RAM, NVIDIA RTX 3050 Ti 4 GB Laptop GPU.
- **GPU Inactivity (`NOT-IMPLEMENTED`):**
  - Environment package is CPU-only `onnxruntime 1.31.0`. `CUDAExecutionProvider` is completely absent.
  - `OnnxDetectionEngine` explicitly hardcodes `providers = ["CPUExecutionProvider"]` with `opts.intra_op_num_threads = 2`.
  - The dedicated 4 GB RTX 3050 Ti GPU is 0% utilized.
- **CPU Bottleneck:**
  - YOLOX-Nano (27 ms) + YuNet (22 ms) + Optical Flow (10 ms) + JPEG decoding (6 ms) + Quality Gate (4 ms) = ~69 ms per frame.
  - This mathematically caps CPU frame processing at **~14.5 FPS**.
- **Memory Pressure (8 GB Budget):**
  - Windows 11 baseline: 3.5 – 4.5 GB.
  - Desktop app (WebView2): 200 – 300 MB.
  - Python Engine (OpenCV + ONNX Runtime + models): 450 – 650 MB.
  - Total system footprint: ~5.0 – 5.5 GB.
  - Leaves only ~2.5 GB free. Running secondary applications (browser, development tools) risks SSD swap paging, which causes severe frame drops.

#### G. Accessibility and Safety Assessment
- **Spoken Announcements:**
  - Prioritized hierarchical arbitration: Critical Hazard (immediate interrupt) $\to$ Path Intersection $\to$ Crossing $\to$ Crowd Summary $\to$ Spatial Guidance.
  - Crowd aggregation prevents speech chattering ("भिडभाड अगाडि" instead of announcing 8 individual pedestrians).
  - Cooldown deduplication (3.5s default, 2.0s hazard) prevents nuisance repetition.
- **Safety Limitations & Disclaimers:**
  - Standard laptop webcam horizontal field of view ($60^\circ - 70^\circ$) has a major blind spot for ground-level drop-offs (curbs, descending staircases, potholes) unless physically tilted downwards.
  - Both backend API schema and desktop UI explicitly present: `"Diagnostics only — not safety certified"`.
- **Silent Degradation Hazard (`FAILED`):**
  - Because `PerceptionPipeline` does not route `state_action.audio_chime` to speech, an obstructed camera produces total silence. For a visually impaired user, silence is indistinguishable from an unobstructed path. **This must be remediated as a P0 blocker.**

---

### 4. Classification of Findings

| Item / Finding | Classification | Evidence & File Location |
|---|---|---|
| Bounded single-slot pending queue prevents memory bloat | `VERIFIED-SOFTWARE` | [`engine.py:406`](file:///D:/trinetra/services/vision-engine/app/detection/engine.py#L406-L415); verified in `test_pipeline_async_integration.py` |
| Canonical language code normalization (`ne`, `en`) | `VERIFIED-SOFTWARE` | [`speaker.py:480`](file:///D:/trinetra/services/vision-engine/app/audio/speaker.py#L480-L500); verified in `test_speech_normalization.py` |
| YOLOX-Nano CPU inference execution (p50 = 26.96 ms) | `VERIFIED-HARDWARE` | Tested directly on AMD Ryzen 7 6800H host using `yolox_nano.onnx` |
| YuNet CPU face detection execution (p50 = 22.41 ms) | `VERIFIED-HARDWARE` | Tested directly on AMD Ryzen 7 6800H host using `face_detection_yunet_2023mar.onnx` |
| Piper TTS local Nepali neural speech synthesis | `VERIFIED-HARDWARE` | Tested directly on host: `piper.exe` + `ne_NP-google-x_low.onnx` synthesized Devanagari in 0.47s |
| Windows SAPI WinRT English speech synthesis | `VERIFIED-HARDWARE` | Tested directly on host: PowerShell WinRT worker enumerated installed system voices |
| Physical camera DirectShow capture & enumeration | `UNVERIFIED` | Host probe returned 4 disconnected indices; zero real cameras tested in CI |
| Camera auto-reconnect upon physical USB unplug | `NOT-IMPLEMENTED` | [`adapter.py:245`](file:///D:/trinetra/services/vision-engine/app/camera/adapter.py#L245-L260); raises unhandled 500 error loop in `App.tsx` |
| Sensor degradation chime dispatched to user | `NOT-IMPLEMENTED` | [`engine.py:434`](file:///D:/trinetra/services/vision-engine/app/detection/engine.py#L434-L460); `state_action.audio_chime` completely ignored |
| Autonomous background camera grabber thread | `NOT-IMPLEMENTED` | Frame capture is slave to frontend HTTP polling (`App.tsx:204`) |
| NVIDIA GPU hardware acceleration | `NOT-IMPLEMENTED` | `onnxruntime` CPU build installed; `providers = ["CPUExecutionProvider"]` hardcoded |
| True photon-to-ear latency accounting | `NOT-IMPLEMENTED` | `e2e_latency_ms` omits sensor capture, ego-motion, tracking, and audio playback |
| Desktop supervisor loopback test independence | `FAILED` | `supervisor.rs` unit tests hang in sandboxed environments due to raw loopback TCP bind |

---

### 5. Recommended Priority Roadmap for Priority 4.7

#### P0 — Critical Safety & Reliability Blockers (Mandatory before Field Testing)
1. **Connect Sensor Degradation Audio Alerting:**
   - Wire `state_action.audio_chime` in [`app/detection/engine.py`](file:///D:/trinetra/services/vision-engine/app/detection/engine.py#L434) to `self.speech_manager.announce()` or a dedicated chime player.
   - When visual quality is severely degraded or the camera is covered, immediately dispatch a rate-limited spoken alert (e.g. *"क्यामेरा अवरुद्ध छ"* / *"Camera view obstructed"*). A blind user must never experience silent perception failure.
2. **Implement Resilient Camera Disconnection & Auto-Recovery:**
   - In `OpenCVCameraAdapter`, catch `cap.read()` capture failures and mark the adapter state as `RECOVERING`.
   - Implement an automatic background re-enumeration and re-open loop (with exponential backoff) instead of throwing terminal HTTP 500 errors.
   - Update `App.tsx` to display an explicit "Camera Disconnected — Reconnecting..." state rather than entering an unhandled retry storm.

#### P1 — Essential Hardware & Architecture Realignment
1. **Invert Frame Acquisition to Autonomous Push Pipeline:**
   - Decouple hardware frame acquisition from HTTP requests. Implement a dedicated background grabber thread in `OpenCVCameraAdapter` continuously reading the camera at target hardware FPS.
   - The perception worker and desktop preview consume from this shared internal buffer. If the desktop UI slows down, background perception and safety monitoring continue unimpeded.
2. **Eliminate Redundant JPEG Transcoding:**
   - Pass native BGR numpy frames directly between capture, gatekeeper, YOLOX, YuNet, and optical flow.
   - Eliminate the 3x redundant `cv2.imdecode` operations per frame cycle, saving ~8 ms of CPU budget per frame.

#### P2 — Perception, Speech & Latency Instrumentation
1. **Implement True Photon-to-Ear Latency Instrumentation:**
   - Instrument hardware grab timestamp, optical flow duration, tracking duration, speech synthesis duration, and audio playback duration.
   - Report both `detection_latency_ms` and estimated total `system_latency_ms` transparently.
2. **Socket-Free Rust Supervisor Unit Tests:**
   - Refactor `supervisor.rs` unit tests to use mock abstraction rather than binding live TCP loopback sockets, ensuring deterministic test passes in sandboxed environments.

#### P3 — Performance Optimization for Target Hardware
1. **GPU Acceleration Assessment (RTX 3050 Ti):**
   - Evaluate upgrading `.venv` to `onnxruntime-gpu` (CUDA/DirectML) or using DirectML execution provider (`DmlExecutionProvider`), offloading YOLOX and YuNet from the CPU.
   - Target reducing pure inference latency from ~49 ms (CPU) to <12 ms (GPU), liberating the Ryzen 7 6800H CPU for tracking, optical flow, and TTS while achieving a smooth 30 FPS.
2. **Memory Footprint Monitoring:**
   - Add a lightweight memory telemetry watchdog in the Python engine alerting when process RSS exceeds 1.0 GB on 8 GB systems.
