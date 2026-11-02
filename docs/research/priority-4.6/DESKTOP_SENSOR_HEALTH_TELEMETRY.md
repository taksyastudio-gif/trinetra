# TRINETRA — PRIORITY 4.6 STAGE 4
## Desktop Sensor-Health Telemetry & UI Integration Report

**Status:** COMPLETE & VERIFIED  
**Targets Modified:**
- Backend API Schema: `services/vision-engine/app/main.py` (`PerceptionHealthTelemetry`, `CameraStatusResponse`)
- Frontend Types: `apps/desktop/src/types/api.ts` (`PerceptionHealthTelemetry`, `CameraStatusResponse`)
- Frontend Components: `apps/desktop/src/components/StatusIndicator.tsx` (Perception Health Card & Safety Disclaimer)
- Desktop Application Root: `apps/desktop/src/App.tsx` (Telemetry State Management)
**Verification Results:**
- Backend Pytest: 45/45 Passed (100%)
- Frontend TypeScript Typecheck & Vite Build: 0 Errors (100%)

---

### 1. Executive Summary

In Priority 4.5, architectural audit revealed that while `SensorHealthController` actively performed spatial quality assessment and state debouncing inside the Python perception loop, the desktop frontend had no direct visibility into perception degradation, occlusion, or sensor outage states. The desktop UI only surfaced raw connection and hardware camera states, leaving users and developers unaware of camera degradation until speech chimes fired.

Stage 4 audited the end-to-end telemetry pathway, updated the `/api/camera/status` contract to securely expose sensor health metrics, and integrated a dedicated perception health status card into the desktop dashboard with prominent non-safety diagnostic disclaimers.

---

### 2. Contract Specification & Data Schema

#### 2.1 Backend Pydantic Schema (`services/vision-engine/app/main.py`)

```python
class PerceptionHealthTelemetry(BaseModel):
    state: str = "VALID_OBSERVATION"
    status: str = "NORMAL"
    is_degraded: bool = False
    reasons: list[str] = Field(default_factory=list)
    last_evaluated_timestamp: Optional[float] = None
    disclaimer: str = "Diagnostics and debugging only; not safety certified."

class CameraStatusResponse(BaseModel):
    active: bool
    adapter: str
    camera_index: Optional[int] = None
    resolution: Optional[str] = None
    frames_captured: int
    dropped_frames: int = 0
    uptime_seconds: float
    session_id: Optional[str] = None
    perception_health: Optional[PerceptionHealthTelemetry] = None
```

- **Backward Compatibility:** `perception_health` defaults to `None` and is optional. Any legacy API client or downstream test consuming `/api/camera/status` deserializes seamlessly.
- **Authoritative Source:** Telemetry is sourced directly from `perception_pipeline.health_controller`, reflecting the exact state driving DNN suppression and Kalman tracking coasting.

#### 2.2 Frontend TypeScript Interface (`apps/desktop/src/types/api.ts`)

```typescript
export interface PerceptionHealthTelemetry {
  state: "VALID_OBSERVATION" | "TEMPORARILY_DEGRADED" | "SENSOR_UNAVAILABLE" | "STALE_TERMINATED" | "RECOVERY_TRANSITION" | string;
  status: "NORMAL" | "DEGRADED" | "SEVERELY_DEGRADED" | string;
  is_degraded: boolean;
  reasons: string[];
  last_evaluated_timestamp: number | null;
  disclaimer: string;
}

export interface CameraStatusResponse {
  active: boolean;
  adapter: string;
  camera_index?: number | null;
  resolution?: string | null;
  frames_captured: number;
  dropped_frames?: number;
  uptime_seconds: number;
  session_id?: string | null;
  perception_health?: PerceptionHealthTelemetry | null;
}
```

---

### 3. Desktop UI Implementation (`StatusIndicator.tsx` & `App.tsx`)

#### 3.1 Status Indicator Grid Integration

The desktop dashboard uses a CSS auto-fit grid (`repeat(auto-fit, minmax(280px, 1fr))`). A third card was added alongside the Vision Engine Service and Webcam Hardware cards:

| Sensor State | Dot Class | Display Label | Detail Description |
|---|---|---|---|
| Camera Inactive | `status-dot-stopped` | Standby | Camera inactive / privacy protected |
| `VALID_OBSERVATION` | `status-dot-active` | Optimal | Clear view, nominal sharpness & lighting |
| `TEMPORARILY_DEGRADED` | `status-dot-starting` | Degraded | Sub-optimal view (`reasons`: blur, low contrast) |
| `RECOVERY_TRANSITION` | `status-dot-starting` | Recovering... | Stabilizing view after temporary outage |
| `SENSOR_UNAVAILABLE` / `STALE_TERMINATED` | `status-dot-error` | Unavailable | Severe obstruction, lens cover, or darkness |

#### 3.2 Non-Safety Certification Disclaimer

In strict accordance with the Trinetra safety protocol, neither the API nor the desktop UI suggests or implies safety certification.
- Backend payload explicitly carries `disclaimer: "Diagnostics and debugging only; not safety certified."`.
- Frontend card renders a permanent subtitle:
  `<span className="status-disclaimer">Diagnostics only — not safety certified</span>`.

#### 3.3 Heartbeat Telemetry Synchronization

- `App.tsx` polls `cameraApi.getStatus()` every 4,000 ms via the existing system heartbeat and immediately upon camera start/stop transitions.
- The `perceptionHealth` state is updated reactively, providing real-time diagnostic awareness without introducing high-frequency network overhead.

---

### 4. Verification Evidence

#### 4.1 Backend API Verification (`test_api.py`)
```text
services\vision-engine\tests\test_api.py::test_camera_status_inactive PASSED
...
============================= 45 passed in 7.04s ==============================
```

#### 4.2 Desktop Frontend Build Verification (`npm --prefix apps/desktop run build`)
```text
> trinetra-desktop@0.1.0 build
> tsc && vite build

vite v5.4.21 building for production...
transforming...
✓ 42 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.42 kB │ gzip:  0.29 kB
dist/assets/index-Ce4XUvzH.css    9.46 kB │ gzip:  2.44 kB
dist/assets/core-BUhCcD2K.js      2.70 kB │ gzip:  1.11 kB
dist/assets/index-D3FeU7qT.js   165.15 kB │ gzip: 52.98 kB
✓ built in 1.34s
```
