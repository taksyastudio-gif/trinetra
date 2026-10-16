# Trinetra System Architecture (Sprint 1)

## 1. Overview

Trinetra is an assistive vision and navigation system designed for blind and visually impaired individuals. Sprint 1 focuses strictly on establishing a solid, reliable, and testable foundation: a desktop client interface communicating with an isolated local vision engine over loopback HTTP to control a camera pipeline.

```
+-------------------------------------------------------------------------+
|                              Desktop Host                                |
|                                                                         |
|  +---------------------------+        +------------------------------+  |
|  |     React + TypeScript    |        |        Tauri 2 Rust Core     |  |
|  |       (Accessible UI)     |<------>|     (Window & Webview host)  |  |
|  +-------------+-------------+        +------------------------------+  |
|                |                                                        |
|                | HTTP polling / REST commands                           |
|                | (http://127.0.0.1:8000)                                |
|                v                                                        |
|  +-------------------------------------------------------------------+  |
|  |                    Python Vision Engine (FastAPI)                 |  |
|  |                                                                   |  |
|  |   [REST Endpoints: /api/health, /api/camera/status, start, stop]   |  |
|  |                               |                                   |  |
|  |                               v                                   |  |
|  |                   CameraAdapter Interface                         |  |
|  |                     /                 \                           |  |
|  |                    v                   v                          |  |
|  |           OpenCVCameraAdapter     FakeCameraAdapter (Unit Tests)  |  |
|  |                    |                                              |  |
|  |                    v                                              |  |
|  |             Hardware Webcam                                       |  |
|  +-------------------------------------------------------------------+  |
+-------------------------------------------------------------------------+
```

## 2. Component Decoupling & Principles

### A. Desktop Interface (`apps/desktop`)
- **Technology:** React 19 / 18, TypeScript (strict mode), Vite, Tauri 2.
- **Responsibility:** Accessible user interface, high-contrast controls, keyboard navigation (tabbing, aria tags, screen reader live regions), camera state presentation, and frame rendering.
- **Independence:** The UI knows nothing about OpenCV, video capture libraries, or camera drivers. It communicates exclusively via a typed HTTP service (`services/cameraApi.ts`).

### B. Vision Engine (`services/vision-engine`)
- **Technology:** Python 3.11+, FastAPI, Uvicorn, OpenCV (`opencv-python`), Pytest.
- **Responsibility:** Ingesting video frames from camera hardware, managing camera lifecycle (open, capture, release), and serving status and encoded JPEG frames over loopback HTTP (`127.0.0.1:8000`).
- **Safety & Concurrency:** Thread-safe state synchronization prevents race conditions during concurrent start/stop requests.

### C. Camera Adapter Abstraction (`CameraAdapter`)
- An abstract base class (`app.camera.adapter.CameraAdapter`) decouples the API from underlying camera drivers.
- **OpenCVCameraAdapter:** Wraps physical webcam access via OpenCV `cv2.VideoCapture`.
- **FakeCameraAdapter:** Generates controlled test frames for automated CI/CD unit testing without requiring physical camera hardware.
- **Future Extensibility:** Facilitates future addition of CSI cameras (Raspberry Pi), USB UVC cameras, RTSP streams, or wearable sensor rigs without rewriting endpoints or client UI.

### D. Hardware & Contracts (`packages/contracts`, `hardware/adapters`)
- Future contracts for data serialization, perception results, and hardware interfaces are decoupled into dedicated packages.
