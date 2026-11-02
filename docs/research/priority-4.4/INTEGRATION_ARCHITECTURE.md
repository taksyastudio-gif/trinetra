# TRINETRA — PRIORITY 4.4
## Integration Architecture: Controlled Sensor Health Gatekeeper

---

### 1. Executive Summary & Architectural Objective

The goal of Priority 4.4 is the controlled integration of the **Sensor Health Gatekeeper** into Trinetra's real-time perception pipeline without risking regressions, audio jitter, or pipeline degradation.

Prior to Priority 4.4, Trinetra's perception pipeline (`PerceptionPipeline` in `services/vision-engine/app/detection/engine.py`) executed deep neural network (DNN) object detection (`YOLOX-Nano` and `YuNet`) unconditionally on every incoming frame packet. When an environmental outage occurred—such as lens obstruction, complete darkness, extreme whiteout, or severe defocus blur—the DNN was forced to infer on uninformative noise, leading to phantom detections, hallucinatory tracks, wasted battery/CPU cycles, and disorientation for visually impaired users.

Under Priority 4.4, the pipeline integrates a single, authoritative **`SensorHealthController`** that acts as an intelligent pre-flight gatekeeper.

```
       [ Incoming Frame Packet (JPEG) ]
                      │
                      ▼
        ┌───────────────────────────┐
        │   SensorHealthController   │◄─── Feature Flag: TRINETRA_ENABLE_SENSOR_HEALTH
        │   (Pre-flight Assessment)  │     (Default: 0 / Disabled -> Pass-through)
        └─────────────┬─────────────┘
                      │
         ┌────────────┴────────────┐
         │ State & Action Decision │
         └────────────┬────────────┘
                      │
      ┌───────────────┴───────────────┐
      │                               │
[ VALID_OBSERVATION ]    [ DEGRADED / OUTAGE / STALE ]
      │                               │
      ▼                               ▼
Run DNN Inference             Suppress DNN Inference (0.0 ms)
(YOLOX-Nano + YuNet)          Coast / Purge Kalman Tracks
Update Kalman Tracks          Emit Debounced Audio Chime
Dispatch Announcements        Maintain System Liveness
```

---

### 2. Single Point of Truth: `SensorHealthController`

All sensor quality metrics, temporal debouncing, lifecycle transitions, Kalman coasting limits, and audio notifications are centralized within `services/vision-engine/app/camera/health_controller.py`. No other module performs independent health heuristic calculations.

#### Core Responsibilities of `SensorHealthController`:
1. **Spatial Quality Assessment:**
   - Subdivides the frame into a 3×3 grid (9 equal spatial tiles).
   - Evaluates tile-level luminance ($\mu_{\text{tile}}$) and standard deviation contrast ($\sigma_{\text{tile}}$).
   - Detects partial lens obstructions (e.g., finger over one quadrant) while distinguishing uniform low-texture scenes (e.g., clean white walls).
2. **Boundary-Induced Artifact Rejection:**
   - Computes the spatial median of tile Laplacian variances ($\widetilde{\sigma^2_{\Delta}}$) rather than relying exclusively on global variance, completely neutralizing boundary inflation caused by hard obstruction edges.
3. **Temporal Debouncing (Hysteresis):**
   - Requires $N_{\text{degrade}} = 2$ consecutive degraded frames before exiting nominal operation, preventing dappled sunlight or transient illumination flickers from causing audio flutter.
   - Requires $N_{\text{recover}} = 2$ consecutive clean frames before transitioning back to `VALID_OBSERVATION`.
4. **Five-State Perception State Machine:**
   - Formally enforces transitions across:
     - `VALID_OBSERVATION`
     - `TEMPORARILY_DEGRADED`
     - `SENSOR_UNAVAILABLE`
     - `STALE_TERMINATED`
     - `RECOVERY_TRANSITION`
5. **Time- & Kinematic-Bounded Coasting:**
   - Enforces both a frame limit ($K_{\text{frames}} = 4$) and an absolute wall-clock duration limit ($\Delta t_{\text{max}} = 0.20\text{ s}$).
   - In rapid turn scenarios ($\Delta \theta > 15^\circ$), coasting is immediately terminated to prevent cross-sector ghost tracks.
6. **Acoustic Safety & Debounce:**
   - Enforces a minimum 5.0-second cooldown between non-verbal audio chimes to guarantee that persistent obstructions do not result in audio clutter or auditory fatigue.

---

### 3. Pipeline Integration Point in `engine.py`

The integration was hooked directly into `PerceptionPipeline` at two symmetrical locations:
1. `process_frame(self, packet: FramePacket) -> Optional[DetectionResult]` (offline synchronous processing and unit testing).
2. `_worker_loop(self)` (real-time asynchronous background worker thread).

#### Exact Hook Mechanism:
```python
# 0. Pre-flight sensor health evaluation (controlled via disabled-by-default feature flag)
state_action = None
if hasattr(self, "health_controller") and self.health_controller and self.health_controller.is_enabled():
    try:
        _, state_action = self.health_controller.evaluate_frame(
            packet.jpeg_bytes,
            frame_id=packet.frame_id,
            timestamp=packet.captured_at
        )
    except Exception as h_err:
        logger.warning(f"SensorHealthController error: {h_err}")
        state_action = None

# 1. Suppress DNN inference during verified outages
if state_action is not None and not state_action.should_run_dnn:
    if getattr(state_action, "tracks_purged", False) or getattr(state_action.state, "value", "") == "STALE_TERMINATED":
        if hasattr(self, "tracker") and self.tracker:
            if hasattr(self.tracker, "tracks"):
                self.tracker.tracks.clear()
            else:
                self.tracker.reset()
    elif getattr(state_action, "kalman_action", "") == "COAST_ONLY":
        if hasattr(self, "tracker") and self.tracker and self.tracker.tracks:
            for trk in self.tracker.tracks:
                if getattr(trk.state, "value", "") != "deleted":
                    trk.predict(packet.captured_at)
                    trk.mark_missed(max_age=15)

    suppressed_result = DetectionResult(
        frame_id=packet.frame_id,
        timestamp=packet.captured_at if packet.captured_at > 0 else time.time(),
        detections=[],
        inference_time_ms=0.0,
        model_name=getattr(self.engine, "model_name", "InferenceSuppressed")
    )
    with self._lock:
        self._latest_result = suppressed_result
        self._last_processed_frame_id = packet.frame_id
        self._last_processed_session_id = packet.session_id
        self._frames_processed_count += 1
    return suppressed_result
```

---

### 4. Zero-Regression Feature Flag Architecture

To ensure 100% backward compatibility and eliminate production risk, the integration is governed by the environment variable:

```bash
TRINETRA_ENABLE_SENSOR_HEALTH
```

- **Default (Unset or `"0"`):** `is_enabled()` returns `False`. The pre-flight evaluation block is bypassed instantly (`state_action = None`), executing existing production paths with $0.0\mu\text{s}$ overhead.
- **Enabled (`"1"`, `"true"`, `"yes"`):** Active monitoring is engaged. Incoming frames undergo spatial evaluation, debouncing, and state machine dispatch.

This guarantee ensures that deployment can proceed with zero blast radius.
