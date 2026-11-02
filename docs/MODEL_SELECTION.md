# Trinetra — Model Selection Evaluation & Verification (Sprint 3)

**Document Version:** 1.0.0  
**Date:** 2026-10-16  
**Auditor / Engineer:** Antigravity  
**Repository:** `D:\trinetra`  
**Purpose:** Independent evaluation, legal licensing review, technical architecture assessment, and provenance verification of candidate object detection models for on-device CPU inference in the Trinetra assistive vision platform.

---

## 1. Executive Summary & Decision

For Sprint 3 on-device AI object detection, three candidate models were investigated:
1. **YOLOX Nano** (Megvii Technology) — **SELECTED (Primary Verified Model)**
2. **YOLOv8 Nano** (Ultralytics) — **REJECTED AS DEFAULT DUE TO AGPL-3.0 COPYLEFT RESTRICTIONS; ARCHITECTURE COMPATIBILITY PRESERVED**
3. **MobileNet-SSD v1/v2** (Google / ONNX Model Zoo) — **REJECTED DUE TO LEGACY OPSET AND LOWER SPATIAL ACCURACY**

### Primary Selection: YOLOX Nano (`yolox_nano.onnx`)
- **Upstream Origin:** Official Megvii Technology release under tag `0.1.1rc0` (`Megvii-BaseDetection/YOLOX`).
- **Software License:** **Apache License 2.0** (Permissive, commercial-friendly, patent grant included, zero copyleft contagion).
- **Artifact Size:** **3,659,407 bytes** (~3.49 MB) — exceptionally lightweight for local assistive edge deployment.
- **In-Tree SHA-256 Pin:** `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d` (pinned from official release asset).
- **CPU Performance on Windows x64:** **22.68 ms average latency (~44.1 FPS)** on pure CPU via ONNX Runtime `CPUExecutionProvider`.
- **Task Alignment:** Anchor-free detection architecture with decoupled classification and regression heads; outstanding small-object precision and fast response times crucial for visually impaired spatial navigation.

---

## 2. Detailed Candidate Evaluation

