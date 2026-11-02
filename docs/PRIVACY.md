# Trinetra Privacy Charter

## 1. Local-First Processing
- **Zero Cloud Uploads:** All camera capture, image processing, model inference, and speech generation occur exclusively on the local machine.
- **Strict Loopback Binding:** The Python vision engine binds exclusively to the loopback IP (`127.0.0.1`), preventing external devices on the local area network (LAN) or the internet from accessing the service.
- **No Frame Persistence:** Camera frames are held exclusively in volatile RAM within a capacity-1 buffer and streamed as ephemeral JPEG byte buffers. No images, video clips, or telemetry are ever written to disk or persistent storage.
- **No Audio Recording or Logging:** The speech synthesis engine only produces outgoing synthetic speech. Trinetra records zero ambient microphone audio, captures zero voice snippets, and maintains zero audio logs on disk.
- **Zero Telemetry or Analytics:** Trinetra contains no tracking beacons, usage metrics collection, analytics scripts, crash uploaders, or external telemetry of any kind.

## 2. Explicit User Consent & Hardware Locks
- **No Spontaneous Activation:** Camera hardware is never activated automatically upon operating system startup, application launch, or background service initialization.
- **User Action Required:** Video capture begins only when the user explicitly triggers the **"Start Camera"** action via UI button or keyboard shortcut.
- **Instant Revocation:** Clicking **"Stop Camera"** or quitting the application immediately stops frame acquisition, breaks the capture loop, releases the OS DirectShow camera device handle, and frees all memory buffers.
- **Instant Speech Silencing:** Users can immediately silence or mute speech feedback via the Spacebar shortcut or mute control without affecting underlying processing.

## 3. Host Loopback Security & Session Authorization
- **Inter-Process Protection:** In multi-user or shared desktop environments, local non-privileged processes may attempt to communicate with loopback ports. Trinetra supports a local session authorization token (`TRINETRA_SESSION_TOKEN`). When configured, requests missing the required bearer token are rejected immediately with HTTP 401 Unauthorized.
- **Tauri Handshake:** In production deployments, Tauri generates a high-entropy cryptographically secure random session token at launch, injects it into the Python sidecar environment, and appends it to all HTTP client headers (`Authorization: Bearer <token>`).
- **Strict Origin Validation:** The HTTP server rejects requests originating from unauthorized browser web pages via strict CORS policies, restricting communication exclusively to Tauri native desktop wrappers and trusted local origins.

## 4. Frontend Memory Hygiene
- **URL Lifetime Management:** When displaying camera streams within the desktop webview, every object URL generated via `URL.createObjectURL()` is tracked and explicitly invalidated using `URL.revokeObjectURL()` after painting. This ensures that video frame data does not linger in webview memory or risk heap leakage.
- **Transient Perception State:** Detected object labels and bounding boxes are held only in ephemeral component state for live screen rendering and ARIA live announcements. No spatial coordinate history is saved.

## 5. Incident Documentation Storage & Retention Policy
- **On-Demand Capture Only:** Snapshots are written to disk strictly upon explicit manual user request (`POST /api/incident/capture`). The system never records incident frames autonomously in background operation.
- **Bounded Local Retention:** A bounded ring buffer (default 50 snapshots) automatically prunes the oldest records to prevent unbounded disk usage on local host storage.
- **Local Tamper-Evidence:** Each incident generates a cryptographic SHA-256 digest over the raw image bytes and canonical metadata. This enables users to verify that local logs have not suffered silent on-disk corruption or unauthorized alteration.
- **No Biometric Data:** Snapshots retain standard generic object classification metadata only. No biometric facial templates, biometric signatures, or facial embeddings are generated or stored.

## 6. Offline Location Privacy & Opt-In Policy
- **Disabled by Default:** Location telemetry is disabled out-of-the-box (`status="disabled"`).
- **Zero Cloud Transmission:** Coordinates remain strictly confined to local volatile memory and local incident records. No coordinates are ever shared or transmitted over the internet.
- **Truthful Status Reporting:** The location provider accurately reports `live`, `cached`, `unavailable`, or `disabled`. Coordinates are never hallucinated, fabricated, or approximated from IP geolocation databases.
