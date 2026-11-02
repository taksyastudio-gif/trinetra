# TRINETRA — Priority 4.3.2: Temporal Stability Results
## State Hysteresis, Transient Exposure & Audio Cooldown Analysis

**Document:** `docs/research/priority-4.3.2/TEMPORAL_STABILITY_RESULTS.md`  
**Execution Environment:** Windows 11 Home, AMD Ryzen 7 6800H CPU @ 3.20 GHz, Python 3.13.15, OpenCV 4.11.0  
**Data Artifact:** `docs/research/priority-4.3.2/hardening_metrics.json`  
**Date:** October 31, 2026  

---

## 1. Executive Summary & Problem Definition

In wearable assistive navigation, instantaneous frame-by-frame quality assessment without temporal memory causes **severe operational instability**:
1. **Dappled Sunlight Chattering:** Walking beneath trees or architectural grates causes rapid alternating illumination ($30\text{--}60\text{ Hz}$), toggling between nominal and degraded states every frame.
2. **Audio Chime Spam:** If an audio chime or voice announcement is dispatched on every degraded frame, the blind user experiences continuous cognitive bombardment, masking auditory environmental cues.
3. **Intermittent Obstruction:** A loose strap or coat zipper fluttering in the wind temporarily blocks the camera for 1 frame every 4 frames, causing thrashing in downstream Kalman filters.

This document presents empirical validation of the **Temporal Hysteresis & Debounce Architecture**, measuring state transitions, detection/recovery latencies, and audio cooldown enforcement.

---

## 2. Experimental Sequences & Empirical Results

Three rigorous dynamic temporal sequences were simulated and measured:

### 2.1. Scenario 1: Dappled Sunlight Exposure Chattering
A 30-frame sequence (representing $1.0\text{ second}$ of walking at $30\text{ FPS}$) alternating every single frame between deep tree shade ($\mu_L = 30.0$, `DEGRADED`) and direct solar glare ($\mu_L = 248.0$, `SEVERELY_DEGRADED`):

```
Frame Index:  00   01   02   03   04   05   06   07  ...  28   29
Raw Input:   Dark Glare Dark Glare Dark Glare Dark Glare ... Dark Glare
Raw Status:  [DEG][SEV] [DEG][SEV] [DEG][SEV] [DEG][SEV] ... [DEG][SEV]
Hysteresis:  [TEMPORARILY_DEGRADED ----------------------------->]
Chimes Sent: ZERO (0) Audio Spam Completely Prevented
```

#### Measured Results:
- **Total Frames Evaluated:** $30$
- **Raw Instantaneous Toggles:** $29$ toggles (would produce 29 audio alarms without debouncing).
- **Hysteresis State Machine Output:** Remained stably locked in `TEMPORARILY_DEGRADED`.
- **Audio Chimes Dispatched:** **$0$** (Audio nuisance completely eliminated).
- **Explanation:** Entry to `SENSOR_UNAVAILABLE` requires $K_{\text{degrade}} = 3$ consecutive severely degraded frames. Because the dappled sunbeam lasts only 1 frame, the system treats it as transient environmental noise, avoids killing Kalman tracks, and suppresses false alarms.

---

### 2.2. Scenario 2: Sudden Extreme Exposure Step Transitions
Evaluates continuous step transitions over 40 frames ($1.33\text{ seconds}$):
- Walking into a dark unlit stairwell (Frames 10–25).
- Momentary flash from a vehicle headlight or camera flash (Frames 30–33).
- Return to steady room lighting (Frames 34–40).

| Event Phase | Frame Range | Duration (ms) | Photometric Range ($\mu_L$) | State Machine State | Kalman Pipeline Action | Audio Chime Dispatched |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Nominal Daylight** | 0–9 | $330\text{ ms}$ | $99.2 \to 98.5$ | `VALID_OBSERVATION` | Full YOLOX & YuNet Updates | None |
| **Darkness Onset** | 10–12 | $99\text{ ms}$ | $65.4 \to 22.1$ | `TEMPORARILY_DEGRADED` | Caution Mode ($R \times 1.5$) | None |
| **Confirmed Darkness** | 13–19 | $231\text{ ms}$ | $18.5 \to 5.3$ | `SENSOR_UNAVAILABLE` | **Inference Suppressed; Coasting** | `CHIME_UNAVAILABLE` (Once) |
| **Prolonged Outage** | 20–29 | $330\text{ ms}$ | $5.3$ | `STALE_TERMINATED` | **Tracks Purged; System Idle** | None (Cooldown active) |
| **Sudden Headlight Flash** | 30–33 | $132\text{ ms}$ | $248.2$ | `STALE_TERMINATED` | Stays Terminated; No Spam | None |
| **Recovery Onset** | 34–36 | $99\text{ ms}$ | $110.0 \to 128.0$ | `RECOVERY_TRANSITION` | Initialize Fresh Kalman Tracks | `CHIME_RECOVERY` (Once) |
| **Restored Nominal** | 37–40 | $132\text{ ms}$ | $133.4$ | `VALID_OBSERVATION` | Full Perception Active | None |

