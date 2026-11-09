# Trinetra Developer & Hardware Integration Guide

This directory provides developer integration scripts and guides to plug **Trinetra's 100% in-house, offline assistive intelligence** into any external application, robot, wearable camera, or smart glasses hardware.

---

## 🐍 5-Line Python Integration

Install or link `packages/trinetra-core`:

```python
from trinetra_core import TrinetraClient

# Connect to the local offline Trinetra engine
client = TrinetraClient(base_url="http://127.0.0.1:8000")

# Speak natural colloquial Nepali
client.speak("नमस्ते हजुर! म त्रिनेत्र प्रणाली हुँ।")

# Fetch real-time perception (obstacles, ground hazards, banknotes, signs)
detections = client.get_latest_detections()
```

---

## 🌐 Universal REST API (For Any Language: C++, Go, Rust, Node, Dart)

The local Vision Engine exposes clean REST endpoints on `http://127.0.0.1:8000`:

### 1. Announce Spoken Nepali (`POST /api/speech/announce`)
```bash
curl -X POST http://127.0.0.1:8000/api/speech/announce \
  -H "Content-Type: application/json" \
  -d '{"text": "नमस्ते हजुर!", "priority": "spatial_navigation", "interrupt": true, "language": "ne"}'
```

### 2. Stream / Poll Perception Detections (`GET /api/detection/latest`)
```bash
curl http://127.0.0.1:8000/api/detection/latest
```
Returns:
```json
{
  "frame_id": 450,
  "detections": [
    {"class_name": "person", "confidence": 0.92, "sector": "center", "distance_m": 2.4}
  ],
  "ground_hazard": {
    "detected": true,
    "hazard_type": "pothole",
    "message": "अगाडि जमिनमा खाल्डो छ, होसियार!"
  },
  "auto_currency": {
    "status": "identified",
    "denomination": 100,
    "message": "रू. 100 (एक सय)"
  },
  "sign_gesture": {
    "detected": true,
    "gesture_type": "namaste",
    "first_person_ne": "नमस्ते हजुर! सन्चै हुनुहुन्छ?",
    "third_person_ne": "अगाडिको व्यक्तिले 'नमस्ते' संकेत गर्नुभयो।"
  }
}
```

### 3. Toggle Auto-Currency Mode (`POST /api/currency/auto-mode`)
```bash
curl -X POST http://127.0.0.1:8000/api/currency/auto-mode \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### 4. Trigger In-Hand Note Recognition (`POST /api/currency/identify`)
```bash
curl -X POST http://127.0.0.1:8000/api/currency/identify \
  -H "Content-Type: application/json" \
  -d '{"speak": true}'
```

### 5. Trigger Devanagari OCR Reading (`POST /api/ocr/read`)
```bash
curl -X POST http://127.0.0.1:8000/api/ocr/read \
  -H "Content-Type: application/json" \
  -d '{"speak": true}'
```

---

## 📂 Example Scripts

- [`01_quickstart.py`](01_quickstart.py) — Connects to Trinetra, speaks in Nepali, and inspects live perception in 5 lines.
- [`02_wearable_smart_glasses.py`](02_wearable_smart_glasses.py) — Continuous 10 Hz perception loop for wearable glasses and robotic assistance.
