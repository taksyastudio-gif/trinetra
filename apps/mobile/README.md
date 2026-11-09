# TRINETRA Mobile (Android Edge Compute Platform)

## 1. Executive Summary & Purpose

Trinetra Mobile represents the highest-priority architectural milestone identified in the external technical audits. Moving real-time compute from a laptop backpack to a **chest-mounted Android smartphone** collapses the entire hardware stack into a single, ubiquitous, self-powered edge device:

| Hardware Component | Laptop + ESP32 Stack | Trinetra Android Edge Stack |
| :--- | :--- | :--- |
| **Compute Engine** | Laptop (Intel Core i5, 2.5 kg backpack) | Smartphone SoC (MediaTek Helio / Snapdragon, 180g) |
| **Vision Input** | ESP32-CAM via 2.4GHz Wi-Fi MJPEG (60–150ms jitter) | Native CameraX zero-copy sensor buffer (<16ms) |
| **Acoustic Feedback** | Laptop speaker or Bluetooth earbuds | Phone loudspeaker (85dB+) or bone-conduction headset |
| **Haptic Feedback** | Requires separate vibrating wearable | Built-in smartphone linear resonance haptic motor |
| **Emergency SOS** | Requires separate GSM modem or PC tether | Built-in native Android `SmsManager` over 2G/4G/5G |
| **Location & Orientation**| External GPS module or manual entry | Built-in high-rate GPS + 6-DOF IMU + Compass |
| **Battery Life & Weight** | Laptop battery (~2.5 hrs, heavy) | 5000 mAh internal phone battery (6–8 hrs continuous) |
| **Cost** | Laptop ($400+) + ESP32 ($10) = $410+ | Budget Android phone ($90–$140 refurbished/new) |

---

## 2. System Architecture & Component Mapping

```
                       [ Chest Mount Harness ]
                                 │
                   ┌─────────────┴─────────────┐
                   │  Trinetra Android Core    │
                   │  (Kotlin / C++ / NDK)     │
                   └─────────────┬─────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
   [ CameraX ]            [ Sensor Fusion ]       [ Native Telephony ]
  Zero-copy YUV           Authoritative Veto        Offline GSM SMS
  640x480 @ 30fps         Simplex Architecture    (Zero Cloud Gateway)
         │                       │                       │
         ▼                       ▲                       ▼
  [ ONNX Runtime ]               │               [ Caretaker Phone ]
  INT8 Quantized                 │               Lat, Lon, Battery, Time
  YOLOv8 + Ground                │
         │                       │
         └───────────┬───────────┘
                     │
         [ BLE GATT Central ]
                     │ (2.4 GHz Low Energy)
                     ▼
       ┌───────────────────────────┐
       │     Smart Cane MCU        │
       │  - Forward Ultrasonic     │
       │  - Downward ToF LiDAR     │
       │  - MPU6050 IMU Tap Sense  │
       └───────────────────────────┘
```

---

## 3. High-Reliability Safety Invariants

1. **Supplements Your Cane**:
   The mobile application prominently displays and audibly affirms on every launch:
   > *"त्रिनेत्र तपाईंको सेतो छडीको सहयोगी मात्र हो; छडी सधैं प्रयोग गर्नुहोस्।"*
   *(Trinetra supplements your white cane; always use your cane).*

2. **Zero False Confidence Guarantee (Simplex Safety Architecture)**:
   Optical neural networks are **advisory**. Physical ranging sensors on the cane (downward ToF LiDAR and forward ultrasonic) have **strict veto power** over optimistic vision output. If physical range detects an obstacle `<90cm` or a ground drop `>12cm`, an emergency audio/haptic alert fires immediately, ignoring vision clearance.

3. **Frame Freshness Deadline (<150ms)**:
   Frames older than 150ms from exposure are dropped immediately. Capacity-1 bounded buffer ensures zero frame queuing and zero latency drift.

4. **Watchdog Heartbeat Tone**:
   A subtle 320Hz 20ms sine pulse sounds every 2.5 seconds to confirm that the vision pipeline is actively inspecting frames. If frame processing stalls for $>800\text{ms}$, a loud multi-tone siren sounds: *"क्यामेरा रोकियो, होसियार!"*.

5. **Offline SMS Caretaker Alert**:
   On 10-second emergency countdown expiration (or manual SOS / severe fall detection), the app transmits an offline GSM SMS with GPS coordinates and battery telemetry directly to designated family contacts.
