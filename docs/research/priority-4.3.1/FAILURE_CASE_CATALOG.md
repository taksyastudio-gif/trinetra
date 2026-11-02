# TRINETRA — Priority 4.3.1: Failure Case Catalog
## Real-World Edge Cases, Failure Modes & Engineering Mitigations

**Document:** `docs/research/priority-4.3.1/FAILURE_CASE_CATALOG.md`  
**Phase:** Priority 4.3.1 (Independent Real-World Validation Gate)  
**Status:** VALIDATED & CATALOGED  
**Date:** October 31, 2026  

---

## 1. Executive Summary

A critical requirement of assistive navigation engineering is an **honest catalog of failure boundaries**. An algorithm that claims to detect 100% of sensor degradations without acknowledging physical blind spots creates dangerous false security for visually impaired pedestrians.

Through empirical testing of genuine Trinetra hardware recordings and physical perturbation sequences, this catalog documents the **six primary failure modes** of the baseline Sensor Health Gatekeeper, explains their root mathematical causes, and defines concrete mitigations.

---

## 2. Failure Case Catalog

```
┌────────────────────────────────────────────────────────────────────────┐
│                      GATEKEEPER FAILURE TAXONOMY                       │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Partial-Frame Occlusion (Mask edge variance inflation)              │
│ 2. Point-Blank Low-Texture False Occlusion (Contrast < 4.0)            │
│ 3. Foreground High-Frequency Masking of Background Defocus             │
│ 4. Dappled Sunlight Exposure Chattering                                │
│ 5. Excessive Kalman Coasting Drift (> 7 frames)                        │
│ 6. Transparent Greasy Smudge / Rain Droplet Micro-Contrast Decay       │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Failure Mode 1: Partial-Frame Obstruction Missed by Global Laplacian Variance

#### Description:
A user's coat strap, carrying pouch, or finger covers $33\%$ to $75\%$ of the camera lens, physically obscuring oncoming pedestrians in that sector.

#### Observed Failure Behavior:
- When $50\%$ of the bottom half of a genuine webcam frame was occluded by a dark strap:
  - Global Laplacian variance **increased from $642.44$ to $2989.84$**!
  - Global Gatekeeper emitted `HealthStatus.NORMAL` with `ActionRecommendation.PROCESS`.
  - **Result: Catastrophic Missed Degradation (MDR = 100% on partial occlusions).**

#### Mathematical Root Cause:
The Laplacian operator $\nabla^2 I$ detects second spatial derivatives. The sharp artificial boundary between the dark obstruction (pixel intensity $\approx 20$) and the bright scene (pixel intensity $\approx 150$) produces an intense step gradient across several hundred pixels. This single artificial boundary injects massive high-frequency energy that artificially inflates the whole-image variance calculation, completely masking the fact that half the field of view is blinded.

#### Concrete Mitigation:
**Spatial $3 \times 3$ Region Grid Partitioning:**
Partition the downsampled $320 \times 240$ buffer into nine $106 \times 80$ spatial sectors. Evaluate local contrast $\sigma_{\text{tile}}$ and luminance $\mu_{\text{tile}}$ per sector. If $\ge 2$ adjacent tiles exhibit $\sigma_{\text{tile}} < 6.0$ and $\mu_{\text{tile}} < 35.0$, flag `PARTIAL_OCCLUSION` and alert the user to the specific obscured sector (e.g., *"Lower camera obstructed"*).
- Spatial $3 \times 3$ grid profiling demonstrated $100\%$ detection of $50\%$ and $75\%$ occlusions with only $0.08\text{ ms}$ of additional CPU overhead.

---

### Failure Mode 2: Point-Blank Low-Texture Wall Misclassified as Occlusion

#### Description:
The user stands facing a smooth, freshly painted white interior wall or holds the camera point-blank against flat concrete pavement.

#### Observed Failure Behavior:
- For a uniform painted wall ($\mu_L = 180.0$, $\sigma_C = 0.53$):
  - Gatekeeper classified as `SEVERELY_DEGRADED` with `OCCLUDED_LENS`.
  - Action recommended: `SUPPRESS_AND_CHIME`.
- For flat concrete pavement ($\mu_L = 130.0$, $\sigma_C = 1.38$):
  - Gatekeeper classified as `SEVERELY_DEGRADED` with `OCCLUDED_LENS`.

#### Mathematical Root Cause:
The threshold for lens occlusion is `contrast_occlusion_threshold = 4.0`. While a covered lens produces near-zero standard deviation ($\sigma_C \approx 0.5\text{--}1.5$), a completely featureless white surface also exhibits $\sigma_C \approx 0.5\text{--}1.5$. Without depth information, 2D passive monocular vision cannot mathematically distinguish a clean lens viewing a blank wall from a white paper sheet pressed directly against the glass.

#### Concrete Mitigation:
1. **Luminance Coupling:** True lens occlusion by clothing or fingers almost always causes photon starvation ($\mu_L < 35.0$). A white wall has normal-to-high illumination ($\mu_L > 100.0$).
2. **Refined Occlusion Logic:** Classify as `OCCLUDED_LENS` only if $\sigma_C < 4.0$ **AND** $\mu_L < 50.0$. If $\sigma_C < 4.0$ but $\mu_L \ge 50.0$, classify as `LOW_TEXTURE` (`DEGRADED`, process with caution) rather than raising an occlusion alarm.
3. **Future ToF Integration:** A Time-of-Flight distance sensor (VL53L8CX) measures physical distance directly: distance $\approx 0\text{ mm}$ confirms occlusion, whereas distance $\ge 500\text{ mm}$ confirms an open wall.

---

### Failure Mode 3: Foreground High-Frequency Artifacts Masking Optical Defocus

#### Description:
The camera lens is severely out of focus (unable to resolve objects beyond 1 meter), but the camera is looking through a window insect screen, fine wire mesh, or dirty scratch marks on the protective lens glass.

#### Observed Failure Behavior:
- Background pedestrians at $3\text{--}10\text{ meters}$ are completely blurred into unrecognizable blobs.
- However, the sharp wire mesh or protective glass scratch directly on the focal plane generates sharp Laplacian derivatives.
- Global Laplacian variance remains high ($\beta > 300.0$).
- Gatekeeper reports `NORMAL`, allowing YOLOX-Nano to run and miss all oncoming obstacles.

#### Mathematical Root Cause:
Laplacian variance measures total edge energy across all spatial frequencies and depths. It cannot determine *which* depth layer produced the sharp edges. Sharp foreground dirt compensates for blurred background hazards.

#### Concrete Mitigation:
1. **Multi-Scale Laplacian Pyramid:** Compute Laplacian at two spatial downsamplings ($320 \times 240$ and $160 \times 120$). Fine scratch marks disappear at the lower octave, whereas genuine scene edges persist across scales.
2. **Active Optics / Fixed-Focus Verification:** On fixed-focus wide-angle wearable cameras (hyperfocal distance $0.5\text{m} \to \infty$), optical defocus occurs primarily from physical lens displacement or heavy front-element contamination.

---

### Failure Mode 4: Exposure Chattering in Dappled Sunlight

#### Description:
A blind user walks along a tree-lined street with rapid alternation between intense sunbeams and deep foliage shadows, or passes beneath flickering construction floodlights.

#### Observed Failure Behavior:
- Frame $N$: In shadow ($\mu_L = 38.0$) $\to$ `DEGRADED` (`LOW_LIGHT`).
- Frame $N+1$: Sunbeam enters lens ($\mu_L = 242.0$) $\to$ `SEVERELY_DEGRADED` (`TOO_BRIGHT`).
- Frame $N+2$: Exposure drops ($\mu_L = 110.0$) $\to$ `NORMAL`.
- **Result:** Rapid state toggling (30 toggles per second), risking audio chime spam and rapid switching of Kalman filter noise covariances.

#### Mathematical Root Cause:
Evaluating health strictly frame-by-frame with zero temporal memory makes instantaneous decisions vulnerable to physical environmental high-frequency fluctuations.

#### Concrete Mitigation:
**Temporal Hysteresis & Debounce Filter:**
Implement an exponential moving average (EMA) or moving-window majority vote:
- Transition to `SEVERELY_DEGRADED` requires **$3$ consecutive degraded frames** ($100\text{ ms}$).
- Transition from `SEVERELY_DEGRADED` back to `NORMAL` requires **$5$ consecutive clean frames** ($165\text{ ms}$).
- Audio chimes must be strictly locked behind a **$5.0\text{ second}$ non-retrigger cooldown**.

---

### Failure Mode 5: Excessive Kalman Track Coasting Drift

#### Description:
The camera is occluded or pitch black for $15$ frames ($0.5\text{ seconds}$). During this time, the gatekeeper suppresses detections, but downstream Kalman filters continue predicting forward based on old velocities.

#### Observed Failure Behavior:
- At $15\text{ frames}$ of coasting, pedestrian position variance grows by **$5.7\times$** ($1.477\text{ m}^2$).
- At $20\text{ frames}$ ($0.66\text{ seconds}$), variance grows by **$8.2\times$** ($2.122\text{ m}^2$).
- If the pedestrian slowed down, turned, or stopped during the 0.5-second blackout, the system projects their ghost position directly in front of the blind user, issuing false collision warnings or, worse, projecting an empty path into an obstacle.

#### Mathematical Root Cause:
In a constant-velocity Kalman filter with state transition $F = \begin{bmatrix} 1 & \Delta t \\ 0 & 1 \end{bmatrix}$, error covariance propagates as $P_{k} = F P_{k-1} F^T + Q$. Without measurement updates ($H P H^T + R$), position variance grows quadratically with time: $\sigma^2(t) \propto t^2 \sigma_v^2 + t Q$.

#### Concrete Mitigation:
**Hard Coasting Ceiling:**
1. Permit coasting for **up to $5$ frames ($165\text{ ms}$)**. Position uncertainty remains $< 0.6\text{ m}^2$.
2. Between **$5$ and $7$ frames ($165\text{--}230\text{ ms}$)**: Freeze hazard alerts; mark tracks as unverified.
3. At **frame $8$ ($> 230\text{ ms}$)**: Terminate all coasting tracks. Mark tracking state as `STALE_TERMINATED`. Emit soft audio alert informing user that perception is temporarily paused.

---

### Failure Mode 6: Transparent Greasy Smudges and Rain Droplets

#### Description:
A thumbprint of skin oil or light rain droplets coats the camera lens.

#### Observed Failure Behavior:
- Light and coarse shapes pass through the grease.
- High-contrast building edges still register $\beta \approx 120\text{--}250$ (above the $100.0$ threshold).
- However, subtle low-contrast hazards (e.g., pavement cracks, low curbs, guy wires) have their MTF destroyed.
- Gatekeeper reports `NORMAL`.

#### Mathematical Root Cause:
A thin greasy film reduces the modulation transfer function (MTF) primarily at high spatial frequencies while leaving macro-edges detectable.

#### Concrete Mitigation:
1. Greasy smudges cannot be reliably distinguished from natural atmospheric haze by 2D scalar Laplacian variance alone.
2. In Phase 2, incorporate a high-frequency energy ratio metric ($E_{\text{high}} / E_{\text{total}}$) via discrete wavelet transform (DWT) or high-pass FFT energy, which specifically isolates micro-contrast decay.
