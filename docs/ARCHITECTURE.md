# Trinetra System Architecture (Sprint 4: End-to-End Reliability, Verification & Security)

## 1. High-Level Architecture Overview

Trinetra is an assistive vision and spatial awareness platform designed for blind and visually impaired individuals. It integrates an accessible desktop application (React 18 + TypeScript + Tauri 2) with a decoupled, high-performance local vision service (FastAPI + OpenCV + ONNX Runtime CPU) communicating strictly over loopback HTTP (`127.0.0.1:8000`).

```
+-------------------------------------------------------------------------------------------------+
|                                         Desktop Host                                            |
|                                                                                                 |
|   +---------------------------------------+       +-----------------------------------------+   |
|   |         React 18 + TypeScript         |       |            Tauri 2 Rust Core            |   |
|   |   - High-Contrast Accessible Controls |<----->|   - Native Windows Webview Host         |   |
|   |   - Camera Device Selector Dropdown   |       |   - Hardware Sandbox Permissions        |   |
|   |   - Real-Time Detections Panel        |       |   - Native Windows Supervisor & BCrypt  |   |
|   |   - Speech Mute & Silence Controls    |       |   - Verified HTTP Health Gatekeeper     |   |
|   |   - ARIA Live Regions (WCAG AAA)      |       |   - Loopback Token Authentication       |   |
|   +-------------------+-------------------+       +-----------------------------------------+   |
|                       |                                                                         |
|                       | HTTP REST & Monotonic Frame Polling                                     |
|                       | (127.0.0.1:8000 with X-Frame-Id, X-Captured-At, X-Session-Id)           |
|                       v                                                                         |
|   +-----------------------------------------------------------------------------------------+   |
|   |                               Local Vision Engine (FastAPI)                             |   |
|   |                                                                                         |   |
|   |   +---------------------------------------------------------------------------------+   |   |
|   |   |                     HTTP REST Layer & Session Authorization                     |   |   |
|   |   |   - Camera: /api/health, /status, /devices, /start, /stop, /frame               |   |   |
|   |   |   - Speech: /api/speech/announce, /stop, /mute, /status                         |   |   |
|   |   |   - Detection: /api/detection/status, /start, /stop, /latest                    |   |   |
|   |   |   - Token Check: TRINETRA_SESSION_TOKEN Header Verification                     |   |   |
|   |   |   - Concurrency Guards: threading.RLock() serialization                         |   |   |
|   |   +-----------------------+-----------------------------+---------------------------+   |   |
|   |                           |                             |                           |   |   |
|   |                           v                             v                           v   |   |
|   |   +-------------------------------+   +---------------------+   +-------------------+   |   |
|   |   |    CameraManager & Adapter    |   |  PerceptionPipeline |   |   SpeechManager   |   |   |
|   |   | - Capacity-1 Bounded Buffer   |   | - OnnxDetection     |   | - Priority Queue  |   |   |
|   |   | - Device Discovery (0..3)     |   | - YOLOX-Nano (CPU)  |   | - Spam Cooldown   |   |   |
|   |   | - Monotonic Frame Sequence    |   | - Strides [8,16,32] |   | - Windows SAPI5   |   |   |
|   |   | - Session Generation UUID     |   | - Sector Classifier |   | - Preemption Stop |   |   |
|   |   | - OpenCV DirectShow / Fake    |   | - Left/Center/Right |   | - Thread-Safe RLock|  |   |
|   |   +-------------------------------+   +---------------------+   +-------------------+   |   |
|   +-----------------------------------------------------------------------------------------+   |
+-------------------------------------------------------------------------------------------------+
```

---

## 2. Core Subsystems

### A. Camera Device Discovery & Lifecycle Management
- **Device Enumeration (`/api/camera/devices`):** Discovers connected video capture devices on Windows by safely probing indices with `cv2.CAP_DSHOW` and verifying `cap.isOpened()`. Unused indices are released immediately.
- **Dynamic Device Switching:** Calling `POST /api/camera/start` with a target `camera_index` safely shuts down and releases the previously active device handle before initializing the new camera.
- **Concurrency Protection:** `CameraManager` utilizes `threading.RLock()` to ensure that multi-threaded start and stop requests cannot corrupt camera device handles or session UUIDs.

