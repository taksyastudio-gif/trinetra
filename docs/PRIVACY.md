# Trinetra Privacy Charter

## 1. Local-First Processing
- **Zero Cloud Uploads:** All camera capture, image processing, and engine logic occur exclusively on the local machine.
- **Strict Loopback Binding:** The Python vision engine binds exclusively to the loopback IP (`127.0.0.1`), preventing external devices on the local network (LAN) or internet from accessing the service.
- **No Frame Persistence:** Camera frames are streamed directly from volatile memory to the UI as JPEG byte buffers. No frames, snapshots, or video streams are written to disk.

## 2. Explicit User Consent
- **No Spontaneous Activation:** The camera hardware is never activated automatically upon application launch or background startup.
- **User Action Required:** Capture only begins when the user intentionally clicks or triggers the **"Start Camera"** control.
- **Instant Revocation:** Clicking **"Stop Camera"** or terminating the desktop application immediately releases the hardware capture lock.

## 3. Telemetry & Analytics
- No analytics trackers, telemetry collectors, tracking cookies, or identifier beacons exist in the application.

## 4. Trust Assumptions & Limitations
- Trinetra assumes that the host operating system (Windows) is secure and free of malware or spyware that could intercept loopback traffic or monitor the display.
- In multi-user operating system environments, local non-privileged processes running under the same user account may theoretically connect to local loopback ports unless restricted by local firewall or IPC authorization tokens. Additional session authentication tokens are planned for subsequent production releases.
