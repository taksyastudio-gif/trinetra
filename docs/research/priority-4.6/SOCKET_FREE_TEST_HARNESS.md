# TRINETRA — PRIORITY 4.6
## Stage 1: Socket-Free API Testing Strategy & Implementation

---

### 1. Architectural Problem Diagnosis

In sandboxed Windows developer and CI environments (`BypassSandbox: false`), standard FastAPI integration testing via `starlette.testclient.TestClient` hung indefinitely during event loop initialization.

#### Forensic Root Cause:
`starlette.testclient.TestClient` relies on AnyIO's `BlockingPortal`, which runs an asynchronous event loop on a background thread. On Windows, Python's `asyncio.ProactorEventLoop` calls `socket.socketpair()` to create a self-pipe. Because Windows lacks native POSIX `AF_UNIX` socketpairs, `socket.socketpair()` binds to `127.0.0.1` and establishes an internal TCP loopback handshake. Under OS-level sandbox isolation, loopback TCP connections block awaiting socket connection authorization.

---

### 2. Implementation: `SocketFreeTestClient`

Rather than bypassing sandbox isolation or weakening test assertions, a high-fidelity, in-process testing harness was implemented in:

`services/vision-engine/tests/socket_free_client.py`

#### Key Capabilities:
1. **Direct Route Dispatch without Networking:**
   Maps incoming requests `(METHOD, PATH)` directly to the synchronous FastAPI endpoint functions registered on the `FastAPI` instance.
2. **Strict Pydantic Request Validation:**
   Extracts route parameter annotations (including `Optional[BaseModel]`). Deserializes incoming JSON dictionaries into formal Pydantic models. If validation fails, immediately returns HTTP 422 with validation error details, exactly mirroring FastAPI.
3. **Route Dependency Injection Execution:**
   Inspects `route.dependencies`. Executes dependency functions (e.g. `verify_token`), checking headers such as `X-Trinetra-Session-Token`. Raises and returns HTTP 401 when unauthorized.
4. **Response Serialization & Header Emulation:**
   - Wraps Pydantic response models via `.model_dump()`.
   - Serializes lists of Pydantic models.
   - Encapsulates binary `Response` bodies (e.g. JPEG bytes).
   - Preserves case-insensitive HTTP headers (e.g. `X-Frame-Id`, `X-Session-Id`, `X-Captured-At`) using Starlette's `Headers` multi-dict.
5. **Lifecycle Context Management (`__enter__` / `__exit__`):**
   Executes startup and shutdown hardware cleanup (`perception_pipeline.stop()`, `camera_manager.stop_session()`, `speech_manager.shutdown()`) when exiting `with SocketFreeTestClient(app) as client:`.

---

### 3. Empirical Verification Results

The socket-free client was integrated into both API test suites:
- **`tests/test_api.py`:** **45 passed out of 45 tests** in $7.63\text{ s}$ (100% pass rate).
- **`tests/test_bilingual_speech.py`:** **8 passed out of 8 tests** in $2.48\text{ s}$ (100% pass rate).

#### Verified Assertions:
- Health check endpoints (`/api/health`).
- Camera device enumeration and status (`/api/camera/devices`, `/api/camera/status`).
- Dynamic device switching and session ID tracking.
- Monotonic frame headers (`X-Frame-Id`, `X-Captured-At`, `X-Session-Id`).
- Speech language endpoints (GET/POST `/api/speech/language`), aliases (`ne-NP`), and invalid code rejection (400 Bad Request).
- Dynamic language switching without camera restart.
- Authenticated endpoint security enforcement (401 Unauthorized without session token).
- Swagger documentation toggling (`/docs`, `/openapi.json`).

---

### 4. Boundary Audit: Untested HTTP-Level Behaviors

The socket-free test harness provides high assurance for application logic, schemas, and security headers. For complete technical transparency, the following transport-layer behaviors remain untested without real TCP sockets:
1. **TCP Connection Multiplexing:** HTTP/1.1 keep-alive timeouts and TCP socket buffer backpressure under multi-client loads.
2. **ASGI Middleware Wire Formats:** Raw chunked transfer encoding and Gzip compression at the raw socket byte level.
3. **Reverse Proxy Header Rewriting:** `X-Forwarded-For` and `X-Forwarded-Proto` handling behind Nginx or Cloudflare.

These transport concerns belong to the web server layer (Uvicorn) rather than Trinetra's application business logic.
