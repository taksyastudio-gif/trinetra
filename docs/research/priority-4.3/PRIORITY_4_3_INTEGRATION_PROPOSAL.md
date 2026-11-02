# TRINETRA — Priority 4.3: Integration Proposal
## Sensor-Health Gatekeeper Non-Blocking Integration Specification

**Document:** `docs/research/priority-4.3/PRIORITY_4_3_INTEGRATION_PROPOSAL.md`  
**Target Module for Future Integration:** `services/vision-engine/app/detection/engine.py` (`PerceptionPipeline`)  
**Status:** PROPOSED & VALIDATED (AWAITING USER APPROVAL PRIOR TO CODE MODIFICATION)  
**Date:** October 31, 2026  

---

## 1. Context & Architectural Constraint

In accordance with strict safety and preservation protocols, **no modifications have been made to `engine.py`, `adapter.py`, or any live production modules** during this phase. 

The `SensorHealthGatekeeper` is fully implemented and tested as an isolated component in `app/camera/sensor_health.py`. This proposal details the precise, non-blocking interface and operational contract for integrating the Gatekeeper into `PerceptionPipeline` in Sprint 5 upon explicit user authorization.

---

## 2. Proposed Integration Architecture

```
                       Camera Ingestion Loop
                                │
                                ▼
                       Raw Image Frame (BGR)
                                │
                                ▼
                 ┌─────────────────────────────┐
                 │   SensorHealthGatekeeper    │  <-- Cost: ~0.60 ms
                 │      assess_frame(...)      │
                 └──────────────┬──────────────┘
                                │
                                ▼
                  SensorHealthAssessment Packet
                                │
     ┌──────────────────────────┼──────────────────────────┐
     ▼                          ▼                          ▼
 [NORMAL]                  [DEGRADED]             [SEVERELY_DEGRADED]
Continue Nominal       Continue with Caution      Suppress Downstream DNN
Perception Loop        - Retain Kalman tracks     - Suppress YOLOX & YuNet
- YOLOX-Nano (~38ms)   - Coast covariance         - Suppress Optical Flow
- YuNet Faces (~12ms)  - Log telemetry metric     - Coast Kalman tracks (max 5 frames)
- Kalman Tracking      - Permit hazard dispatch   - Trigger Audio Chime (cooldown: 5.0s)
                                                  - Save battery & thermal headroom
```

---

## 3. Detailed Operational Contract for `PerceptionPipeline`

### 3.1. Hook Location: `PerceptionPipeline.process_frame()`

The gatekeeper check executes at the absolute beginning of `process_frame(frame, frame_id, timestamp)`:

```python
# PROPOSED INTEGRATION SNIPPET (For Future Implementation)
def process_frame(self, frame: np.ndarray, frame_id: int, timestamp: float) -> DetectionResult:
    # Step 1: Pre-flight Sensor-Health & Quality Check (<0.6 ms)
    health: SensorHealthAssessment = self.sensor_gatekeeper.assess_frame(
        frame=frame,
        frame_id=frame_id,
        timestamp=timestamp
    )

    # Step 2: Route by Health Recommendation
    if health.action == ActionRecommendation.SUPPRESS_AND_CHIME:
        return self._handle_severely_degraded_frame(health, frame_id, timestamp)

    # Step 3: Handle Moderate Degradation (Caution)
    if health.action == ActionRecommendation.PROCESS_WITH_CAUTION:
        self._record_telemetry_warning(health)

    # Step 4: Proceed to Heavy Perception (YOLOX, YuNet, Kalman, Scene Analyzer)
    ...
```

### 3.2. Action Policies & State Machine

#### Policy A: `HealthStatus.NORMAL` (`ActionRecommendation.PROCESS`)
- **Execution:** Normal perception execution.
- **Detections:** YOLOX-Nano and YuNet run normally.
- **Tracking:** Kalman filter receives standard measurement updates.
- **Audio:** No health announcements or chimes emitted. Recovery chime triggered if transitioning from `SEVERELY_DEGRADED`.

#### Policy B: `HealthStatus.DEGRADED` (`ActionRecommendation.PROCESS_WITH_CAUTION`)
- **Execution:** Downstream models run, but internal confidence weighting is softened.
- **Tracking:** Ego-motion optical flow may be noisy; Kalman measurement noise covariance $R$ is scaled by $1.5\times$ to trust temporal prediction over noisy instantaneous detections.
- **Speech:** Non-urgent degradation (e.g. twilight lighting, walking motion blur) does **not** interrupt the user. Speech engine operates normally.

