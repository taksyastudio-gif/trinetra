# TRINETRA — Priority 4.3.1: Real-World Sensor Health Validation Protocol
## Experimental Framework, Datasets & Measurement Methodology

**Document:** `docs/research/priority-4.3.1/REAL_WORLD_VALIDATION_PROTOCOL.md`  
**Execution Environment:** Windows 11 Home, AMD Ryzen 7 6800H CPU @ 3.20 GHz, Python 3.13.15, OpenCV 4.11.0  
**Phase:** Priority 4.3.1 (Independent Real-World Validation Gate)  
**Status:** COMPLETE & INDEPENDENTLY EXECUTED  
**Date:** October 31, 2026  

---

## 1. Objective & Scope

This protocol defines the independent validation methodology for the **Sensor-Health, Occlusion & Quality Gatekeeper** (`services/vision-engine/app/camera/sensor_health.py`).

While the Priority 4.3 benchmark established sub-millisecond execution ($0.596\text{ ms}$) on synthetic frames, this stage subjects the gatekeeper to **uncontrolled physical reality**:
1. Genuine Trinetra camera recordings from past test sessions.
2. Partial-frame physical obstructions (fingers, straps, carrying pouch flaps).
3. Realistic pedestrian walking dynamics (multi-axis body sway, footstep impact bob).
4. Extreme dynamic range transitions (walking into dark underpasses, solar glare flashes).
5. Natural low-texture surfaces (white walls, concrete, clear sky) vs. optical/mechanical failure.
6. Temporal recovery dynamics and debounce hysteresis.
7. Downstream perception consequences: Kalman track coasting and covariance blowup.

> [!IMPORTANT]
> **Safety Rule:** In accordance with user directives, **no accuracy claims are manufactured from synthetic data alone**. All experiments distinguish explicitly between:
> - **Recorded Ground Truth:** Unmodified photographic and webcam frames captured by Trinetra hardware.
> - **Physical Perturbation Transforms:** Real-world optical and spatial transformations applied directly to genuine captured frames.
> - **Synthetic Edge Controls:** Controlled mathematical baselines for sensitivity boundaries.

---

## 2. Dataset Provenance & Labeling

The evaluation uses four distinct datasets:

| Dataset Identifier | Provenance | Native Dimensions | Dynamic Range | Description & Ground Truth |
| :--- | :--- | :--- | :--- | :--- |
| **`DS-REC-1` (`trinetra_webcam`)** | `apps/desktop/trinetra-frame.jpg` | $640 \times 480 \times 3$ | $[0, 255]$ ($\mu=99.23$, $\sigma=68.73$) | Genuine Trinetra desktop webcam capture of indoor workspace under nominal ambient illumination. Ground truth: `NORMAL`. |
| **`DS-REC-2` (`root_webcam`)** | `trinetra-frame.jpg` (repo root) | $640 \times 480 \times 3$ | $[0, 52]$ ($\mu=13.20$, $\sigma=12.44$) | Genuine Trinetra capture during an unlit room test. Severe photometric starvation. Ground truth: `SEVERELY_DEGRADED` (`TOO_DARK`). |
| **`DS-REC-3` (`fixture_person`)** | `services/vision-engine/tests/fixtures/test_person.jpg` | $640 \times 424 \times 3$ | $[0, 255]$ ($\mu=161.28$, $\sigma=44.30$) | Natural daylight photograph of an approaching pedestrian on a street. Ground truth: `NORMAL`. |
| **`DS-REC-4` (`fixture_dog`)** | `services/vision-engine/tests/fixtures/test_dog.jpg` | $768 \times 576 \times 3$ | $[0, 255]$ ($\mu=132.73$, $\sigma=48.66$) | High-texture outdoor photograph of an animal obstacle on pavement. Ground truth: `NORMAL`. |

---

## 3. Seven Experimental Investigations

### Investigation 1: Baseline Recorded Frame Validation
Evaluates whether unmodified genuine Trinetra captures pass through the gatekeeper with zero false alarms under nominal lighting, and are correctly intercepted under darkness.

