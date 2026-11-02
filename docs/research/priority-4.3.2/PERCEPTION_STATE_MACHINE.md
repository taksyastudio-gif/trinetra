# TRINETRA — Priority 4.3.2: Formal Perception State Machine
## State Definitions, Transition Matrix & Downstream Behavioral Contract

**Document:** `docs/research/priority-4.3.2/PERCEPTION_STATE_MACHINE.md`  
**Phase:** Priority 4.3.2 (Sensor Health Hardening & State-Machine Verification)  
**Status:** FORMALIZED & VALIDATED  
**Date:** October 31, 2026  

---

## 1. Executive Summary & Purpose

A vision-based assistive system must **never** operate in an ambiguous or unverified state. When video frames deteriorate due to environmental lighting, physical obstruction, or optical defocus, simply letting downstream algorithms (YOLOX-Nano, YuNet, Kalman tracking, and Nepali/English TTS) run indiscriminately causes phantom detections, track divergence, and audio spam.

The **Formal Perception State Machine** governs the operational life cycle of the vision pipeline. It guarantees deterministic, verified transitions between five distinct states, establishes strict track expiration bounds, and enforces precise audio suppression rules.

---

## 2. The Five Perception States

```
                 ┌──────────────────────────────────────┐
                 │          VALID_OBSERVATION           │◄────────┐
                 └───────┬──────────────────────┬───────┘         │
                         │                      │                 │
              Sensor     │                      │ 3 Consecutive   │
             Degraded    ▼                      ▼ Severely        │
                 ┌───────────────┐      ┌───────────────┐         │
                 │  TEMPORARILY  │      │    SENSOR     │         │
                 │   DEGRADED    │      │  UNAVAILABLE  │         │
                 └───────┬───────┘      └───────┬───────┘         │
                         │                      │                 │
                         │                      │ Coast > 5       │
                         │                      │ Frames          │
                         │                      ▼                 │
                         │              ┌───────────────┐         │
                         │              │     STALE     │         │
                         │              │  TERMINATED   │         │
                         │              └───────┬───────┘         │
                         │                      │                 │
                         │                      │ 3 Clean Frames  │
                         ▼                      ▼                 │
                 ┌──────────────────────────────────────┐         │
                 │         RECOVERY_TRANSITION          ├─────────┘
                 └──────────────────────────────────────┘
```

### State 1: `VALID_OBSERVATION`
- **Definition:** Camera optics, illumination, and frame clarity are fully verified within nominal parameters.
- **Sensor Criteria:** Health status is `NORMAL` (no occlusion, adequate luminance $\mu_L \in [40, 240]$, sharpness $\beta \ge 100$).
- **Pipeline Actions:**
  - Full deep learning inference (YOLOX-Nano, YuNet) executes.
  - Kalman filter receives fresh bounding-box measurement updates ($z_k$).
  - Spatial navigation announcements and crowd summaries are dispatched normally.
  - Telemetry: Green status indicator (`active: true`, `sensor_status: "normal"`).

### State 2: `TEMPORARILY_DEGRADED`
- **Definition:** Sensor quality is partially compromised by environmental factors (e.g. twilight lighting $\mu_L \in [15, 40)$, walking camera sway $\beta \in [25, 100)$, or flat painted wall $\sigma_C \in [4, 12)$), but coarse spatial structures remain discernible.
- **Pipeline Actions:**
  - Deep learning models execute, but detection confidence threshold is elevated ($0.35 \to 0.45$) to filter low-confidence hallucinations.
  - Kalman measurement noise covariance $R$ is scaled by $1.5\times$ to weight temporal momentum over noisy instantaneous observations.
  - Non-critical informational speech chatter is suppressed. Critical hazard alerts remain active.
  - Telemetry: Amber status indicator (`active: true`, `sensor_status: "degraded"`).