#### Policy C: `HealthStatus.SEVERELY_DEGRADED` (`ActionRecommendation.SUPPRESS_AND_CHIME`)
- **Execution:** **Downstream DNN inference (YOLOX-Nano, YuNet) is completely bypassed.**
- **CPU / Thermal Benefit:** Saves $\approx 50\text{ ms}$ of compute per frame, preventing thermal throttling on battery-operated wearables.
- **Tracking Integrity:** Existing tracks are **not deleted immediately**. The Kalman filter enters coasting mode (prediction without measurement update) for up to $5$ consecutive frames ($\approx 165\text{ ms}$). If severe degradation persists beyond $5$ frames, tracks are gracefully terminated to prevent ghost obstacles.
- **Audio Notification:** Dispatches non-verbal audio chime (see Section 4).

---

## 4. Audio Notification & Chime Protocol

### 4.1. Voice Spam Prohibition
A user navigating an unfamiliar outdoor environment must **never** be bombarded with repetitive synthetic speech messages like *"The camera is covered"*, *"Camera is dark"*, *"Frame is blurry"* on every single video frame ($30$ times per second). This causes cognitive overload, masks real environmental audio cues (traffic, footsteps, sirens), and poses severe safety risks.

### 4.2. Non-Verbal Audio Cues

Trinetra utilizes short ($80\text{--}150\text{ ms}$), distinct, non-verbal auditory chimes generated locally:

| Diagnostic State | Auditory Cue | Acoustic Signature | Cooldown Period |
| :--- | :--- | :--- | :--- |
| **Occluded Lens** | `CHIME_OCCLUDED` | Low double-beep ($220\text{ Hz} \to 180\text{ Hz}$, $120\text{ ms}$) | **$5.0\text{ seconds}$** |
| **Pitch Black Darkness** | `CHIME_DARKNESS` | Descending two-tone chime ($300\text{ Hz} \to 200\text{ Hz}$, $150\text{ ms}$) | **$5.0\text{ seconds}$** |
| **Severe Defocus Blur** | `CHIME_DEFOCUS` | Soft muffled double-click ($100\text{ ms}$) | **$5.0\text{ seconds}$** |
| **Recovery to Normal** | `CHIME_RECOVERY` | Rising bright chirp ($440\text{ Hz} \to 880\text{ Hz}$, $80\text{ ms}$) | Once on state exit |

### 4.3. Cooldown & Hysteresis State Machine

To prevent rapid oscillation (chattering) between `NORMAL` and `SEVERELY_DEGRADED` (e.g., when walking beneath alternating streetlamps or through dappled foliage):
1. **Debounce / Temporal Hysteresis:** A transition to `SEVERELY_DEGRADED` requires **$2$ consecutive degraded frames** before suppressing inference or chiming.
2. **Recovery Hysteresis:** A transition back to `NORMAL` requires **$3$ consecutive clean frames** before emitting the recovery chime.
3. **Audio Cooldown:** A minimum of $5.0\text{ seconds}$ must elapse before repeating the same degradation chime.

---

## 5. Telemetry & Frontend API Visibility

The assessment data will be exposed to the desktop UI and mobile client via the existing `DetectionResult` and `/api/camera/status` endpoints:

```json
{
  "sensor_health": {
    "status": "normal",
    "blur_score": 642.44,
    "mean_luminance": 99.23,
    "contrast": 68.73,
    "is_blurry": false,
    "is_dark": false,
    "is_bright": false,
    "is_occluded": false,
    "reasons": [],
    "action": "process",
    "latency_ms": 0.596
  }
}
```

The desktop UI (`StatusIndicator.tsx`, `Header.tsx`) can render a subtle icon (e.g., small amber indicator for `DEGRADED`, red for `SEVERELY_DEGRADED`) without disturbing the audio channel.

---

## 6. What NOT to Do (Anti-Patterns to Avoid)

1. ❌ **Do NOT block the frame capture loop:** Gatekeeper assessment must be synchronous in `process_frame()` but strictly bounded to $< 1.0\text{ ms}$. Never perform disk I/O, network requests, or heavy logging inside the evaluation path.
2. ❌ **Do NOT raise unhandled exceptions:** If a malformed or corrupted frame arrives, the gatekeeper must return a fallback assessment (`SEVERELY_DEGRADED`) and never crash the perception thread.
3. ❌ **Do NOT immediately clear Kalman tracks:** A single dark or blurred frame during a rapid step must allow Kalman coasting rather than resetting tracked pedestrian IDs.
4. ❌ **Do NOT queue voice speech for health warnings:** Use non-verbal synthesized tone bursts or pre-rendered WAV chimes through `SpeechPriority.INFORMATIONAL` with a strict $5.0\text{s}$ cooldown.