### Investigation 2: Partial-Frame Obstruction & Spatial Region Analysis
A fundamental vulnerability of scalar whole-image Laplacian variance is that localized obstructions (e.g. finger over $33\%$ of the lens) may leave the remaining $67\%$ sharp.
- **Occlusion Ratios:** $10\%$, $25\%$, $33\%$, $50\%$, $75\%$.
- **Spatial Sectors:** `top`, `bottom`, `left`, `right`, `center`.
- **Comparison:** Global scalar Gatekeeper vs. a prototype **$3 \times 3$ Spatial Region Grid** evaluating tile-level variance and contrast.

### Investigation 3: Realistic Pedestrian Walking Kinematics
Models the point spread function (PSF) of camera motion on a wearable/chest-mounted harness:
- **Horizontal Head/Torso Sway:** Panning displacement of $15\text{--}40\text{ px}$.
- **Vertical Footstep Impact Bob:** High-frequency impact oscillation of $10\text{--}25\text{ px}$.
- **Elliptical / Multi-Axis Jitter:** 2D curved trajectory simulating rapid head orientation change.

### Investigation 4: Dynamic Lighting & Changing Exposure Sequences
Evaluates temporal response across a continuous 40-frame sequence (representing $1.33\text{ seconds}$ at $30\text{ FPS}$):
- **Phase A (Frames 0–9):** Steady nominal daylight ($\mu_L \approx 100$).
- **Phase B (Frames 10–19):** Walking into an unlit tunnel / staircase ($\mu_L \to 5.3$).
- **Phase C (Frames 20–29):** Pitch darkness in tunnel interior ($\mu_L \approx 5.3$).
- **Phase D (Frames 30–34):** Emerging into blinding solar glare ($\mu_L \to 248.0$).
- **Phase E (Frames 35–39):** Auto-exposure settling back to nominal ($\mu_L \approx 133$).

### Investigation 5: Low-Texture Surface Disambiguation
Maps the feature separation boundary between:
1. Flat painted indoor wall ($\mu_L = 180$, $\sigma_C \approx 0.5$).
2. Painted wall with ambient shadow gradient ($\mu_L = 150$, $\sigma_C \approx 5.6$).
3. Uniform flat concrete sidewalk pavement ($\mu_L = 130$, $\sigma_C \approx 1.4$).
4. Genuine optical defocus blur of a textured street ($\mu_L = 99.2$, $\sigma_C = 65.8$, $\beta = 9.48$).
5. Physically covered lens ($\mu_L = 16.0$, $\sigma_C \approx 0.5$).

### Investigation 6: Temporal Recovery Dynamics & Debounce Hysteresis
A 60-frame sequence evaluates transition latencies:
- Clean frames ($0\text{--}14$) $\to$ Sudden dark occlusion ($15\text{--}29$) $\to$ Clean recovery ($30\text{--}59$).
- Measures exact frame latency for degradation onset and clean restoration.

### Investigation 7: Stale Detection & Kalman Coasting Safety Limits
When the gatekeeper detects `SEVERELY_DEGRADED` and suppresses YOLOX-Nano inference to prevent spurious hallucination, downstream Kalman filters must coast (predict without measurement updates).
- Models approaching pedestrian at $1.2\text{ m/s}$ ($10\text{ m}$ distance).
- Measures position variance $P_{0,0}$ and covariance trace $\operatorname{Tr}(P)$ across coasting durations of $1, 3, 5, 7, 10, 15, 20$ frames ($33\text{ ms}$ to $660\text{ ms}$).
- Identifies the mathematical safety ceiling beyond which coasting must be terminated.

---

## 4. Measurement Standards & Metrics

1. **False Rejection Rate (FRR):**
   $$\text{FRR} = \frac{\text{Sharp, Valid Frames Rejected as DEGRADED or SEVERELY\_DEGRADED}}{\text{Total Valid Frames Evaluated}} \times 100\%$$
2. **Missed Degradation Rate (MDR):**
   $$\text{MDR} = \frac{\text{Degraded Frames Accepted as NORMAL}}{\text{Total Degraded Frames Evaluated}} \times 100\%$$
3. **Latency Profile:** High-precision monotonic nanosecond profiling reporting p50, p95, and p99 execution times.
4. **Kalman Safety Limit:** Defined as $P_{0,0} < 1.0\text{ m}^2$ (position standard deviation $< 1.0\text{ m}$), preventing hazardous false spatial projections for blind users.