### B. Frame Delivery & Bounded Latency (`FramePacket`)
- **Capacity-1 Buffer:** Frame acquisition overwrites older unconsumed frames, guaranteeing that assistive feedback reflects **immediate real-time reality** rather than stale, delayed video data.
- **Telemetry Propagation:** Every frame response contains `X-Frame-Id` (monotonic 64-bit integer), `X-Captured-At` (Unix timestamp), `X-Frames-Dropped` (skipped frames count), and `X-Session-Id` (unique session UUID).
- **Webview Memory Hygiene:** The React desktop client defers `URL.revokeObjectURL(prevUrl)` by 100ms via `window.setTimeout`. This allows the webview renderer to paint the new frame before the previous blob URL is deallocated, preventing rendering flickers and memory leaks.

### C. Non-Blocking Audio & Prioritized Speech System (`SpeechManager`)
- **Decoupled Daemon Execution:** Speech synthesis executes on a dedicated background thread, ensuring speech operations never block camera capture, frame encoding, or UI rendering.
- **Priority Queue (`queue.PriorityQueue`):**
  1. `CRITICAL_HAZARD` (Priority 1): Immediate preemption; drains lower-priority items and halts current speech to announce impending collisions or drop-offs.
  2. `SPATIAL_NAVIGATION` (Priority 2): Standard path announcements (e.g. "Chair, center").
  3. `INFORMATIONAL` (Priority 3): Routine status updates (e.g. "Camera started").
- **Cooldown Deduplication:** Suppresses duplicate announcements of the same object class within a configurable cooldown window (default: 3.0s).
- **Zero-Cloud Local Synthesis:** Utilizes native Windows SAPI speech via `System.Speech` spawned as a controllable sub-process, enabling instant termination (`stop()`) without third-party cloud APIs.

### D. Decoupled Asynchronous Perception Worker (`PerceptionPipeline`)
- **Independent Sampling:** Camera frame delivery (`get_camera_frame`) is fully decoupled from AI inference. Frames are submitted to an internal bounded capacity-1 slot guarded by `threading.Condition` (`submit_frame`).
- **No Stale Accumulation:** If a model takes 150 ms to run, HTTP frame streaming continues at full camera speed (30+ FPS) without waiting for inference. Frames captured while inference is running overwrite stale unconsumed packets without queue buildup.
- **Monotonic Frame Tracking:** The background worker skips duplicate or older frame IDs (`packet.frame_id > last_processed_frame_id`), ensuring inference is only performed once per frame.

### E. Production ONNX Inference Engine (`OnnxDetectionEngine`)
- **Verified Primary Model:** Runs Megvii's official **YOLOX-Nano** (`yolox_nano.onnx`, 3.66 MB) under **Apache License 2.0**. Also provides shape-adaptive decoding for YOLOv8 (`[1, 84, 8400]`).
- **Cryptographic Model Verification:** Validates weights against expected SHA-256 digests (`c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`) before model loading to prevent corrupted or tampered models from executing.
- **Precomputed Grid Strides:** YOLOX feature strides $[8, 16, 32]$ and grid coordinate anchors for $416 \times 416$ inputs are precomputed at initialization, eliminating per-frame grid allocation overhead.
- **Safety Bounding Box Validation:** Clamps coordinates to $[0.0, 1.0]$, rejects non-finite (NaN/Inf) floats, and eliminates degenerate boxes ($x_{\max} \le x_{\min}$ or $y_{\max} \le y_{\min}$).
- **Spatial Sector Partitioning:** Projects 2D bounding boxes into three directional sectors:
  - **Left Sector:** Normalized $x_{\text{center}} \in [0.0, 0.33)$
  - **Center Sector:** Normalized $x_{\text{center}} \in [0.33, 0.66]$
  - **Right Sector:** Normalized $x_{\text{center}} \in (0.66, 1.0]$
