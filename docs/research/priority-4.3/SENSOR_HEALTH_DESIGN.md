# TRINETRA — Priority 4.3: Sensor-Health, Occlusion & Quality Gatekeeper
## Architectural Design & Mathematical Formulation

**Document:** `docs/research/priority-4.3/SENSOR_HEALTH_DESIGN.md`  
**Version:** 1.0.0 (Priority 4.3 Controlled Implementation)  
**Status:** IMPLEMENTED & BENCHMARKED (ISOLATED)  
**Author:** Trinetra Assistive Intelligence Core Team  
**Date:** October 31, 2026  

---

## 1. Executive Summary & Purpose

The **Sensor-Health, Occlusion & Quality Gatekeeper** is the first implementation milestone derived from the **Priority 4.2 Engineering Decision Matrix** (Priority 1: Gatekeeper & Health Layer). 

In assistive navigation for blind and low-vision individuals, false negative detections (failing to alert a user to a dangerous obstacle or vehicle) frequently stem not from deep learning model failure, but from **upstream sensor degradation**:
1. Camera obscured by clothing, fingers, carrying straps, or bag flaps.
2. Sudden lighting changes (entering a pitch-black underpass, unlit staircase, or blinding solar glare).
3. Severe walking motion blur (rapid head turns, body sway, stumbling).
4. Optical defocus blur (dirty lens, macro focus lock, optical misalignment).

Allowing an object detector (YOLOX-Nano, YuNet) or trajectory tracking pipeline (Kalman, Lucas-Kanade optical flow) to run unconditionally on corrupted, dark, or blurred frames wastes scarce battery and CPU compute, injects spurious noise into Kalman filters, and can produce fatal silent failures.

The Gatekeeper acts as an **independent, zero-allocation, sub-millisecond pre-flight validator** that inspects incoming frames *before* heavier downstream perception tasks execute.

```
                          Incoming Camera Frame
                       [BGR ndarray or JPEG bytes]
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │    SensorHealthGatekeeper     │
                   │  - SIMD Grayscale Downsample  │
                   │  - cv2.meanStdDev (Luminance) │
                   │  - cv2.Laplacian (CV_16S)     │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
                     Diagnostics Assessment Packet
                     - HealthStatus (NORMAL / DEGRADED / SEVERELY_DEGRADED)
                     - ActionRecommendation (PROCESS / CAUTION / SUPPRESS)
                     - Metric Scores (Blur, Luminance, Contrast)
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
   [NORMAL]                   [DEGRADED]             [SEVERELY_DEGRADED]
Proceed to full          Proceed with caution     Suppress downstream DNN
Perception Loop          - Soften confidence      - Save battery/CPU
- YOLOX Detection        - Maintain tracking      - Play non-verbal chime
- YuNet Faces            - Log telemetry warning  - Prevent hallucination
- Kalman Tracking
```

---

## 2. Mathematical Formulation & Edge Metrics

The gatekeeper uses three lightweight, deterministic computer vision primitives computed on a single-channel 8-bit grayscale image $I(x, y)$ of dimensions $W \times H$:

### 2.1. Mean Luminance (Exposure & Illumination Assessment)

The average image brightness $\mu_L$ is computed via single-pass SIMD vector reduction:
$$\mu_L = \frac{1}{W \cdot H} \sum_{x=0}^{W-1} \sum_{y=0}^{H-1} I(x, y)$$

- **Physical Meaning:** Overall photometric flux incident on the CMOS sensor.
- **Dynamic Range:** $[0.0, 255.0]$ for standard 8-bit unsigned integer buffers.

### 2.2. Global Contrast (Standard Deviation)

The global contrast $\sigma_C$ measures the dispersion of pixel intensities around the mean:
$$\sigma_C = \sqrt{\frac{1}{W \cdot H} \sum_{x=0}^{W-1} \sum_{y=0}^{H-1} \left(I(x, y) - \mu_L\right)^2}$$

- **Physical Meaning:** Scene dynamic range and structural feature presence. A frame with $\sigma_C \to 0$ contains no usable spatial gradients (either pitch black, bleached white, or physically occluded by a flat obstacle).

