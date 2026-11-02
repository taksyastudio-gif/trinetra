# TRINETRA — PRIORITY 4.4
## Rollback Procedure & Operational Runbook

---

### 1. Instant Runtime Rollback (Zero Code Change)

Because the integration is governed by the `TRINETRA_ENABLE_SENSOR_HEALTH` feature flag, any unexpected behavior in production can be instantly resolved in **0 seconds** without modifying code, rebuilding binaries, or redeploying packages.

#### Step 1: Disable Feature Flag
Ensure the environment variable is unset or explicitly set to `0`:

**Windows PowerShell:**
```powershell
$env:TRINETRA_ENABLE_SENSOR_HEALTH = "0"
# Or delete the variable entirely:
Remove-Item Env:TRINETRA_ENABLE_SENSOR_HEALTH
```

**Linux / macOS:**
```bash
export TRINETRA_ENABLE_SENSOR_HEALTH="0"
# Or unset:
unset TRINETRA_ENABLE_SENSOR_HEALTH
```

**Docker / Systemd / Process Supervisor (`tauri.conf.json` / `supervisor.rs`):**
Remove `TRINETRA_ENABLE_SENSOR_HEALTH="1"` from the environment configuration block or set to `"0"`.

#### Verification of Rollback:
When disabled, `pipeline.health_controller.is_enabled()` immediately returns `False`. The pre-flight block is bypassed unconditionally, restoring 100% legacy execution flow.

---

### 2. Code-Level Reversion Procedure

If a full code-level rollback is desired to completely remove the Priority 4.4 changes from the repository:

#### Step 1: Identify Changed Files
Priority 4.4 modified or created the following files in `services/vision-engine`:
1. `services/vision-engine/app/camera/health_controller.py` *(New file)*
2. `services/vision-engine/app/detection/engine.py` *(Modified: pre-flight check hook)*
3. `services/vision-engine/tests/test_health_controller.py` *(New test file)*
4. `services/vision-engine/tests/test_controlled_sensor_health_integration.py` *(New test file)*

#### Step 2: Revert In-Place Modifications
To revert `engine.py` without affecting other uncommitted changes in the repository:
```bash
git checkout HEAD -- services/vision-engine/app/detection/engine.py
```

#### Step 3: Remove New Isolated Files (If Desired)
```bash
rm services/vision-engine/app/camera/health_controller.py
rm services/vision-engine/tests/test_health_controller.py
rm services/vision-engine/tests/test_controlled_sensor_health_integration.py
```

---

### 3. Blast Radius and Side-Effect Analysis

| Affected Area | Blast Radius if Rolled Back | Side Effects on Running Application |
| :--- | :---: | :--- |
| **Object Detection (`engine.py`)** | Zero | Reverts to unconditional inference on all frames (legacy behavior). |
| **Speech Output (`speaker.py`)** | Zero | Unaffected; speech backend and arbitration are unchanged. |
| **Camera Acquisition (`adapter.py`)** | Zero | Unaffected; camera frame ingestion and timestamps are unchanged. |
| **Desktop Application (`apps/desktop`)** | Zero | Unaffected; HTTP API contracts and schemas remain identical. |
| **Database / Disk State** | Zero | No persistent storage or database schemas are altered by the controller. |

---

### 4. Post-Rollback Validation Checklist

After executing a runtime or code-level rollback:
1. Run core perception tests:
   ```bash
   pytest services/vision-engine/tests/test_kalman_tracking.py services/vision-engine/tests/test_ego_motion.py services/vision-engine/tests/test_scene_decision.py -v
   ```
2. Verify that `test_kalman_tracking.py` (10/10) and `test_ego_motion.py` (21/21) pass without failure.
3. Verify that the desktop UI receives live video streaming and detection boxes normally.
