# TRINETRA — Priority 4.3: Sensor-Health Gatekeeper Benchmark Report
## Empirical Latency, Memory Footprint & Throughput Profiling

**Document:** `docs/research/priority-4.3/SENSOR_HEALTH_BENCHMARK.md`  
**Execution Environment:** Windows 11 Home (x86_64), AMD Ryzen 7 6800H with Radeon Graphics (16 vCPUs, 3.20 GHz base), 16 GB DDR5 RAM, Python 3.13.15, OpenCV 4.11.0  
**Data Artifact:** `docs/research/priority-4.3/benchmark_data.json`  
**Benchmark Date:** October 31, 2026  

---

## 1. Executive Summary & Latency Profile

The benchmark evaluates the CPU execution cost of the `SensorHealthGatekeeper` across 800 synthetic and real camera frames under eight operational conditions:
1. Sharp natural urban street scenes (`sharp_natural`)
2. Walking camera shake / multi-axis motion blur (`motion_blur`)
3. Severe optical defocus blur (`defocus_blur`)
4. Pitch black sensor noise floor (`pitch_black`)
5. Twilight / indoor dim lighting (`twilight_dim`)
6. Saturated solar glare / overexposure (`overexposed`)
7. Fully occluded lens (`occluded_lens`)
8. Textureless flat painted wall (`low_texture_wall`)

### 1.1. Summary Latency Table

| Ingestion Mode | Input Resolution | Eval Resolution | Samples | Mean Latency | Median (p50) | p95 Latency | p99 Latency | Single-Core FPS |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Decoded BGR Array** | $640 \times 480 \times 3$ | $320 \times 240$ (SIMD) | $800$ | **$0.596\text{ ms}$** | **$0.588\text{ ms}$** | **$0.666\text{ ms}$** | **$0.715\text{ ms}$** | **$1676.5\text{ FPS}$** |
| **Decoded BGR Array** | $640 \times 480 \times 3$ | $640 \times 480$ (Native) | $800$ | $2.223\text{ ms}$ | $2.073\text{ ms}$ | $2.933\text{ ms}$ | $3.525\text{ ms}$ | $449.8\text{ FPS}$ |
| **Raw JPEG Bytes** | $640 \times 480$ compressed | $320 \times 240$ (DCT 2x) | $75$ | **$0.799\text{ ms}$** | **$0.732\text{ ms}$** | **$1.084\text{ ms}$** | **$1.302\text{ ms}$** | **$1251.3\text{ FPS}$** |

```
Latency Distribution (Decoded BGR Array, 320x240 Eval):
Min    : 0.513 ms
p50    : 0.588 ms [██████████████████████████]
Mean   : 0.596 ms [██████████████████████████]
p95    : 0.666 ms [█████████████████████████████]
p99    : 0.715 ms [████████████████████████████████]
Max    : 1.157 ms [████████████████████████████████████████████]
StdDev : 0.038 ms (Extremely low jitter, deterministic real-time bound)
```

---

## 2. Key Engineering Findings

### 2.1. $73.2\%$ Latency Reduction via Linear SIMD Downsampling

Evaluating the Laplacian variance at native $640 \times 480$ requires computing second derivatives across $307,200$ pixels, consuming $2.223\text{ ms}$ per frame ($449.8\text{ FPS}$).

By bilinear downsampling to $320 \times 240$ ($76,800$ pixels), the total assessment latency collapses to **$0.596\text{ ms}$** ($1676.5\text{ FPS}$).
- **Latency saving:** $1.627\text{ ms}$ per frame ($73.2\%$ reduction).
- **Perception loop impact:** In a $30\text{ FPS}$ vision loop ($33.33\text{ ms}$ frame budget), spending $0.596\text{ ms}$ represents merely **$1.79\%$ of the available frame budget**, leaving $>98\%$ of CPU time for object detection, Kalman filtering, ego-motion compensation, and TTS dispatch.

### 2.2. Mathematical Precision: `cv2.CV_16S` vs `cv2.CV_64F`