### State 3: `SENSOR_UNAVAILABLE`
- **Definition:** Sensor is severely degraded (pitch black $\mu_L < 15$, glare $\mu_L > 240$, optical defocus $\beta < 25$, or lens occlusion $\ge 2$ tiles) for $3$ consecutive frames ($99\text{ ms}$).
- **Pipeline Actions:**
  - **Downstream deep learning inference (YOLOX-Nano, YuNet) is completely bypassed.** (Saves $>50\text{ ms}$ CPU/battery).
  - Kalman tracking enters **prediction-only coasting** ($x_k = F x_{k-1}$, $P_k = F P_{k-1} F^T + Q$).
  - New obstacle detection is frozen. Existing obstacles are predicted forward for a maximum of $5$ frames.
  - Dispatches `CHIME_UNAVAILABLE` tone (subject to $5.0\text{s}$ cooldown).
  - Telemetry: Red status indicator (`active: true`, `sensor_status: "unavailable"`).

### State 4: `STALE_TERMINATED`
- **Definition:** Severe sensor outage has persisted beyond the mathematical safety limit ($> 5$ consecutive coasting frames / $> 165\text{ ms}$).
- **Pipeline Actions:**
  - **All active Kalman tracks are purged immediately.**
  - Coasting predictions are terminated to eliminate stale ghost obstacles.
  - Collision prediction and spatial navigation speech are suspended.
  - If ToF distance sensor is present, local range safety fallbacks activate.
  - Telemetry: Red flashing indicator (`active: false`, `sensor_status: "stale_terminated"`).

### State 5: `RECOVERY_TRANSITION`
- **Definition:** Transient intermediate state engaged when the sensor returns to clean nominal conditions for $\ge 3$ consecutive frames ($99\text{ ms}$) following an outage.
- **Pipeline Actions:**
  - Dispatches `CHIME_RECOVERY` rising chirp.
  - Re-engages YOLOX-Nano inference.
  - Initializes fresh Kalman tracks with clean covariance matrices. (Prohibits retroactive association with dead pre-outage tracks).
  - Automatically transitions to `VALID_OBSERVATION` on the very next frame.
  - Telemetry: Blue/cyan transient indicator (`sensor_status: "recovering"`).

---

## 3. Formal State Transition Matrix

The table below governs all permitted transitions ($S_{\text{current}} \to S_{\text{next}}$):

| Current State ($S_t$) | Incoming Frame Condition | Target State ($S_{t+1}$) | Permitted? | Guard Condition & Action |
| :--- | :--- | :--- | :--- | :--- |
| `VALID_OBSERVATION` | `NORMAL` | `VALID_OBSERVATION` | ✅ Yes | Continue nominal pipeline. |
| `VALID_OBSERVATION` | `DEGRADED` | `TEMPORARILY_DEGRADED` | ✅ Yes | Apply caution weighting ($R \times 1.5$). |
| `VALID_OBSERVATION` | `SEVERELY_DEGRADED` ($1\text{--}2\text{ frames}$) | `VALID_OBSERVATION` | ✅ Yes | Debounce buffer absorbs transient glitch. |
| `VALID_OBSERVATION` | `SEVERELY_DEGRADED` ($\ge 3\text{ frames}$) | `SENSOR_UNAVAILABLE` | ✅ Yes | Bypass DNN; initiate coasting; chime. |
| `VALID_OBSERVATION` | Any condition | `STALE_TERMINATED` | ❌ **INVALID** | Cannot jump straight to terminated without coasting. |
| `TEMPORARILY_DEGRADED` | `NORMAL` | `VALID_OBSERVATION` | ✅ Yes | Restore standard thresholds. |
| `TEMPORARILY_DEGRADED` | `DEGRADED` | `TEMPORARILY_DEGRADED` | ✅ Yes | Maintain caution mode. |
| `TEMPORARILY_DEGRADED` | `SEVERELY_DEGRADED` ($\ge 3\text{ frames}$) | `SENSOR_UNAVAILABLE` | ✅ Yes | Bypass DNN; initiate coasting; chime. |
| `SENSOR_UNAVAILABLE` | `SEVERELY_DEGRADED` ($C_{\text{coast}} \le 5$) | `SENSOR_UNAVAILABLE` | ✅ Yes | Continue Kalman prediction-only coasting. |
| `SENSOR_UNAVAILABLE` | `SEVERELY_DEGRADED` ($C_{\text{coast}} > 5$) | `STALE_TERMINATED` | ✅ Yes | **Safety limit reached: Purge tracks.** |
| `SENSOR_UNAVAILABLE` | `NORMAL` ($< 3\text{ frames}$) | `SENSOR_UNAVAILABLE` | ✅ Yes | Debounce buffer waits for stable signal. |
| `SENSOR_UNAVAILABLE` | `NORMAL` ($\ge 3\text{ frames}$) | `RECOVERY_TRANSITION` | ✅ Yes | Recovery confirmed; chirp dispatched. |
| `SENSOR_UNAVAILABLE` | Any condition | `VALID_OBSERVATION` | ❌ **INVALID** | Must pass through `RECOVERY_TRANSITION`. |
| `STALE_TERMINATED` | `SEVERELY_DEGRADED` | `STALE_TERMINATED` | ✅ Yes | Remain idle; rate-limit audio chimes. |
| `STALE_TERMINATED` | `NORMAL` ($\ge 3\text{ frames}$) | `RECOVERY_TRANSITION` | ✅ Yes | Re-engage vision; initialize fresh tracks. |
| `STALE_TERMINATED` | Any condition | `VALID_OBSERVATION` | ❌ **INVALID** | Direct jump prohibited; prevents track association race. |
| `RECOVERY_TRANSITION` | Any condition | `VALID_OBSERVATION` | ✅ Yes | Single-frame step: clean handoff to nominal. |

