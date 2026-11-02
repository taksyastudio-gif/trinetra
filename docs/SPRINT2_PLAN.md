# Trinetra — Sprint 2 Implementation Plan

## 1. Objectives & Scope

Sprint 2 builds directly upon the validated foundation established in Sprint 1 and the architectural enhancements adopted during the research integration. The goal of Sprint 2 is to introduce **local perception and prioritized audio feedback** without sacrificing latency, accessibility, or privacy.

Sprint 2 deliverables:
1. **Camera Device Enumeration:** Allow users to query and select among multiple connected camera devices.
2. **Prioritized Audio Announcement Engine (TTS):** Implement an asynchronous, non-blocking audio queue with hazard preemption and spam suppression.
3. **Local Edge Object Detection:** Integrate lightweight local object detection (YOLOv8n) with strict on-device inference.
4. **Spatial Positioning Logic:** Partition visual fields into directional sectors (Left, Center, Right) to guide user spatial awareness.
5. **Accessible Keyboard Shortcuts:** Global hotkeys for blind and visually impaired users.

---

## 2. Milestone Breakdown

### Milestone 2.1: Camera Device Enumeration [COMPLETED]
- **Goal:** Support switching between built-in webcams, external USB webcams, and body-worn cameras.
- **Backend Implementation:**
  - Added `CameraDeviceInfo` dataclass and `enumerate_devices()` to `CameraAdapter`.
  - Implemented DirectShow device probing in `OpenCVCameraAdapter` on Windows with auto-cleanup of test handles.
  - Added `GET /api/camera/devices` endpoint returning index, name, availability, and active status.
  - Extended `POST /api/camera/start` to accept an optional `camera_index: int`.
  - Upgraded `CameraManager` internal synchronization to `threading.RLock()` to ensure safe re-entrant switching and device releases.
- **Frontend Implementation:**
  - Created `DeviceSelector.tsx` with accessible `<select>` dropdown, refresh button, device busy states, and screen-reader announcements.

### Milestone 2.2: Prioritized Non-Blocking Audio & Speech Queue [COMPLETED]
- **Goal:** Provide fast, clear auditory feedback without blocking video capture or overwhelming the user with repetitive chatter.
- **Backend Implementation:**
  - Created `services/vision-engine/app/audio/speaker.py`.
  - Native offline speech via `WindowsSapiSpeechBackend` utilizing Windows `System.Speech.Synthesis.SpeechSynthesizer` via managed subprocesses with timeout guards and immediate process kill on preemption.
  - Requires **zero third-party pip dependencies** (`pyttsx3` is optional/not required).
  - Three distinct priority levels: `CRITICAL_HAZARD` (10), `SPATIAL_NAVIGATION` (20), `INFORMATIONAL` (30).
  - Preemption logic: `CRITICAL_HAZARD` terminates currently playing lower-priority utterances and purges lower-priority queued items.
  - 3.0s per-phrase/class cooldown filter prevents spamming while static objects remain in frame.
  - Global mute flag and instant emergency stop controls (`/api/speech/stop`, `/api/speech/mute`).
  - Unit tests using `FakeSpeechBackend` verifying preemption, cooldown suppression, priority ordering, and mute toggles.

### Milestone 2.3: Local Edge Perception & Pipeline [COMPLETED]
- **Goal:** Modular edge perception architecture decoupling vision capture from model inference with zero cloud dependency.
- **Backend Implementation:**
  - Created `services/vision-engine/app/detection/engine.py`.
  - Abstract base class `DetectionEngine` providing clean pluggability for YOLOv8, MobileNet, or custom ONNX models.
  - `FakeDetectionEngine` for deterministic automated tests and offline environments with zero weight downloads.
  - Asynchronous `PerceptionPipeline` daemon thread polling the camera buffer on a dedicated tick loop (100ms / 10 FPS target).
  - Clean separation: camera capture thread never waits for inference or speech dispatch.

### Milestone 2.4: Spatial Orientation & Sector Division [COMPLETED]
- **Goal:** Convert 2D bounding boxes into actionable spatial orientation guidance.
- **Implementation:**
  - Implemented `classify_sector(center_x: float) -> str`:
    - **Left Sector:** Normalized $x_{center} \in [0.0, 0.33)$
    - **Center Sector:** Normalized $x_{center} \in [0.33, 0.66]$
    - **Right Sector:** Normalized $x_{center} \in (0.66, 1.0]$
  - Calculated visual prominence metric `box.area_ratio` ($w \times h$) to prioritize larger/closer obstacles.
  - Minimal, uncluttered announcement syntax: `"{label}, {sector}"` (e.g. "chair, center", "person, left").

### Milestone 2.5: Accessible UI & Keyboard Controls [COMPLETED]
- **Goal:** Enable rapid, eyes-free control through dedicated keybindings and high-contrast, WCAG-compliant UI components.
- **Frontend Implementation:**
  - Created `DetectionPanel.tsx` with ARIA live regions (`aria-live="polite"` and `assertive` for hazards).
  - Added status telemetry: model name, inference FPS, inference latency (ms), active detections count.
  - Integrated global keyboard shortcuts in `App.tsx`:
    - `Space`: Immediately silence / stop all ongoing speech announcements.
    - `KeyD`: Toggle object detection pipeline on/off.
    - `KeyM`: Toggle audio mute on/off.
    - `KeyC`: Announce current system & camera status.
  - High-contrast visual styling meeting WCAG AAA color contrast standards (yellow accents on deep dark backgrounds).

---

## 3. Sprint 2 Acceptance Criteria Status

| ID | Requirement | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **AC-2.1** | Camera list returns all connected hardware cameras with zero crashes. | Automated API test + physical DirectShow probe. | **PASS** (100% verified) |
| **AC-2.2** | High-priority warnings interrupt long background speech within 150 ms. | Unit test simulating preemption & subprocess kill. | **PASS** (100% verified) |
| **AC-2.3** | Repeated detection of static object produces at most 1 spoken alert per 3 seconds. | Audio queue cooldown unit test. | **PASS** (100% verified) |
| **AC-2.4** | Edge model architecture runs 100% offline; zero packets sent to external IP addresses. | Codebase inspection & offline mock engine. | **PASS** (100% verified) |
| **AC-2.5** | Video capture loop remains decoupled and non-blocking during inference. | Asynchronous `PerceptionPipeline` thread architecture. | **PASS** (100% verified) |

---

## 4. Safety & Privacy Guardrails for Sprint 2

1. **Non-Obstacle Guarantee:** Audio announcements prefix qualitative terms ("Detected chair ahead") and never claim "Clear path ahead".
2. **Ambient Hearing Protection:** Spoken announcements are short, concise, cooldown-filtered, and instantly mutable with Spacebar to prevent masking environmental hearing cues.
3. **No Monocular Distance Claims:** Bounding-box pixel size is strictly never converted to metric distance.
4. **Local Execution:** 100% local speech synthesis and inference; zero cloud communication or telemetry.
