# TRINETRA — PRIORITY 4.5
## Missing Test Coverage & Gap Analysis

---

### 1. Executive Summary

Trinetra's vision engine has achieved high unit test coverage (61 passing tests covering heuristics, state transitions, Kalman filtering, ego-motion, and scene decision). 

However, the Priority 4.5 audit identified specific architectural gaps where integration, stress, and platform-boundary tests are currently missing.

---

### 2. Comprehensive Gap Analysis Matrix

| Gap ID | Subsystem Area | Current Coverage | Missing Integration / Edge Case Test | Risk Level | Recommended Test Specification |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **GAP-01** | **FastAPI Language Endpoints** | Tested via `TestClient` (which blocks on Windows sandbox sockets). | Socket-free route handler test invoking `speech_set_language` and `speech_get_language` directly without network stack. | **Medium** | Invoke endpoint functions directly with Pydantic request models; assert response schemas and component state mutation. |
| **GAP-02** | **Continuous Camera Stream Outage** | Synchronous frame packet tests in `test_controlled_sensor_health_integration.py`. | Multi-threaded test where a background `PerceptionWorkerThread` receives 100 continuous frames via `submit_frame`, encounters 10 dark frames, and resumes. | **High** | Spawn worker thread; feed frames via `submit_frame`; assert zero deadlock, bounded memory, and clean track drop/recovery. |
| **GAP-03** | **Multi-Session Track ID Boundary** | Single session tracking tests. | Verifying that calling `reset_session()` (e.g. camera stop/start) resets `_next_track_id = 1`, whereas in-session degradation preserves monotonic incrementation. | **Low** | Test both codepaths in succession; assert track ID sequence `[1, 1 (coasting), purged] -> [2 (recovered)] -> [reset_session()] -> [1 (new session)]`. |
| **GAP-04** | **Rapid Language Switching Under Load** | Component-level switching tests without simultaneous detection load. | Switching languages while 10 objects are actively tracked by Kalman filters and pending in speech queue. | **Medium** | Spawn 5 tracking objects; trigger language switch mid-flight; assert that subsequent announcements speak in the new language without error. |
| **GAP-05** | **UVC Camera Disconnect & Recovery** | Mock camera adapter unit tests. | Physical or simulated USB camera unplug mid-stream (`FrameCaptureError`), followed by reconnect. | **High** | Test `OpenCVCameraAdapter.capture_frame()` with simulated device drop; assert `dropped_frames` counter increments and status reports error without crashing server. |
| **GAP-06** | **Speech Queue Overflow & Backpressure** | Tested up to queue limit (10 items). | Extreme burst of 100 simultaneous announcements arriving within 10ms. | **Medium** | Verify that `queue.Full` drops lowest priority items gracefully with logged warning, and worker thread continues operating. |
| **GAP-07** | **Ego-Motion Degeneracy under Extreme Shake** | Moderate camera motion tests in `test_ego_motion.py`. | Violent camera shake causing 100% optical flow outlier rejection. | **Low** | Input frames with pure white noise / random shifts; verify that estimator returns identity matrix and does not trigger numerical NaN/Inf in Kalman covariance. |

---

### 3. Implementation Plan for Missing Tests

To close these gaps in Priority 4.6 without risking sandbox hangs:
1. **Socket-Free API Test Harness:** Standardize an in-memory test runner for FastAPI endpoints that passes requests directly to endpoint functions, bypassing `starlette.testclient.TestClient`.
2. **Asynchronous Perception Worker Integration Suite:** Implement `tests/test_pipeline_async_integration.py` utilizing `submit_frame` and real thread synchronization.
3. **Hardware Fault Injection Harness:** Expand `FakeCameraAdapter` to include controllable fault injection methods:
   - `adapter.simulate_disconnect()`
   - `adapter.simulate_corrupted_packet()`
   - `adapter.simulate_frame_delay(ms=500)`
