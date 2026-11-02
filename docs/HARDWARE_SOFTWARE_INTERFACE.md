# TRINETRA — Hardware / Software Interface Specification

**Document Version:** 1.0.0  
**Status:** Active Interface Contract  
**Components:** ESP32-CAM Physical Sensor Rig <---> Local Vision Engine / Desktop Supervisor  
**Updated:** November 2026  

---

## 1. Overview & Architectural Boundaries

TRINETRA connects wearable edge hardware (ESP32-CAM) with an on-device local vision processing engine over standard network protocols. This document specifies the data formats, endpoints, physical constraints, error-handling mechanisms, and lifecycle states governing the boundary between the two systems.

---

## 2. Video Streaming & Camera Data Interface

### 2.1 Protocol & Transport
- **Protocol:** HTTP 1.1 multipart MJPEG stream.
- **Content-Type:** `multipart/x-mixed-replace; boundary=frame` (or standard `boundary=--frame`).
- **Endpoint:** `GET http://<ESP32_IP>:81/stream` (Default port `81` as used by standard ESP32-CAM stream server).
- **Ingestion Implementation:** Ingested via OpenCV in [`services/vision-engine/app/camera/adapter.py`](file:///d:/trinetra/services/vision-engine/app/camera/adapter.py):
  ```python
  # When camera_index is string URL:
  cap = cv2.VideoCapture("http://192.168.1.100:81/stream")
  ```

### 2.2 Frame Specifications
| Dimension | Specification | Notes |
| :--- | :--- | :--- |
| **Resolution** | **640 x 480 (VGA)** | Primary operational resolution. |
| **Fallback Resolution** | **320 x 240 (QVGA)** | Low-bandwidth or low-power fallback. |
| **Aspect Ratio** | 4:3 | Standard OV2640 sensor layout. |
| **Frame Rate** | **15.0 – 25.0 FPS** | Nominal target: 20 FPS. |
| **JPEG Quality Factor** | `10` to `15` | Balance of artifact reduction and bandwidth. |
| **Max Network Bandwidth** | 1.5 – 2.5 Mbps | At 640x480 @ 20 FPS with Q=12. |
| **Latency Budget** | **< 150 ms** | Camera sensor capture to HTTP frame read. |

### 2.3 Frame Dropping & Buffering
- **Zero-Backlog Rule:** The ESP32-CAM HTTP task must **drop older unserved frames** when the Wi-Fi transmission socket is full. It must never buffer stale frames in PSRAM, as delivery delay is hazardous to a visually impaired user.
- **Software Pipeline Decoupling:** The Vision Engine's `PerceptionPipeline` maintains a bounded capacity-1 queue slot. Fresh frames immediately overwrite unconsumed frames in $O(1)$ time.

---

## 3. Device Telemetry & Health Monitoring

### 3.1 Optional Telemetry Endpoint (Recommended on ESP32-CAM)
- **Endpoint:** `GET http://<ESP32_IP>:80/status`
- **Response Format:** `application/json`
- **Schema:**
  ```json
  {
    "device_id": "trinetra-node-01",
    "hardware_rev": "ESP32-CAM-AI-THINKER",
    "firmware_version": "1.0.0",
    "battery_mv": 3950,
    "battery_pct": 82,
    "wifi_rssi_dbm": -58,
    "stream_fps": 19.4,
    "uptime_seconds": 3600,
    "free_psram_bytes": 3912440
  }
  ```

### 3.2 Software Sensor Health Diagnostics
The Vision Engine continuously evaluates frame health in [`services/vision-engine/app/camera/sensor_health.py`](file:///d:/trinetra/services/vision-engine/app/camera/sensor_health.py). The hardware must satisfy the following thresholds to avoid triggering sensor degradation alarms:

| Failure Mode | Detection Criteria in Software | Hardware Remediation |
| :--- | :--- | :--- |
| **Total Darkness** | Mean pixel brightness $< 15.0$ ($[0, 255]$) | Adequate environmental illumination or auxiliary IR/white LED. |
| **Severe Glare** | Bright saturated pixels $> 35\%$ of frame area | Enable sensor Automatic Exposure Control (AEC) and Gain Control (AGC). |
| **Extreme Blur** | Laplacian variance $< 45.0$ | Calibrate lens focal ring for 1.5m to 5.0m focus; clean lens surface. |
| **Stream Freeze** | Identical frame diffs for $> 1.5$ seconds | ESP32-CAM DMA watchdogs preventing frame buffer lockup. |
| **Packet Loss** | Frame inter-arrival gap $> 2.0$ seconds | Maintain stable Wi-Fi RSSI ($> -70$ dBm) and low jitter. |

---

## 4. Software Detection Event Contracts

The Vision Engine processes ingested camera frames and produces structured detection payloads conforming to the following verified contract ([`apps/desktop/src/types/api.ts`](file:///d:/trinetra/apps/desktop/src/types/api.ts)):

```json
{
  "frame_id": 481,
  "timestamp": 1729094400.124,
  "detections": [
    {
      "class_name": "person",
      "confidence": 0.88,
      "box": {
        "x_min": 180.5,
        "y_min": 64.0,
        "x_max": 390.2,
        "y_max": 420.0
      },
      "sector": "center"
    },
    {
      "class_name": "chair",
      "confidence": 0.74,
      "box": {
        "x_min": 410.0,
        "y_min": 250.0,
        "x_max": 590.0,
        "y_max": 470.0
      },
      "sector": "right"
    }
  ],
  "inference_time_ms": 23.4,
  "e2e_latency_ms": 36.1,
  "runtime": "onnxruntime_cpu",
  "active_model": "yolox_nano.onnx"
}
```

### Sector Spatial Mapping
- **`left`**: Normalized $x_{center} \in [0.0, 0.33)$
- **`center`**: Normalized $x_{center} \in [0.33, 0.66]$
- **`right`**: Normalized $x_{center} \in (0.66, 1.0]$

---

## 5. Connection State Machine

The camera connection lifecycle follows a deterministic 5-state machine implemented in [`services/vision-engine/app/camera/adapter.py`](file:///d:/trinetra/services/vision-engine/app/camera/adapter.py):

```
                     +-------------------+
                     |   DISCONNECTED    |
                     +-------------------+
                               |
                        start_capture()
                               v
                     +-------------------+
            +------->|    CONNECTING     |
            |        +-------------------+
            |                  |
            |            Success / Ready
            |                  v
            |        +-------------------+
            |        |     CONNECTED     |
            |        +-------------------+
     Backoff Fail              |
            |            Frame Drop / EOF
            |                  v
            |        +-------------------+
            +--------|   RECONNECTING    |
                     +-------------------+
                               |
                    Max Retries Exceeded (5)
                               v
                     +-------------------+
                     |       ERROR       |
                     +-------------------+
```

- **Reconnection Schedule:** 5 maximum attempts with progressive exponential backoff (0.5s, 1.0s, 2.0s, 4.0s, 8.0s).
- **Session Preservation:** Active session tokens and UI state remain persistent across transient network interruptions.

---

## 6. Power & Thermal Hardware Specifications

| Characteristic | Nominal Requirement | Failure Condition |
| :--- | :--- | :--- |
| **Input Rail Voltage** | $5.0\text{V} \pm 5\%$ ($4.75\text{V} - 5.25\text{V}$) | Drops below $4.5\text{V}$ trigger ESP32 brownout reset. |
| **Continuous Current** | $250\text{ mA}$ average | Subsystem unable to sustain continuous streaming. |
| **Peak Transient Current** | $500\text{ mA}$ (Wi-Fi RF pulses) | Voltage rail sag causing camera sensor artifacts. |
| **Battery Chemistry** | $3.7\text{V}$ Li-Ion (18650) / Li-Po | Operating below $3.0\text{V}$ damages cells without BMS protection. |
| **Battery Capacity** | $\ge 2600\text{ mAh}$ | Runtime $< 3$ hours unacceptable for field mobility. |
| **Max Enclosure Temp** | $\le 45^\circ\text{C}$ exterior | User discomfort or thermal throttling of OV2640 sensor. |

---

## 7. Audio Feedback & Speech Integration

When hazards or obstacles are identified from camera frames, the bilingual audio engine in [`services/vision-engine/app/audio/`](file:///d:/trinetra/services/vision-engine/app/audio/) produces voice alerts according to priority:

| Priority Level | Example Nepali Event | Example English Event | Audio Preemption |
| :--- | :--- | :--- | :--- |
| **CRITICAL (0)** | "सावधान! अगाडि अवरोध छ।" | "Warning! Immediate obstacle ahead." | **Instant Preemption** (Stops all speech immediately) |
| **HIGH (1)** | "अगाडि गाडी नजिकिँदै छ।" | "Car approaching in center." | Interrupts normal queue |
| **NORMAL (2)** | "अगाडि मान्छे छ।" | "Person ahead." | Enqueued in FIFO queue |
| **LOW (3)** | "बत्ती धेरै मधुरो छ।" | "Lighting is too low." | Enqueued; dropped if stale |

---

## 8. Pending Architectural Decisions

The following specifications are tracked as pending decisions between Developer 1 and Developer 2:

- [ ] **DECISION-01:** Should ESP32-CAM operate in **SoftAP Mode** (ESP32 acts as Wi-Fi router) or **Station Mode** (both connect to a mobile hotspot) for field usage?
  - *Current Status:* Software supports any IP address via URL input; Station mode is used in testing.
- [ ] **DECISION-02:** Inclusion of physical hardware push-button on chest rig for "Describe Scene" snapshot command.
  - *Current Status:* Pending mechanical prototype design.
- [ ] **DECISION-03:** Direct Serial UART telemetry vs. pure Wi-Fi HTTP telemetry.
  - *Current Status:* Wi-Fi HTTP stream is primary; UART is reserved for flashing/bench debugging.
