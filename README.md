# TRINETRA (त्रिनेत्र) — Assistive Vision & Navigation Platform
## Sprint 1: Core Foundation & Webcam Capture Pipeline

**Trinetra** is an assistive computer-vision system designed to empower blind and visually impaired individuals with real-time awareness of their physical surroundings through auditory feedback, spatial reasoning, and obstacle detection.

> ⚠️ **CRITICAL SAFETY DISCLAIMER**: Trinetra is an experimental assistive technology research prototype. It is **NOT** a certified medical device, protective equipment, or mobility aid. It **must never replace** a white cane, guide dog, orientation and mobility (O&M) training, or human sighted guides.

---

## 🏛 System Architecture (Sprint 1)

Sprint 1 establishes a modular, local-first client-server foundation:

```
+-------------------------------------------------------------------------+
|                               HOST COMPUTER                             |
|                                                                         |
|  +---------------------------+        +------------------------------+  |
|  |    React + TypeScript     |        |      Tauri 2 (Rust Host)     |  |
|  |     (Accessible UI)       |<------>|     (Windows Webview Host)   |  |
|  +-------------+-------------+        +------------------------------+  |
|                |                                                        |
|                | Loopback REST Polling (http://127.0.0.1:8000)          |
|                v                                                        |
|  +-------------------------------------------------------------------+  |
|  |                 Python Vision Engine (FastAPI)                    |  |
|  |                                                                   |  |
|  |   [Endpoints: /api/health, /api/camera/status, start, stop, frame]|  |
|  |                               |                                   |  |
|  |                               v                                   |  |
|  |                    CameraAdapter Interface                        |  |
|  |                     /                 \                           |  |
|  |                    v                   v                          |  |
|  |           OpenCVCameraAdapter     FakeCameraAdapter (Unit Tests)  |  |
|  |                    |                                              |  |
|  |                    v                                              |  |
|  |             Physical Webcam                                       |  |
|  +-------------------------------------------------------------------+  |
+-------------------------------------------------------------------------+
```

### Modular Directory Structure
```text
Trinetra/
├── apps/
│   └── desktop/                   # Desktop UI Application
│       ├── src/
│       │   ├── components/        # Accessible React components (Header, Preview, Status, Notices)
│       │   ├── services/          # Typed API service (cameraApi.ts)
│       │   ├── types/             # TypeScript contracts (api.ts)
│       │   ├── App.tsx            # Main state & frame polling loop
│       │   ├── index.css          # High-contrast accessible styling (WCAG 2.1 AAA)
│       │   └── main.tsx           # React entry point
│       ├── src-tauri/             # Tauri 2 Rust desktop host
│       │   ├── capabilities/      # Least-privilege permissions
│       │   ├── icons/             # Windows application icons
│       │   ├── src/               # Rust entry point (lib.rs, main.rs)
│       │   ├── Cargo.toml         # Rust crate manifest
│       │   └── tauri.conf.json    # Tauri 2 configuration
│       ├── package.json           # Frontend dependencies (React, Vite, Tauri CLI)
│       ├── tsconfig.json          # Strict TypeScript configuration
│       └── vite.config.ts         # Vite bundler configuration
├── services/
│   └── vision-engine/             # Local Python Vision Engine
│       ├── app/
│       │   ├── camera/
│       │   │   ├── __init__.py
│       │   │   └── adapter.py     # CameraAdapter, OpenCVCameraAdapter, FakeCameraAdapter
│       │   ├── __init__.py
│       │   └── main.py            # FastAPI service (bound to 127.0.0.1)
│       ├── tests/
│       │   └── test_api.py        # 9 automated unit tests (zero-hardware FakeCameraAdapter)
│       └── pyproject.toml         # Python service dependencies
├── packages/
│   └── contracts/                 # Shared data contracts and schemas
├── hardware/
│   └── adapters/                  # Hardware specifications and sensor pinouts
├── docs/
│   ├── ARCHITECTURE.md            # System design and component decoupling
│   ├── PRIVACY.md                 # Local-first privacy guarantees
│   └── SAFETY.md                  # Critical safety disclaimers
├── .gitignore                     # Git ignore rules
└── README.md                      # This document
```

---

## 🔒 Privacy & Accessibility Guarantees

1. **Local-First & Zero Cloud Uploads**: The Vision Engine binds strictly to loopback IP `127.0.0.1`. Video frames are retained purely in volatile RAM as JPEG buffers. No frames or recordings are written to disk or sent across networks.
2. **Explicit User Activation**: The webcam is **never** turned on automatically. Capture begins only when the user explicitly triggers the **Start Camera** button.
3. **Accessibility First (WCAG 2.1 AAA)**:
   - High-contrast visual palette with zero visual clutter.
   - Screen-reader friendly announcements via `aria-live="polite"` and `aria-live="assertive"` regions.
   - 100% keyboard navigable with high-visibility `:focus-visible` outlines (3px solid cyan).
   - Generous button tap targets (minimum 48px height).

