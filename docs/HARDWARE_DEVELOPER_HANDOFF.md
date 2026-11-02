# TRINETRA — Hardware Developer Handoff & Prototyping Guide

**Target Audience:** Developer 2 (Physical Hardware, ESP32-CAM, Electronics, Power & Prototyping)  
**Lead Software Developer:** Developer 1 (Vision Engine, AI Detection, Audio Assistance, Tauri Desktop App)  
**Repository:** `trinetra` (Private GitHub Repository)  
**Hardware Branch:** `dev/hardware`  
**Status Date:** November 2026  

---

## 1. What TRINETRA Is

**TRINETRA** (meaning *"The Third Eye"*) is an assistive spatial awareness and hazard detection platform designed for blind and visually impaired individuals. The platform operates on a **local-first, zero-cloud architecture**: all computer vision inference, depth/obstacle reasoning, and voice announcements occur locally without internet connectivity or external cloud egress.

The system empowers the user by continuously scanning their immediate frontal environment, identifying potential obstacles, people, vehicles, and navigation hazards, and relaying real-time auditory guidance through an intelligent, prioritized bilingual speech engine (Nepali and English).

---

## 2. Overall Architecture: Software & Hardware Collaboration

The complete TRINETRA platform consists of two cooperative halves:

```
+-----------------------------------------------------------------------------------+
|                        PHYSICAL HARDWARE (Developer 2)                            |
|                                                                                   |
|  [Li-Ion Battery] ---> [Power Management (TP4056 + 5V Boost)]                    |
|                                    |                                              |
|                                    v                                              |
|                           [ESP32-CAM / OV2640]                                    |
|                      (Chest-Mounted Wearable Rig)                                 |
|                                    |                                              |
|                   Wi-Fi 802.11 b/g/n (Local LAN / SoftAP)                         |
|                   HTTP MJPEG Video Stream (Port 81)                               |
+-----------------------------------------------------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------------+
|                        SOFTWARE PLATFORM (Developer 1)                            |
|                                                                                   |
|  [Tauri 2 + React 18 Desktop App] <--(IPC)--> [Rust Supervisor (supervisor.rs)]  |
|                                                      | Spawns & Ephemeral Token   |
|                                                      v Handshake                  |
|  [FastAPI Vision Engine (127.0.0.1:8000)]                                          |
|    |-- CameraAdapter (DirectShow USB or Network Stream from ESP32-CAM)            |
|    |-- SensorHealthController (Darkness, Blur, Freeze, Glare, Packet Loss)        |
|    |-- PerceptionPipeline (YOLOX-Nano ONNX CPU, YuNet Face, Kalman Filter)        |
|    `-- Bilingual Audio Engine (Piper Neural TTS for Nepali + Windows SAPI for EN) |
+-----------------------------------------------------------------------------------+
```

---

## 3. Existing Integration Status: Verified vs. Planned

To prevent assumptions, all capabilities are classified below by their verified status:

### Verified Existing Functionality (Software Side)
- **Network Stream Ingestion:** [`services/vision-engine/app/camera/adapter.py`](file:///d:/trinetra/services/vision-engine/app/camera/adapter.py) natively supports string network URLs (e.g., `http://192.168.1.100:81/stream`) via OpenCV `cv2.VideoCapture`.
- **UI Device Selector:** [`apps/desktop/src/components/DeviceSelector.tsx`](file:///d:/trinetra/apps/desktop/src/components/DeviceSelector.tsx) features a dedicated **📡 Network Stream (ESP32-CAM)** tab where the user can enter or modify the ESP32-CAM stream URL.
- **Connection State Machine:** The software handles states (`DISCONNECTED`, `CONNECTING`, `CONNECTED`, `RECONNECTING`, `ERROR`) with exponential backoff and automatic stream reconnection if the Wi-Fi or camera drops.
- **Sensor Health Controller:** Detects camera glare, severe underexposure (darkness), lens obstruction, and frozen streams.
- **On-Device Object Detection:** Real-time YOLOX-Nano ONNX model running on CPU at ~23ms per frame.
- **Prioritized Bilingual Speech:** Asynchronous audio queue delivering critical hazard announcements with instant preemption.

### Planned Hardware Functionality (Developer 2 Scope)
- **Dedicated ESP32-CAM Firmware:** Stable Arduino C++ or ESP-IDF firmware hosting a resilient HTTP MJPEG video stream.
- **Standalone Battery Subsystem:** 18650 or Li-Po battery with charging circuit, low-voltage cutoff, and stable 5V rail.
- **Chest Mount & Wearable Enclosure:** 3D-printed or physical rig with thermal ventilation, lens opening, and secure body harness.
- **Direct Wi-Fi Link:** Dedicated SoftAP or auto-connecting Station mode connecting the ESP32-CAM to the laptop/compute device.
- **Rangefinder Sensors (Future Phase):** Ultrasonic (HC-SR04) or Time-of-Flight (VL53L0X) rangefinders over UART/I2C.

---

## 4. Camera & Video Stream Requirements

The Vision Engine ingests frames using OpenCV's `VideoCapture`. The ESP32-CAM stream must comply with the following parameters:

| Parameter | Specification | Rational & Tolerance |
| :--- | :--- | :--- |
| **Protocol** | HTTP MJPEG (Multipart) | `multipart/x-mixed-replace; boundary=frame` |
| **Default Port** | `81` (or `80`) | e.g. `http://<ESP32_IP>:81/stream` |
| **Resolution** | **VGA (640x480)** or **QVGA (320x240)** | VGA is optimal for object detection. QVGA can be used in low-power modes. |
| **Frame Rate** | **15 – 25 FPS** | Stable 15 FPS minimum. Perception pipeline samples frames non-blockingly. |
| **JPEG Quality** | `10 – 15` (OV2640 scale) | Lower numbers indicate higher quality. 12 provides good balance between compression and artifacting. |
| **Pixel Format** | JPEG / YUV from sensor | Standard compressed JPEG stream to minimize Wi-Fi bandwidth (< 2 Mbps). |
| **Frame Dropping** | Latest frame priority | ESP32 must discard old frames rather than buffering backlog if transmission lags. |

---

## 5. Battery & Power Subsystem Requirements

The chest-mounted wearable must operate autonomously without requiring tethered power:

1. **Operating Voltage:** ESP32-CAM core runs at 3.3V, but the standard AI-Thinker board requires **5V DC** input into its onboard LDO (AMS1117-3.3) for reliable camera sensor operation and PSRAM stability.
2. **Current Draw:**
   - Active Wi-Fi transmission + OV2640 streaming: **180 mA – 310 mA** with periodic peaks up to **500 mA** during Wi-Fi transmission bursts.
   - Brownout Sensitivity: Insufficient peak current causes ESP32 brownout resets (`Brownout detector was triggered`).
3. **Power Architecture:**
   - **Battery Cell:** Single 18650 Li-Ion cell (3.7V nominal, 2600–3500 mAh) or 3.7V 2000mAh+ Li-Po pouch.
   - **Protection & Charging:** TP4056 charging module with battery protection IC (overcharge, overdischarge cutoff at 2.8V).
   - **Step-Up Boost Converter:** High-efficiency 5V synchronous boost regulator capable of delivering at least **1.0A continuous output**.
   - **Target Runtime:** Minimum **3 to 4 hours** continuous streaming per charge.
4. **Thermal Dissipation:**
   - The ESP32 RF chip and camera module generate noticeable heat during continuous streaming.
   - The enclosure must include ventilation slots or heat-spreading pads to prevent thermal throttling or user discomfort when worn on the chest.

---

## 6. ESP32 Communication Expectations

### Endpoints on ESP32-CAM
1. `GET /stream` (Mandatory): Returns continuous `multipart/x-mixed-replace` MJPEG video.
2. `GET /capture` (Optional/Recommended): Returns a single instantaneous JPEG snapshot.
3. `GET /status` (Recommended): Returns simple JSON status:
   ```json
   {
     "device": "trinetra-cam-01",
     "firmware": "1.0.0",
     "battery_mv": 3950,
     "wifi_rssi": -55,
     "fps": 18.2,
     "uptime_s": 1420
   }
   ```

### Networking Modes
- **Station Mode (Recommended for testing):** ESP32 connects to existing home/lab Wi-Fi router. Laptop connects to the same router.
- **Access Point (AP) Mode (Field operation):** ESP32 creates its own Wi-Fi AP (e.g., `TRINETRA-NODE`, password-protected). Laptop or mobile device joins this AP.

---

## 7. Chest-Mounted Prototype Objectives

The wearable unit will be worn on the user's upper torso/chest:
- **Mounting Angle:** Fixed 90-degree frontal view with a slight downward inclination (~5 degrees) to capture both ground obstacles (potholes, steps) and chest-height hazards (branches, doors).
- **Physical Stability:** Elastic chest harness or clip mount preventing camera rotation or tilt swing while walking.
- **Weight Target:** Under 150 grams total (including battery and housing).
- **Material:** 3D printed PETG or ABS recommended (PLA softens under prolonged direct sunlight or body heat).

---

## 8. Hardware / Software Integration Boundaries

| Responsibility Area | Software Developer (Dev 1) | Hardware Developer (Dev 2) |
| :--- | :--- | :--- |
| **Firmware Code** | Reviews interface contracts | Owns & writes in `hardware/firmware/` |
| **Circuit Design & Schematics** | Reviews power requirements | Owns & writes in `hardware/schematics/` |
| **Camera Ingestion** | Owns `services/vision-engine/app/camera/` | Verifies stream compatibility with OpenCV |
| **Object Detection & Models** | Owns `app/detection/` & ONNX models | Ingests feedback on frame clarity/quality |
| **Sensor Health Detection** | Alerts on blur/glare/frozen frame | Adjusts lens focus, exposure, and lighting |
| **Desktop Application** | Owns React/Tauri frontend & supervisor | Tests UI device selection against hardware |

---

## 9. Current Known Limitations & Traps

1. **Wi-Fi Latency & Jitter:** In high-interference environments, MJPEG streaming over 2.4 GHz Wi-Fi can suffer packet drop or latency spikes. Firmware must drop stale frames rather than queueing.
2. **ESP32-CAM Lens Focus:** Most stock OV2640 camera modules come with manual screw-threaded focus locked with glue. Developer 2 should gently break the glue ring and calibrate focus for **1.0 to 5.0 meters** distance (rather than macro 10 cm).
3. **Brownout Resets:** If the 5V power supply drops below 4.5V under Wi-Fi transmit bursts, the ESP32 resets. Add a 470uF to 1000uF low-ESR electrolytic capacitor across the 5V and GND rail on the hardware board.
4. **Lighting Sensitivity:** OV2640 has limited dynamic range. Moving from bright daylight to indoor corridors triggers sensor health glare/darkness alerts. Hardware automatic gain control (AGC) and automatic white balance (AWB) should be enabled in the camera initialization code.

---

## 10. Hardware Testing Procedures

Before declaring hardware ready for full software integration:

1. **Power & Burn-in Test:**
   - Power the ESP32-CAM from the battery and boost converter.
   - Run stream continuously for 2 hours.
   - Measure battery voltage drop and ensure no brownout resets occur.
2. **Stream Latency Probe:**
   - Open the stream in a browser or VLC: `http://<IP>:81/stream`.
   - Point the camera at a millisecond digital stopwatch running on the computer screen. Take a photo of both screens to compute glass-to-glass latency (target: `< 150 ms`).
3. **Integration Test with Vision Engine:**
   - In `apps/desktop`, navigate to the **Device Selector**.
   - Switch to **📡 Network Stream (ESP32-CAM)**.
   - Enter `http://<IP>:81/stream` and click **Apply Stream URL**.
   - Start Camera in TRINETRA. Verify that bounding boxes appear around detected persons and objects in real-time.

---

## 11. Required Development Tools

For Developer 2's remote workstation:
- **Arduino IDE 2.x** or **VS Code + PlatformIO**
- **ESP32 Board Support Package** (Espressif v2.0.x or v3.0.x)
- **USB-to-Serial TTL Programmer** (FTDI FT232RL or CP2102) with 3.3V/5V selector
- **Multimeter** (for measuring 5V rail stability and battery voltage)
- **Soldering Station & Jumper Wires**
- **Git** for Windows/Linux/macOS
- **Node.js 18+ & Python 3.10–3.13** (to run the local desktop app and test stream integration)

---

## 12. How to Clone & Configure the Project

```powershell
# 1. Clone the private repository
git clone https://github.com/taksyastudio-gif/trinetra.git
cd trinetra

# 2. Switch to the dedicated hardware branch
git checkout dev/hardware

# 3. Pull latest changes
git pull origin dev/hardware
```

---

## 13. Branch Workflow & Collaboration Rules

1. **Never Commit to `master` Directly:** `master` represents production-ready code.
2. **Hardware Development Branch:** Developer 2 works exclusively on `dev/hardware` (or feature branches branched off it, e.g. `feature/esp32-mjpeg-firmware`).
3. **Pull Before Work:** Always execute `git pull` before starting new edits.
4. **Scope Isolation:**
   - Commit firmware code into `hardware/firmware/`.
   - Commit schematics and pinouts into `hardware/schematics/`.
   - Commit hardware test notes into `hardware/docs/`.
   - Do not modify core software files in `services/vision-engine/` or `apps/desktop/` without coordinating with Developer 1.
5. **No Destructive Operations:** Never run `git reset --hard` or `git push --force`.
6. **Submitting Changes:**
   - Push your branch: `git push origin dev/hardware`.
   - Open a Pull Request on GitHub targeting `integration`.
   - Developer 1 will review the PR, verify integration, and merge into `integration` and then `master`.
