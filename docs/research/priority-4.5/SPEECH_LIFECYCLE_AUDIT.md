# TRINETRA — PRIORITY 4.5
## Speech Subsystem Lifecycle & Concurrency Audit

---

### 1. Executive Summary & Problem Investigation

During Priority 4.4 and prior test runs, test suites involving FastAPI's `TestClient` and bilingual speech lifecycle endpoints (specifically `test_speech_language_endpoints_lifecycle`, `test_concurrent_language_updates_thread_safety`, and `test_camera_stream_remains_active_during_language_switch` in `services/vision-engine/tests/test_bilingual_speech.py`) hung indefinitely or were terminated by timeout.

To address the mandate of Priority 4.5:
> "Investigate the previously cancelled or terminated bilingual speech lifecycle tests. Determine whether the issue originates in FastAPI TestClient, application lifecycle hooks, SpeechManager initialization, global language locks, background threads, or audio resources. Determine whether the tests genuinely hang or are blocked by the test environment."

A forensic investigation was conducted isolating every layer of the speech and API stack.

---

### 2. Forensic Root Cause Discovery: Windows Sandbox Socketpair Blocking

The investigation discovered that **the speech subsystem, application lifecycle hooks, SpeechManager initialization, and global language locks are completely functional and thread-safe**. 

The hang was caused by a fundamental platform constraint in the Windows execution sandbox:

#### Evidence & Call Stack Analysis:
1. `starlette.testclient.TestClient.__enter__` initializes an asynchronous blocking portal:
   ```python
   self.portal = portal = stack.enter_context(
       anyio.from_thread.start_blocking_portal(**self.async_backend)
   )
   ```
2. `anyio.from_thread.start_blocking_portal()` starts a background worker thread running `anyio.run_eventloop()`, which defaults on Windows to Python's `asyncio.ProactorEventLoop`.
3. `asyncio.ProactorEventLoop.__init__` establishes an internal IPC self-pipe for signal wakeup by executing:
   ```python
   self._csock, self._ssock = socket.socketpair()
   ```
4. On Windows platforms (where POSIX `AF_UNIX` socketpairs are historically emulated over loopback TCP), `socket.socketpair()` binds a listener on `127.0.0.1`, establishes a TCP connection, and calls `accept()`.
5. Under **Standard Sandbox Mode (`BypassSandbox: false`)**, OS-level network isolation blocks TCP socket establishment. Calling `socket.socketpair()` blocks indefinitely awaiting socket connection handshake.

#### Empirical Proof:
An isolated test running purely `socket.socketpair()` hung immediately inside the sandbox:
```python
import socket
s1, s2 = socket.socketpair() # Blocks indefinitely in Standard Sandbox Mode
```
Similarly, a minimal dummy FastAPI application (`app = FastAPI()`) with `with TestClient(app) as client:` hung immediately at the same point, proving that Trinetra's application code was not the cause of the hang.

---

### 3. Speech Subsystem Concurrency & Thread-Safety Audit

To evaluate Trinetra's speech subsystem independently of `starlette.testclient`, a dedicated stress test (`scratch/verify_speech_concurrency.py`) was executed across 5 core areas:

| Test Scenario | Stress Load | Result | Behavioral Finding |
| :--- | :---: | :---: | :--- |
| **Concurrent Announcements** | 40 threads calling `SpeechManager.announce` simultaneously | **PASSED** | Thread-safe queue insertion; `_state_lock` and `_cooldown_lock` prevented data corruption or deadlock. |
| **Priority Preemption & Queue Drain** | 5 low-priority items followed by 1 `CRITICAL_HAZARD` with `interrupt=True` | **PASSED** | Critical item immediately drained pending low-priority queue and halted active audio. |
| **Concurrent Language Switching** | 60 concurrent threads switching between `'ne'` and `'en'` | **PASSED** | State consistency maintained across `PerceptionPipeline`, `SceneDecisionEngine`, `SpeechManager`, and `IncidentRecorder`. |
| **Direct Endpoint Function Execution** | Invoking `/api/speech/language`, `/api/speech/announce`, `/api/speech/status` directly | **PASSED** | Route handlers validated languages, returned HTTP 400 on invalid input, and updated state without requiring `TestClient`. |
| **Mute, Pause, and Cleanup Lifecycle** | Enqueuing while muted/paused; queue drainage on `stop()` and `shutdown()` | **PASSED** | Queue emptied cleanly; muted calls suppressed; worker daemon thread terminated without lingering threads. |

---

### 4. Discrepancy Identified: Un-normalized `SpeechManager.language` Setter

During the stress test, a concrete implementation inconsistency was discovered:

- In `app/detection/engine.py` (`PerceptionPipeline.language` setter):
  ```python
  norm = normalize_language(value) if is_supported_language(value) else value.strip().lower()
  ```
- In `app/main.py` (`/api/speech/language` endpoint):
  ```python
  target_lang = normalize_language(payload.language) # Converts 'ne-NP' -> 'ne'
  ```
- In `app/audio/speaker.py` (`SpeechManager.language` setter):
  ```python
  @language.setter
  def language(self, value: str) -> None:
      with self._state_lock:
          self._default_language = value.strip().lower() # Stored 'ne-np' literally!
  ```

#### Impact:
When language is updated via the HTTP endpoint (`/api/speech/language`), `main.py` normalizes the input before passing it to `SpeechManager`, so in production it is always normalized. However, if a developer or test suite sets `speech_manager.language = "ne-NP"` directly, `SpeechManager` stores `"ne-np"` unnormalized. While `active_language.startswith("ne")` still matched for voice checks, strict equality checks (`manager.language == "ne"`) failed.

**Recommendation:** Update `SpeechManager.language.setter` to pass `value` through `normalize_language()` to ensure absolute API contract symmetry across all components.

---

### 5. Summary of Audit Conclusions

1. **Test Environment vs Code Defect:** The test hangs were 100% caused by `TestClient`'s reliance on `socket.socketpair()` in an isolated sandbox environment without network permissions.
2. **Subsystem Thread Safety:** Verified across 40–60 concurrent threads. No race conditions, deadlocks, or state corruption observed.
3. **Queue Cancellation & Audio Halting:** Priority preemption, queue draining, mute suppression, and shutdown behave strictly according to architectural specifications.
