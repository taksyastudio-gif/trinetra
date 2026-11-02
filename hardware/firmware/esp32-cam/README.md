# TRINETRA ESP32-CAM Firmware

This directory is designated for Developer 2's ESP32-CAM firmware implementations (Arduino C++ or ESP-IDF).

## Target Hardware Specifications
- **Module:** AI-Thinker ESP32-CAM (or ESP32-S3-CAM)
- **Camera Sensor:** OV2640 (2 Megapixel)
- **PSRAM:** 4MB external PSRAM (required for stable UXGA/SVGA/VGA streaming)
- **Power:** 5V DC via external regulated buck converter or USB FTDI programmer

## Firmware Responsibilities
1. Initialize OV2640 sensor with appropriate frame size (VGA `640x480` or QVGA `320x240`) and JPEG quality (10-12).
2. Connect to local Wi-Fi network (AP or Station mode).
3. Host an HTTP MJPEG video stream on port 81 (e.g. `http://<device-ip>:81/stream`).
4. Support HTTP GET `/status` or `/health` for heartbeat monitoring.
5. Provide low-latency, non-blocking frame delivery without buffer drift.