---

### 2.3. Scenario 3: Intermittent Obstruction (Fluttering Strap / Hair)
Simulates a loose bag strap fluttering across the lens every 4 frames (Frames $0, 4, 8, 12, 16, 20$ obstructed; intervening frames clear):
- **Raw Instantaneous Assessment:** Toggles between `SEVERELY_DEGRADED` and `NORMAL` 10 times in 20 frames.
- **Hysteresis State Machine Output:**
  - The isolated 1-frame obstructions do not meet the $3\text{-frame}$ threshold for `SENSOR_UNAVAILABLE`.
  - The state machine transitions smoothly to `TEMPORARILY_DEGRADED`.
  - **Downstream Benefit:** YOLOX detections are processed with caution; Kalman tracks coast gracefully through the single-frame dip without track ID resets or false speech alerts.

---

## 3. Detection and Recovery Latency Profiles

The temporal parameters define the trade-off between **responsiveness to genuine failure** and **immunity to transient noise**:

| Transition Path | Required Consecutive Frames | Latency at 30 FPS | Latency at 15 FPS | Safety Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Nominal $\to$ Degraded** | $1\text{ frame}$ | **$33.3\text{ ms}$** | $66.7\text{ ms}$ | Immediate transition to cautious Kalman noise weighting ($R \times 1.5$) ensures quick safety adaptation. |
| **Nominal $\to$ Sensor Unavailable** | $3\text{ frames}$ | **$99.0\text{ ms}$** | $200.0\text{ ms}$ | Requires 100ms of sustained degradation before suppressing DNN inference, preventing premature model cancellation on single-frame glitches. |
| **Sensor Unavailable $\to$ Stale Terminated** | $5\text{ frames}$ coasting | **$165.0\text{ ms}$** | $333.3\text{ ms}$ | Strictly enforces the mathematically proven 5-frame Kalman safety ceiling, purging tracks before lateral uncertainty exceeds $1.0\text{ m}^2$. |
| **Unavailable / Stale $\to$ Recovery** | $3\text{ frames}$ | **$99.0\text{ ms}$** | $200.0\text{ ms}$ | Guarantees sensor has genuinely stabilized before re-engaging deep learning models and emitting the recovery chime. |

---

## 4. Audio Cooldown & Nuisance Prevention Protocol

A critical accessibility engineering requirement is preventing audio harassment:

```
                          Degradation Event Occurs
                                     │
                                     ▼
                      Is (Current Time - Last Chime) >= 5.0s?
                                     │
                        ┌────────────┴────────────┐
                        ▼                         ▼
                      [YES]                      [NO]
               Dispatch Audio Chime        Suppress Chime
               Record Last Chime Time      Maintain Silent State Log
```

### 4.1. Formal Audio Rules
1. **Minimum Retrigger Interval:** A minimum cooldown of **$5.0\text{ seconds}$** is enforced across all degradation chimes.
2. **Non-Verbal Frequency Discrimination:** Chimes use tone bursts rather than speech:
   - `CHIME_UNAVAILABLE`: Low two-tone descending beep ($220\text{ Hz} \to 180\text{ Hz}$, duration $120\text{ ms}$).
   - `CHIME_RECOVERY`: Rising pleasant chirp ($440\text{ Hz} \to 880\text{ Hz}$, duration $80\text{ ms}$).
3. **Recovery Exemption:** The `CHIME_RECOVERY` tone is exempt from the 5.0-second cooldown *if and only if* a prior `CHIME_UNAVAILABLE` was dispatched, ensuring the user always receives closure when clear vision returns.
4. **Speech Suppression:** During `SENSOR_UNAVAILABLE` and `STALE_TERMINATED`, informational speech announcements are strictly blocked. Only `CRITICAL_HAZARD` audio cues (from non-camera sensors like ToF or sonar) may bypass suppression.
