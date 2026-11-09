# Trinetra Hardware Adapters & Wearable Specifications

Trinetra is designed to run decoupled from the physical camera. Any optical capture device capable of streaming frames—internal UVC webcams, wearable USB cameras, or wireless ESP32-CAM microcontrollers—connects into the unified vision pipeline via `app.camera.adapter`.

---

## 1. Supported Input Interfaces

| Hardware Type | Connection Protocol | Adapter Implementation | Primary Deployment Scenario |
| :--- | :--- | :--- | :--- |
| **Internal / USB Webcam** | DirectShow / V4L2 / UVC | `NativeCameraAdapter` | Testing, desk station, classroom demonstration |
| **ESP32-CAM Smart Glasses** | HTTP MJPEG (`http://<ip>:81/stream`) | `MJPEGStreamCameraAdapter` | Ultra-lightweight glasses side-mount (first-person FOV) |
| **Smart White Cane Rig** | HTTP MJPEG or USB OTG | `MJPEGStreamCameraAdapter` | Ground hazard detection (potholes, open drains, curbs) |
| **Chest Harness Mount** | HTTP MJPEG or USB UVC | `MJPEGStreamCameraAdapter` | High-stability urban pedestrian navigation |
| **Simulated Test Rig** | HTTP MJPEG (`http://127.0.0.1:81/stream`) | `MJPEGStreamCameraAdapter` | Headless CI/CD, mock obstacle testing without physical hardware |

---

## 2. Smart Glasses Mounting Specifications

```
                     +-----------------------------+
                     |   3D-Printed Temple Clip    |
                     +--------------+--------------+
                                    |
  +---------------------------------+---------------------------------+
  |                                                                   |
  v                                                                   v
+-----------------------+                             +-------------------------------+
| ESP32-CAM (AI-Thinker)|                             | Power Cable (Micro-USB / 2-Pin)|
| - OV2640 120° Lens    |                             | To neck lanyard battery pack  |
| - Dimensions: 40x27mm |                             | (3.7V Li-Po or 5V Power Bank) |
| - Weight: ~10 grams   |                             +-------------------------------+
+-----------------------+
```

### Mechanical Guidelines
1. **Target Weight**: Keep head-mounted weight under **35 grams** to avoid neck strain.
2. **Mounting Location**: Right temple arm of standard prescription or safety frames.
3. **Lens Selection**: Use an **OV2640 with a 120° or 160° Wide-Angle Fisheye Lens** (M12 mount) to ensure full peripheral coverage of oncoming vehicles and pedestrians.
4. **Thermal Dissipation**: ESP32-CAM running continuous JPEG streaming dissipates ~1.2W. Provide passive airflow slots in the 3D enclosure.
5. **Vibration Damping**: Use silicone padding between the frame clamp and glasses temple arm to isolate micro-vibrations from walking footfalls.

---

## 3. White Cane Ground-Hazard Rig

```
     White Cane Shaft
          |
          |  [15° Forward-Downward Tilt]
          +----[\\]----+  Vibration-Damped Clamp
               |  ||   |
               |  ++   |  ESP32-CAM + VL53L0X Time-of-Flight LiDAR
               +-------+
                  |
                  v  Sweeping 1.5m - 3.0m in front of walking path
              [Potholes / Open Drains / Curbs / Dhukuti Steps]
```

### Cane Configuration
- **Tilt Angle**: 15 degrees downward relative to cane shaft axis. When the cane is held at a standard 45-degree walking posture, the camera aims directly at the ground 2 to 3 meters ahead.
- **Hazards Detected**: Broken flagstones, uncovered sewer manholes, puddle depths, Kathmandu open drainage ditches (*dhukuti*), and abrupt curbs.
- **Sensor Fusion**: Integrates with onboard `GroundHazardDetector` in `services/vision-engine/app/detection/ground_hazard.py`.

---

## 4. Connecting ESP32-CAM to Trinetra

### Option A: Local WiFi Hotspot (Recommended for Outdoor Mobility)
1. Turn on personal hotspot on mobile phone or portable LTE router:
   - SSID: `Trinetra-Field`
   - Password: `assistivevision`
2. Flash ESP32-CAM with `USE_STATION_MODE 1` matching the hotspot SSID.
3. ESP32-CAM automatically associates and obtains an IP address (e.g., `192.168.43.120`).
4. In Trinetra Desktop Settings (or `.env`):
   ```bash
   CAMERA_STREAM_URL=http://192.168.43.120:81/stream
   ```
5. Trinetra launches the bounded, low-latency streaming pipeline automatically.

### Option B: SoftAP Mode (Zero-Infrastructure Field Setup)
1. Flash firmware with `USE_STATION_MODE 0`.
2. ESP32-CAM creates its own WiFi network:
   - SSID: `Trinetra-ChestCam`
   - Password: `trinetra123`
3. Connect your laptop or processing device directly to `Trinetra-ChestCam`.
4. Point Trinetra to default gateway:
   ```bash
   CAMERA_STREAM_URL=http://192.168.4.1:81/stream
   ```

---

## 5. Software Simulation for Development

When physical ESP32 hardware is not at hand, run the included software simulator:

```powershell
# Launch synthetic obstacle streaming rig on port 81
python tools/simulate_esp32_stream.py --port 81 --source synth
```

Verify the stream in your browser at `http://127.0.0.1:81/stream` or check health telemetry at `http://127.0.0.1:81/status`.