### Candidate 1: YOLOX Nano (Megvii) — [SELECTED]
- **Repository / Source:** [Megvii-BaseDetection/YOLOX](https://github.com/Megvii-BaseDetection/YOLOX)
- **Direct Official Artifact URL:** `https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx`
- **Release Version:** `0.1.1rc0` (Asset ID `42724905`)
- **License Terms:** Apache License 2.0. The license is explicitly declared in `LICENSE` in the repository root. It permits commercial use, modification, distribution, and sublicensing without requiring open-source release of proprietary modifications or consumer applications.
- **Model Architecture:** Anchor-free CNN object detector with SimOTA label assignment.
- **Input Specification:** `images`: `float32[1, 3, 416, 416]` (BGR color layout, unnormalized pixel range $[0, 255]$ with 114 gray canvas padding).
- **Output Specification:** `output`: `float32[1, 3549, 85]` consisting of $3549$ candidate grid predictions across strides $8, 16, 32$ with $4$ box parameters ($cx, cy, w, h$), $1$ objectness score, and $80$ COCO class scores.
- **Memory Footprint:** $< 50$ MB RAM during active inference.
- **Digest Provenance & Limitation:** Downloaded directly over HTTPS from GitHub Releases API matching the exact file size (`3,659,407` bytes) recorded in the GitHub Release asset metadata. Upstream Megvii release notes do not publish a standalone signed `.sha256` or PGP signature; therefore, the computed SHA-256 (`c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`) functions as an **in-tree integrity pin and regression lock** against subsequent local corruption or altered re-downloads, rather than an independently signed third-party attestation.

### Candidate 2: YOLOv8 Nano (Ultralytics) — [COMPATIBILITY PRESERVED, NOT DEFAULT]
- **Repository / Source:** Ultralytics YOLOv8 (`ultralytics/ultralytics`)
- **License Terms:** **GNU Affero General Public License v3.0 (AGPL-3.0)** or Proprietary Enterprise License.
- **Legal & Distribution Risk:** Under AGPL-3.0, any derivative work or service distributed or networked with the model is subject to viral copyleft obligations. If Trinetra were distributed with YOLOv8 weights or depended upon Ultralytics code by default, the entire Trinetra codebase, including hardware interfaces and proprietary extensions, might be forced into AGPL-3.0 compliance. Commercial redistribution by assistive hardware manufacturers would be severely impaired.
- **Technical Metrics:** Input `[1, 3, 640, 640]`, output `[1, 84, 8400]`, size ~12.2 MB.
- **Resolution:** The `OnnxDetectionEngine` retains shape-adaptive postprocessing for `[1, 84, 8400]` so users who license YOLOv8 or export custom weights can load them, but the default, verified model shipped with Trinetra is permissively licensed YOLOX Nano.

### Candidate 3: MobileNet-SSD v1 / v2 (Google / ONNX Model Zoo) — [REJECTED]
- **Repository / Source:** ONNX Model Zoo (`onnx/models`)
- **License Terms:** Apache License 2.0.
- **Technical Metrics:** Input `[1, 3, 300, 300]`, size ~106 MB (v1) or ~68 MB (v2). Older ONNX opset (opset 10/11) with hardcoded non-standard NMS operator nodes that frequently break across newer ONNX Runtime versions on Windows x64.
- **Defects for Assistive Vision:** Low mean Average Precision (mAP) on small obstacles, pedestrian hazards, and indoor furniture. Substantially larger file size than YOLOX Nano despite lower accuracy.

---

## 3. Comparison Matrix

| Evaluation Criteria | YOLOX Nano (Selected) | YOLOv8 Nano | MobileNet-SSD v2 |
| :--- | :--- | :--- | :--- |
| **Upstream Maintainer** | Megvii Technology | Ultralytics | Google / ONNX Zoo |
| **Software License** | **Apache 2.0 (Permissive)** | **AGPL-3.0 (Strict Copyleft)** | Apache 2.0 (Permissive) |
| **Commercial Feasibility** | **High (No copyleft)** | Restricted (Requires Enterprise) | High |
| **Artifact File Size** | **3.66 MB** | 12.2 MB | 68 MB |
| **Input Dimensions** | $416 \times 416 \times 3$ | $640 \times 640 \times 3$ | $300 \times 300 \times 3$ |
| **Output Tensor** | `[1, 3549, 85]` | `[1, 84, 8400]` | Multi-tensor / custom NMS |
| **CPU Latency (Avg)** | **22.68 ms** | ~45-55 ms | ~28 ms |
| **CPU Throughput** | **44.1 FPS** | ~18-22 FPS | ~35 FPS |
| **Detection Quality (mAP)** | High (Anchor-Free) | High | Low - Moderate |
| **Digest Provenance** | **Verified Official Release** | Variable (Export dependent) | Official Model Zoo |

---

## 4. Verification and Security Controls

1. **Cryptographic Integrity:** The model binary is checked at startup against `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`. Any alteration, truncation, or substitution immediately raises `ModelIntegrityError`.
2. **Git Binary Handling:** `.gitignore` explicitly excludes `*.onnx`, `*.weights`, and `*.pt` to prevent accidental binary bloat in Git history.
3. **Execution Safety:** The model is treated purely as serialized neural weights parsed by ONNX Runtime's C++ graph parser; it is never executed as program code or unpickled via Python `pickle`.
4. **Local-First Privacy:** Zero network calls are made during inference. Video frames and bounding boxes are evaluated strictly on loopback within device RAM.

---

## 6. Automated Model Setup & Fresh Clone Reproducibility (Sprint 4.1)

Because binary `.onnx` files are excluded from Git to prevent repository bloat, fresh repository clones must acquire verified model weights prior to production use.

### Setup Script
A standalone, zero-dependency Python script is provided at `services/vision-engine/scripts/setup_models.py`.

```bash
# Standard automated setup (downloads Megvii release, verifies SHA-256, atomically installs)
python services/vision-engine/scripts/setup_models.py

# Verify cryptographic integrity of existing weights without downloading
python services/vision-engine/scripts/setup_models.py --check-only

# Offline / air-gapped environment import from local file
python services/vision-engine/scripts/setup_models.py --local-file /path/to/downloaded_yolox_nano.onnx

# Force re-download even if a valid file exists
python services/vision-engine/scripts/setup_models.py --force
```

### Integrity & Safety Guarantees
- **Pinned SHA-256 Digest:** `c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`
- **Atomic File Replacement:** Downloads to a temporary file (`.tmp.<pid>`) and verifies SHA-256 before atomic rename (`os.replace`). Partial or corrupted downloads never overwrite valid models.
- **Idempotence:** If the target model file already exists and its hash matches the pinned digest, the script exits immediately with code 0 without making network requests.
- **Explicit Failure Handling:** If model weights are missing or corrupt, `get_default_detection_engine()` returns `UnavailableDetectionEngine` with `is_ready: False`. The application never emits silent mock detections in production, and attempting to start detection returns HTTP 503 with instructions to run `setup_models.py`.