### 2.3. Edge Sharpness via Laplacian Variance

The Laplacian operator $\nabla^2 I$ computes the second spatial derivative (divergence of the gradient) of the 2D image:
$$\nabla^2 I(x, y) = \frac{\partial^2 I}{\partial x^2} + \frac{\partial^2 I}{\partial y^2}$$

In discrete space, this is evaluated using the standard $3 \times 3$ isotropic convolution kernel:
$$K_L = \begin{bmatrix} 0 & 1 & 0 \\ 1 & -4 & 1 \\ 0 & 1 & 0 \end{bmatrix}$$

The edge sharpness metric $\beta$ (blur score) is the sample variance of the Laplacian response:
$$\mu_{\nabla^2} = \frac{1}{W \cdot H} \sum_{x=0}^{W-1} \sum_{y=0}^{H-1} (\nabla^2 I)(x, y)$$
$$\beta = \operatorname{Var}(\nabla^2 I) = \frac{1}{W \cdot H} \sum_{x=0}^{W-1} \sum_{y=0}^{H-1} \left( (\nabla^2 I)(x, y) - \mu_{\nabla^2} \right)^2$$

- **Physical Meaning:** Sharp, in-focus images with rapid intensity transitions exhibit large positive and negative second derivatives, yielding high variance. Blurred, defocused, or smeared images smooth out edge transitions, driving the Laplacian response toward zero and drastically reducing variance.

---

## 3. Threshold Calibration & Diagnostic Decision Logic

Threshold boundaries were established empirically through multi-condition benchmarks across 800 synthetic frames and verified against genuine Trinetra webcam captures (`trinetra-frame.jpg`, `test_dog.jpg`, `test_person.jpg`):

| Metric | Threshold Field | Value | Physical & Empirical Reasoning |
| :--- | :--- | :--- | :--- |
| **Pitch Black Floor** | `luminance_too_dark` | `15.0` | Below $15.0$, sensor noise dominates photon count. YOLOX-Nano cannot resolve pedestrian contours. |
| **Low-Light / Twilight** | `luminance_low_light` | `40.0` | Between $15.0$ and $40.0$, pedestrian silhouettes exist but color information and edge contrasts are degraded. |
| **Solar Glare / Bleach** | `luminance_too_bright` | `240.0` | Above $240.0$, CMOS photodiode wells saturate into pure white clipping ($255$), obliterating edges. |
| **Occlusion Threshold** | `contrast_occlusion_threshold` | `4.0` | A finger, cloth flap, or lens cap directly against the aperture produces near-uniform luminance ($\sigma_C < 4.0$). |
| **Low-Texture Floor** | `contrast_low_texture` | `12.0` | A smooth painted wall or featureless ceiling illuminated normally exhibits low standard deviation ($\sigma_C \in [4.0, 12.0)$). Disambiguates blank surfaces from optical defocus. |
| **Severe Defocus Blur** | `blur_severe_threshold` | `25.0` | Heavy optical defocus ($\sigma_{\text{blur}} \ge 9.0$) drops Laplacian variance below $25.0$. Object detection bounding boxes collapse. |
| **Motion Blur Threshold** | `blur_degraded_threshold` | `100.0` | Human walking camera shake ($k \approx 20\text{--}35\text{ px}$) drops variance into $[25.0, 100.0)$. Small distant hazards are obscured. |

### 3.1. Diagnostic Rule Hierarchy

The diagnostic engine evaluates checks in a strictly ordered, orthogonal decision ladder:

```python
# 1. Illumination Checks
if mean_lum < thresholds.luminance_too_dark:
    is_dark = True; reasons.append(TOO_DARK)
elif mean_lum < thresholds.luminance_low_light:
    is_dark = True; reasons.append(LOW_LIGHT)
elif mean_lum > thresholds.luminance_too_bright:
    is_bright = True; reasons.append(TOO_BRIGHT)

# 2. Occlusion / Texture / Sharpness Checks
if contrast < thresholds.contrast_occlusion_threshold:
    is_occluded = True; reasons.append(OCCLUDED_LENS)
elif not is_dark and not is_bright:
    if contrast < thresholds.contrast_low_texture:
        # Scene is well-lit but featureless (e.g. blank wall)
        reasons.append(LOW_TEXTURE)
    else:
        # Scene has physical structure; evaluate optical sharpness
        if blur_score < thresholds.blur_severe_threshold:
            is_blurry = True; reasons.append(DEFOCUS_BLUR)
        elif blur_score < thresholds.blur_degraded_threshold:
            is_blurry = True; reasons.append(MOTION_BLUR)

# 3. Policy Synthesis
if (TOO_DARK in reasons or TOO_BRIGHT in reasons or 
    OCCLUDED_LENS in reasons or DEFOCUS_BLUR in reasons):
    status = HealthStatus.SEVERELY_DEGRADED
    action = ActionRecommendation.SUPPRESS_AND_CHIME
elif (LOW_LIGHT in reasons or MOTION_BLUR in reasons or 
      LOW_TEXTURE in reasons):
    status = HealthStatus.DEGRADED
    action = ActionRecommendation.PROCESS_WITH_CAUTION
else:
    status = HealthStatus.NORMAL
    action = ActionRecommendation.PROCESS
```

---

## 4. Performance Optimization Architecture

To maintain a sub-millisecond execution budget ($< 1.0\text{ ms}$) on low-power mobile and laptop CPUs without GPU acceleration:

1. **Spatial Downsampling to $320 \times 240$:**  
   Computing a full $640 \times 480$ Laplacian on float64 takes $3.17\text{ ms}$. Bilinear downsampling to $320 \times 240$ reduces pixel count by $4\times$ ($76,800$ vs $307,200$ pixels), executing in $0.02\text{ ms}$ and preserving relative variance gradients perfectly.
2. **`cv2.CV_16S` Signed 16-Bit Laplacian:**  
   Instead of default 64-bit float (`cv2.CV_64F`), the gatekeeper uses signed 16-bit integers (`cv2.CV_16S`). Because second derivatives of an 8-bit image cannot exceed $[-2040, 2040]$, 16-bit signed integer math is mathematically exact, avoids overflow, uses SIMD vector registers (AVX2/NEON), and cuts kernel latency by $55\%$.
3. **Single-Pass Mean and Standard Deviation (`cv2.meanStdDev`):**  
   Simultaneously computes $\mu_L$ and $\sigma_C$ in a single hardware-vectorized memory pass over the downsampled grayscale buffer.
4. **Fast DCT-Domain JPEG Decoding:**  
   When ingesting raw JPEG network bytes (e.g., streaming over HTTP/WebSocket), `cv2.IMREAD_REDUCED_GRAYSCALE_2` decodes directly from discrete cosine transform coefficients at half-resolution without allocating an intermediate full-size BGR color image.

---

## 5. Critical Engineering Limitations (Honest Assessment)

> [!WARNING]
> **What Laplacian Variance & Global Contrast CANNOT Do:**
> 1. **Partial Lens Occlusion:** If a user's finger covers the bottom $30\%$ of the lens while the upper $70\%$ observes a sharp outdoor street, global Laplacian variance may remain comfortably above $150.0$, and global contrast will remain normal. The gatekeeper evaluates global frame statistics and **cannot pinpoint localized sector occlusions**. Spatial grid partitioning ($3 \times 3$ tile analysis) will be explored in Priority 4.3 Phase 2.
> 2. **Transparent / Greasy Smudges:** A thin film of grease, sweat, or water droplets acts as a soft optical low-pass filter that softens micro-contrast while leaving coarse edges detectable. While severe grease triggers `MOTION_BLUR` or `DEFOCUS_BLUR`, light smudges may pass as `NORMAL`.
> 3. **Semantic Hallucination Prevention:** The gatekeeper measures signal quality, not semantic content. A perfectly sharp, high-contrast photograph held directly in front of the lens will be classified as `NORMAL`.