- **Measured CPU Latency (Windows 11 x64):**
  - Model Load Time: **160.55 ms**
  - ORT Inference Latency: **23.53 ms** (median: 23.28 ms, p95: 29.08 ms)
  - Preprocessing (Decode + Resize + Pad): **8.96 ms**
  - Postprocessing (Decode + NMS + Sectors): **3.05 ms**
  - Total End-to-End Latency: **35.56 ms** (~28.1 detections/second)
- **Zero Silent Fallback:** If a configured model fails to load, is corrupted, or fails checksums, the engine explicitly reports failure and never silently substitutes mock detections.

---

## 3. Tauri Service Supervisor & Security Architecture (`ServiceSupervisor`)

In production desktop deployments, the Rust Tauri core acts as the authoritative process supervisor:

```
+-------------------------------------------------------------------------------+
|                            Handshake Flow Diagram                             |
|                                                                               |
|  [Tauri 2 Rust Host]                                  [FastAPI Vision Engine] |
|           |                                                      |            |
|           | 1. Generate 32-byte CSPRNG token via                 |            |
|           |    native Windows BCryptGenRandom                    |            |
|           |                                                      |            |
|           | 2. Spawn python process with TRINETRA_SESSION_TOKEN  |            |
|           |----------------------------------------------------->|            |
|           |                                                      |            |
|           | 3. Loopback TCP readiness polling (127.0.0.1:8000)   |            |
|           |                                                      |            |
|           | 4. Inject token into frontend via IPC command        |            |
|           v    ("get_session_token") strictly in-memory          |            |
|  [React Frontend Client]                                         |            |
|           |                                                      |            |
|           | 5. All HTTP requests include header:                 |            |
|           |    "X-Trinetra-Session-Token": <token>               |            |
|           |----------------------------------------------------->|            |
|           |                                                      | 6. Validate|
|           |<-----------------------------------------------------|    token   |
|           |    HTTP 200 OK (or 401 if invalid/missing)           |            |
+-------------------------------------------------------------------------------+
```

### Security Guardrails:
1. **Windows BCryptGenRandom CSPRNG:** Generates a 256-bit cryptographic hex token using `BCryptGenRandom` with `BCRYPT_USE_SYSTEM_PREFERRED_RNG`.
2. **Private In-Memory Storage & 401 Eviction:** The frontend retrieves the token via Tauri IPC and retains it strictly in private closure memory in `cameraApi.ts`. The token is never stored in `localStorage`, `sessionStorage`, cookies, URLs, or console logs. If an HTTP 401 Unauthorized is received (e.g. following a service supervisor restart), the cached token is automatically evicted so subsequent requests re-acquire the fresh token from Tauri.
3. **Loopback Confinement:** FastAPI binds strictly to `127.0.0.1`. Remote network access is rejected.
4. **Explicit Development Mode:** When `TRINETRA_SESSION_TOKEN` is unset or whitespace, authentication is explicitly disabled for local development. When configured, all camera, speech, and detection endpoints enforce strict 401 rejection.
5. **Deterministic Lifecycle Cleanup:** When the Tauri application exits or is closed, the supervisor explicitly terminates the child Python process via `SIGTERM` / `kill()` to eliminate orphaned background processes.
6. **Ancestor Directory & Venv Discovery:** The supervisor walks directory ancestors to locate `services/vision-engine` from any execution path (current dir, cargo workspace, or packaged bundle) and auto-selects `.venv/Scripts/python.exe` when available.
7. **Background Auto-Startup Setup Hook:** The Tauri application builder executes a background thread in its `.setup()` hook that starts the supervisor and verifies HTTP health without blocking webview window creation.
8. **Dual Latency Telemetry:** The engine explicitly decouples and reports both raw ONNX model inference latency (`inference_time_ms`, ~23ms) and total capture-to-detection end-to-end latency (`e2e_latency_ms`, ~35ms) across the API and frontend UI.

---

## 4. Event-Aware Perception & Decision Layer

Rather than narrating every detected bounding box independently, Trinetra interprets observations temporally and spatial-structurally:

```
+--------------------+      +--------------------+      +-------------------------+      +-------------------+
|  Raw 2D Detections | ---> |  Temporal Tracker  | ---> |  Scene & Space Analyzer | ---> |  Decision Engine  |
| (YOLOX-Nano ONNX)  |      | (IoU Association)  |      | (Crowd & Sector Bounds) |      | (Priority Queue)  |
+--------------------+      +--------------------+      +-------------------------+      +-------------------+
                                                                                                   |
                                                                                                   v
                                                                                         +-------------------+
                                                                                         |   SpeechManager   |
                                                                                         | (Piper NE/SAPI EN)|
                                                                                         +-------------------+
```

1. **Temporal Object Tracking (`TemporalTracker`):**
   - Implements zero-dependency IoU association across consecutive frames.
   - Assigns monotonic track IDs to confirmed objects, suppressing repetitive chatter for stationary objects.
   - Estimates movement trajectory (`APPROACHING`, `RECEDING`, `MOVING_LEFT`, `MOVING_RIGHT`, `STATIONARY`) only when sufficient temporal observations exist ($\ge 3$ frames).
   - Handles track aging, missing frame tolerance (`miss_streak`), and track eviction.

2. **Scene & Walkable Space Understanding (`SceneAnalyzer`):**
   - **Crowd Aggregation:** Detects crowd scenes ($\ge 3$ persons) and replaces individual person alerts with concise crowd summaries.
   - **Collision Threat Assessment:** Differentiates approaching dynamic objects (e.g., vehicles) from stationary obstacles.
   - **Honest Walkable Space Estimation:** Evaluates left, center, and right sector clearance. Only issues directional recommendations when evidence clearly supports them. When all sectors are obstructed, returns `recommended_direction = None` with high obstruction confidence—never guessing safe paths.

3. **Speech Decision Engine (`SceneDecisionEngine`):**
   - Sits between perception analysis and `SpeechManager`.
   - Dispatches prioritized announcements in strictly structured hierarchy:
     1. `CRITICAL_HAZARD`: Impending collision or rapidly approaching vehicle (preempts all audio in $<120$ ms).
     2. `CROWD_SUMMARY`: Natural crowd description replacing spammy individual counts.
     3. `APPROACHING_OBSTACLE`: Approaching hazards.
     4. `STATIONARY_OBSTACLE`: Top priority identified obstacle with track-ID deduplication.
     5. `PATH_ADVISORY`: Clearance guidance when center is obstructed.
   - Bilingual support: Fluent Nepali (`ne_NP`) via local Piper neural TTS and English via Windows SAPI.

---

## 5. Accessible Incident Documentation (`IncidentRecorder`)

Provides on-demand, tamper-evident visual logging (`POST /api/incident/capture`):
1. **Cryptographic SHA-256 Digest:** Computes independent hashes for raw JPEG image bytes and canonical metadata, followed by a combined integrity digest.
2. **Local Bounded Storage:** Retains a bounded ring buffer of incident files (`inc_*.jpg` and `inc_*.json`) in `services/vision-engine/incidents/`, automatically pruning oldest records beyond the limit (default: 50).
3. **Audible Confirmation:** Dispatches immediate spoken confirmation in the active language ("घटना अभिलेख गरियो।" in Nepali / "Incident snapshot recorded" in English).
4. **Safety Boundaries:** Standard generic object classification only; no facial recognition, biometric identity extraction, or criminal profiling.

---

## 6. Offline Location Capability Layer (`LocationProvider`)

Hardware-independent location abstraction designed for privacy and local-first operation:
1. **Privacy-Safe Defaults:** Disabled by default (`LocationStatus.DISABLED`) out-of-the-box.
2. **Windows Location Integration:** Safely queries local Windows Geolocation (`System.Device.Location`) when enabled. Honestly reports `UNAVAILABLE` if hardware or permissions are absent.
3. **Manual Offline Landmark Support:** Allows configuring fixed offline reference coordinates (e.g. home base or Kathmandu landmark) without requiring active GPS hardware.
4. **Anti-Hallucination Guarantee:** Never fabricates, guesses, or hallucinates coordinates when location services are unavailable.