---

## 4. Track Expiration & Kalman Coasting Rules

1. **Maximum Coasting Duration ($C_{\text{max}}$):**
   $$C_{\text{max}} = 5\text{ frames} \quad (\approx 165\text{ ms at } 30\text{ FPS})$$
   Under no circumstances may a track coast beyond $5$ frames without measurement updates.
2. **Track Purge Contract:**
   Upon transition to `STALE_TERMINATED`, `PerceptionPipeline` must invoke `tracker.clear_all_tracks()`. All bounding-box histories, velocities, and Kalman state vectors are cleared from memory.
3. **No Retroactive Association:**
   When transitioning from `RECOVERY_TRANSITION` to `VALID_OBSERVATION`, newly detected bounding boxes must be treated as **brand new tracks** with fresh track IDs (`track_id = next_id++`). They must **never** be associated with pre-outage tracks, even if spatial proximity matches, because unobserved target movement during the outage makes velocity history invalid.

---

## 5. Speech & Audio Suppression Protocol

| Perception State | Informational Speech (e.g., Mode/Status) | Spatial Guidance (e.g., "Person ahead") | Critical Hazards (e.g., Immediate Drop-off) | Non-Verbal Auditory Chimes |
| :--- | :--- | :--- | :--- | :--- |
| **`VALID_OBSERVATION`** | Allowed (Standard Cooldown) | Allowed (Priority 2) | Allowed (Priority 1) | Recovery Chime on Entry |
| **`TEMPORARILY_DEGRADED`** | **Suppressed** | Allowed with Caution | Allowed (Priority 1) | None |
| **`SENSOR_UNAVAILABLE`** | **Suppressed** | Coasted Tracks Only ($\le 5\text{ frames}$) | Allowed (Priority 1) | `CHIME_UNAVAILABLE` ($5.0\text{s}$ Cooldown) |
| **`STALE_TERMINATED`** | **Suppressed** | **Suppressed** | Allowed if ToF Active | `CHIME_OUTAGE_EXPIRED` ($5.0\text{s}$ Cooldown) |
| **`RECOVERY_TRANSITION`** | **Suppressed** | Initializing | Allowed (Priority 1) | `CHIME_RECOVERY` (Exempt from Cooldown) |
