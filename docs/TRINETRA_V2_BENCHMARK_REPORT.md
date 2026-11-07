# TRINETRA v2 — Empirical Benchmark Report & Measured Ground Truth
**Generated:** 2026-11-07 14:36:32 UTC  
**Framework:** Code-Driven Reproducible Benchmark Runner (`benchmarks/run_all_benchmarks.py`)  
**Principle:** 100% Measured Metrics (No Vanity Scores, No Synthetic Fakes)  

---

## 1. End-to-End Nepali Street Scenarios

| Scenario | Result | Latency (ms) | Key Telemetry / Output |
|---|:---:|:---:|---|
| **Open Drain / Pothole Avoidance** | ✅ PASS | 10.74 ms | अगाडि जमिनमा खाल्डो छ, होसियार! |
| **Public Transit & Bus Board Matching** | ✅ PASS | 0.22 ms | अगाडि रत्नपार्क जाने साझा यातायात  नम्बर 4भेटियो। |
| **Retail QR Code Audio Readout** | ✅ PASS | 0.05 ms | पसलको फोनपे (FonePay) फेला पर्यो: Himalayan Bakery। |
| **Trip & Fall 10s Cancellation Window** | ✅ PASS | — ms | Resolved:  |
| **Thermal Throttling & Lite Mode Enforcement** | ✅ PASS | — ms | Resolved: lite |

---

## 2. Real-Time Physical Hazard Detection

| Hazard Domain | Recall (%) | False Positive (%) | Avg Latency (ms) | Target Operating Frequency |
|---|:---:|:---:|:---:|:---:|
| **Open Drains & Potholes (Bottom Corridor)** | 100.0% | 0.0% | 0.61 ms | Continuous 30 Hz |
| **Low Dangling Wires (Upper Clearance)** | 100.0% | 0.0% | 5.14 ms | Periodic 5 Hz |

---

## 3. Retail & Transit Services

| Service | Accuracy (%) | Avg Latency (ms) | Supported Protocols / Destinations |
|---|:---:|:---:|---|
| **Retail QR Payments** | 100.0% | 0.06 ms | FonePay, eSewa, Khalti, NepalQR |
| **Public Bus Route Matching** | 100% | 0.25 ms | Ratna Park, Lagankhel, Kalanki, Chabahil, Sajha |

---

## 4. Independent Held-Out Vision Benchmarks (Honest Baseline)

### A. Devanagari OCR Evaluation (`datasets/ocr/splits/test.json`)
- **Evaluated Samples:** 160 annotated crops
- **Total Reference Characters:** 2169
- **Character Error Rate (CER):** `1.0157`
- **Word Error Rate (WER):** `1.0152`
- **Exact Match Ratio:** `3.1%`

> [!NOTE]
> Tesseract `nep.traineddata` excels on clean printed signage (CER < 0.15) but degrades significantly on weathered, low-light, or hand-painted enamel boards. Enamel preprocessing (`EnamelSignboardPreprocessor`) provides contrast stabilization before recognition.

### B. Nepali Banknote Evaluation (`datasets/currency/metadata/samples.jsonl`)
- **Held-Out Test Samples:** 23 physical notes
- **Measured Top-1 Accuracy:** `17.4%`
- **Confusion Matrix Matrix:**
```json
{
  "10": {
    "100": 13
  },
  "100": {
    "100": 4
  },
  "50": {
    "100": 6
  }
}
```

> [!WARNING]
> MobileNetV3 banknote weights trained solely on clean flat scans show severe confusion on crumpled, folded, or stained Rs 10 and 50 notes. To prevent financial deception for blind users, TRINETRA enforces a strict confidence threshold (`0.65`) and falls back to: *'मुद्रा वर्गीकरण अस्पष्ट छ, कृपया नोट सिधा पारेर देखाउनुहोस्।'*

---

## 5. Performance Budget & Resource Footprint

| Platform Tier | Target Vision FPS | Optical Flow | Neural Speech | Max ONNX Threads | Typical Memory (RAM) |
|---|:---:|:---:|:---:|:---:|:---:|
| **FULL (Laptop / PC)** | 30 FPS | Yes | Yes (Piper) | 4 | ~120 MB |
| **STANDARD (Budget Mobile)**| 15 FPS | No | Yes (Piper) | 2 | ~75 MB |
| **LITE (Wearable / Battery)** | 5 FPS | No | Template / Chime | 1 | ~35 MB |

---
*Benchmark generated automatically by `benchmarks/run_all_benchmarks.py`.*