OpenCV's default Python documentation frequently showcases `cv2.Laplacian(gray, cv2.CV_64F)`. Profiling revealed that:
1. `cv2.CV_64F` allocates double-precision floating-point arrays ($8$ bytes per pixel), which increases memory traffic, triggers CPU L2/L3 cache misses, and increases execution time to $3.17\text{ ms}$.
2. `cv2.CV_16S` operates directly in 16-bit signed integer registers ($2$ bytes per pixel). Second derivatives of an 8-bit image have a theoretical maximum domain of $[-2040, 2040]$, comfortably fitting within the $[-32768, 32767]$ range of signed 16-bit integers without overflow or rounding error.
3. `cv2.CV_16S` enables auto-vectorization across 16 parallel lanes in AVX2 registers (or 8 lanes in ARM NEON), achieving identical numerical variance results in $0.596\text{ ms}$.

### 2.3. Direct DCT 2x Grayscale JPEG Decoding

For network-streamed frames (e.g. mobile client streaming to engine or Tauri IPC):
- Traditional decoding (`cv2.imdecode(buf, cv2.IMREAD_COLOR)`) plus `cvtColor(BGR2GRAY)` plus `resize(320, 240)` takes $4.85\text{ ms}$.
- Utilizing libjpeg's DCT-domain downsampling decode (`cv2.IMREAD_REDUCED_GRAYSCALE_2`) directly extracts a $320 \times 240$ 8-bit single-channel image during entropy decoding, completing decompression *and* quality assessment in **$0.799\text{ ms}$ total**.

---

## 3. Memory Footprint & Allocation Profiling

The gatekeeper was profiled for dynamic memory allocation using Python's `tracemalloc`:

- **Static Object Memory:** $1.2\text{ KB}$ (immutable `SensorHealthThresholds` and `SensorHealthGatekeeper` instance).
- **Per-Frame Allocation Overhead:**
  - Downsampled grayscale buffer ($320 \times 240 \times 1\text{ uint8}$): $76.8\text{ KB}$.
  - Signed 16-bit Laplacian response ($320 \times 240 \times 2\text{ int16}$): $153.6\text{ KB}$.
  - Immutable `SensorHealthAssessment` tuple packet: $0.32\text{ KB}$.
  - Total transient memory footprint per evaluation: $\approx 231\text{ KB}$.
- **Garbage Collection Pressure:**
  Because the internal buffers are transient numpy arrays scoped within the method, memory is allocated from Python's C-level arenas and reused across calls without accumulating cyclic heap garbage.

---

## 4. Hardware Portability & Embedded Extrapolation

Based on empirical benchmarks on the AMD Ryzen 7 6800H ($0.596\text{ ms}$ on 1 core at $3.2\text{ GHz}$):

| Target Platform | Target Processor | Est. Clock | Single-Core Perf Ratio | Estimated Gatekeeper Latency |
| :--- | :--- | :--- | :--- | :--- |
| **x86_64 Laptop / Desktop** | AMD Ryzen 7 6800H / Core i7 | $3.2\text{ GHz}$ | $1.0\times$ (Measured) | **$0.596\text{ ms}$** |
| **Mid-Range Smartphone** | Snapdragon 7 Gen 1 (Cortex-A710) | $2.4\text{ GHz}$ | $\approx 2.4\times$ slower | **$1.43\text{ ms}$** |
| **Entry Smartphone** | MediaTek Helio G88 (Cortex-A75) | $2.0\text{ GHz}$ | $\approx 3.8\times$ slower | **$2.26\text{ ms}$** |
| **Embedded Wearable** | Raspberry Pi CM4 (Broadcom BCM2711) | $1.5\text{ GHz}$ | $\approx 4.5\times$ slower | **$2.68\text{ ms}$** |

Even on an entry-level smartphone or Raspberry Pi Compute Module 4, the Gatekeeper consumes $< 2.7\text{ ms}$, comfortably remaining well beneath the $10\text{ ms}$ pre-flight evaluation deadline.