---

## 🛠 Prerequisites for Windows

| Tool | Minimum Version | Verified on System |
| :--- | :--- | :--- |
| **Git** | 2.30+ | `2.55.0` |
| **Node.js** | 18+ or 20+ | `v24.17.0` |
| **npm** | 9+ | `11.13.0` |
| **Python** | 3.11+ | `3.13.15` |
| **Rust & Cargo** | 1.75+ | `1.99.0` (MSVC toolchain) |
| **C++ Build Tools** | Visual Studio 2022 | MSVC Build Tools 17.14 |
| **WebView2** | Evergreen Runtime | `155.0.4283.45` |

---

## 🚀 Step-by-Step Setup & Launch Guide

Open **PowerShell** in the repository root (`d:\trinetra`):

### Step 1: Install Python Dependencies
```powershell
python -m pip install fastapi uvicorn pytest httpx opencv-python
```

### Step 2: Run Python Automated Tests
Run the test suite using `FakeCameraAdapter` (runs completely offline without requiring a physical camera):
```powershell
python -m pytest services/vision-engine/tests -v
```
*Expected Result: 9 passed in ~1.5s.*

### Step 3: Start the Python Vision Engine
In Terminal 1:
```powershell
cd services/vision-engine
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
*Verify: Open `http://127.0.0.1:8000/api/health` in your browser. You will see: `{"status":"ok","service":"trinetra-vision-engine","version":"0.1.0"}`.*

### Step 4: Install Desktop Dependencies & Run Typecheck
In Terminal 2:
```powershell
cd apps/desktop
npm install
npm run build
```
*Expected Result: `tsc && vite build` finishes with 0 errors.*

### Step 5: Launch the Application
You can run the desktop interface in two modes:

#### Option A: Web Development Server (Browser Mode)
```powershell
cd apps/desktop
npm run dev
```
Open `http://127.0.0.1:5173` in your browser.

#### Option B: Native Desktop Window (Tauri 2 Mode)
```powershell
cd apps/desktop
npm run tauri dev
```
This compiles the native Rust host and displays the native desktop application window.

---

## 🎮 How to Test the Camera Pipeline

1. Ensure the Vision Engine is running on `http://127.0.0.1:8000`.
2. Open the Trinetra application. Notice the **Vision Engine Service** card displays: `Online (127.0.0.1:8000)`.
3. Press **Tab** to navigate to the **"▶ Start Camera"** button and press **Enter** (or click it).
4. The webcam will initialize, and live video frames will stream into the viewport at ~20 FPS.
5. Press **Tab** to navigate to the **"⏹ Stop Camera"** button and press **Enter**.
6. The video preview immediately clears, the hardware lock is released, and the status returns to `Stopped (Privacy protected)`.

---

## ❓ Troubleshooting & Common Windows Issues

### 1. "Could not open webcam at index 0" (HTTP 503)
- **Cause 1 (Occupied Camera)**: Another app (Zoom, Teams, Skype, or Windows Camera) has exclusive access to the webcam. Close those applications and click Start Camera again.
- **Cause 2 (Windows Privacy Permissions)**:
  1. Open Windows **Settings** > **Privacy & Security** > **Camera**.
  2. Ensure **"Camera access"** is turned **ON**.
  3. Ensure **"Let desktop apps access your camera"** is turned **ON**.

### 2. "Cannot connect to the Trinetra Vision Engine at 127.0.0.1:8000"
- The Python FastAPI backend is not running. Launch it using:
  ```powershell
  cd services/vision-engine
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  ```

---

## 🔌 Hardware Extension Guide (Future Sprints)

The `CameraAdapter` interface in `services/vision-engine/app/camera/adapter.py` is completely decoupled from the UI. To add a new camera type (e.g. Raspberry Pi CSI camera, wearable smart glasses, or an RTSP wireless stream):

1. Subclass `CameraAdapter`:
   ```python
   from app.camera.adapter import CameraAdapter

   class WearableGlassesCameraAdapter(CameraAdapter):
       def start(self) -> None:
           # Open custom USB/WiFi stream
           pass

       def stop(self) -> None:
           # Release hardware
           pass

       def is_active(self) -> bool:
           return self._active

       def capture_jpeg(self) -> bytes:
           # Return in-memory JPEG byte array
           return frame_bytes

       def get_status(self) -> dict:
           return {"adapter": "WearableGlassesCameraAdapter", "active": self._active}
   ```
2. Plug the adapter into `create_app(adapter=WearableGlassesCameraAdapter())`.
3. Zero changes are required in the React UI, TypeScript types, or Tauri desktop host.
