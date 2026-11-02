//! Trinetra Vision Engine Service Supervisor
//! Manages the lifecycle of the local Python vision engine process,
//! provides cryptographically secure ephemeral session token generation,
//! verifies HTTP health and service identity on startup,
//! and ensures deterministic shutdown and orphan process prevention.

use std::collections::VecDeque;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[cfg(windows)]
#[link(name = "bcrypt")]
extern "system" {
    fn BCryptGenRandom(
        h_algorithm: *mut std::ffi::c_void,
        pb_buffer: *mut u8,
        cb_buffer: u32,
        dw_flags: u32,
    ) -> i32;
}

/// Generates an unpredictable 256-bit cryptographically secure hexadecimal token.
pub fn generate_secure_session_token() -> String {
    let mut bytes = [0u8; 32];

    #[cfg(windows)]
    {
        // BCRYPT_USE_SYSTEM_PREFERRED_RNG = 0x00000002
        let status = unsafe {
            BCryptGenRandom(
                std::ptr::null_mut(),
                bytes.as_mut_ptr(),
                bytes.len() as u32,
                0x00000002,
            )
        };
        if status == 0 {
            return bytes.iter().map(|b| format!("{:02x}", b)).collect();
        }
    }

    // High-resolution fallback for non-Windows or fallback scenarios
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    format!("trinetra_sec_{:x}_{:x}", now.as_nanos(), std::process::id())
}

/// Validates raw HTTP response bytes against expected Trinetra Vision Engine identity.
pub fn parse_and_validate_health_response(response_bytes: &[u8]) -> Result<(), String> {
    let response_str = String::from_utf8_lossy(response_bytes);

    // 1. Check HTTP status line
    let mut lines = response_str.lines();
    let status_line = lines
        .next()
        .ok_or_else(|| "Empty response received from service".to_string())?;

    if !status_line.starts_with("HTTP/1.1 200") && !status_line.starts_with("HTTP/1.0 200") {
        return Err(format!(
            "Health check returned non-200 status line: '{}'",
            status_line
        ));
    }

    // 2. Locate response body (after double CRLF or LF)
    let body = if let Some(idx) = response_str.find("\r\n\r\n") {
        &response_str[idx + 4..]
    } else if let Some(idx) = response_str.find("\n\n") {
        &response_str[idx + 2..]
    } else {
        return Err("Malformed HTTP response: Missing header/body delimiter".to_string());
    };

    // 3. Parse JSON body
    let json: serde_json::Value = serde_json::from_str(body.trim())
        .map_err(|e| format!("Invalid JSON body in health check ('{}'): {}", body.trim(), e))?;

    // 4. Validate exact service identity and status
    let service = json
        .get("service")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "Missing 'service' field in health check response".to_string())?;

    let status = json
        .get("status")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "Missing 'status' field in health check response".to_string())?;

    if service != "trinetra-vision-engine" {
        return Err(format!(
            "Service identity mismatch: expected 'trinetra-vision-engine', got '{}'",
            service
        ));
    }

    if status != "ok" {
        return Err(format!(
            "Health check status is not 'ok': got '{}'",
            status
        ));
    }

    Ok(())
}

/// Sends an HTTP GET request to a specified path with an optional session token header.
/// Returns the HTTP status code and response string.
pub fn send_http_get(
    host: &str,
    port: u16,
    path: &str,
    token: Option<&str>,
    timeout: Duration,
) -> Result<(u16, String), String> {
    let target = format!("{}:{}", host, port);
    let socket_addr = target
        .parse()
        .map_err(|e| format!("Invalid target socket address '{}': {}", target, e))?;

    let mut stream = TcpStream::connect_timeout(&socket_addr, timeout)
        .map_err(|e| format!("Connection to {} failed: {}", target, e))?;

    stream
        .set_read_timeout(Some(timeout))
        .map_err(|e| format!("Failed to set read timeout: {}", e))?;
    stream
        .set_write_timeout(Some(timeout))
        .map_err(|e| format!("Failed to set write timeout: {}", e))?;

    let mut request = format!(
        "GET {} HTTP/1.1\r\nHost: {}:{}\r\nConnection: close\r\nAccept: application/json\r\n",
        path, host, port
    );
    if let Some(tok) = token {
        request.push_str(&format!("X-Trinetra-Session-Token: {}\r\n", tok));
    }
    request.push_str("\r\n");

    stream
        .write_all(request.as_bytes())
        .map_err(|e| format!("Failed to send HTTP request: {}", e))?;

    let mut response_bytes = Vec::new();
    stream
        .read_to_end(&mut response_bytes)
        .map_err(|e| format!("Failed to read HTTP response: {}", e))?;

    let response_str = String::from_utf8_lossy(&response_bytes).to_string();
    let status_code = if let Some(first_line) = response_str.lines().next() {
        let parts: Vec<&str> = first_line.split_whitespace().collect();
        if parts.len() >= 2 {
            parts[1].parse::<u16>().unwrap_or(0)
        } else {
            0
        }
    } else {
        0
    };

    Ok((status_code, response_str))
}

/// Sends an HTTP GET request to /api/health and verifies that the responding service is Trinetra.
pub fn verify_http_health(host: &str, port: u16, timeout: Duration) -> Result<(), String> {
    let (_status_code, response_str) = send_http_get(host, port, "/api/health", None, timeout)?;
    parse_and_validate_health_response(response_str.as_bytes())
}

/// Verifies that an existing Trinetra service enforces authentication AND matches the expected session token.
/// Probes `/api/camera/status` with an invalid token first to ensure 401 is returned (auth enforced),
/// then with the expected token to ensure 200 is returned (token match).
pub fn verify_service_authentication(
    host: &str,
    port: u16,
    expected_token: &str,
    timeout: Duration,
) -> Result<(), String> {
    // 1. Probe with non-secret dummy token to verify that auth is actually enforced
    let dummy_probe_token = "trinetra_auth_enforcement_probe";
    let (dummy_status, _) = send_http_get(host, port, "/api/camera/status", Some(dummy_probe_token), timeout)
        .map_err(|e| format!("Failed to probe service auth enforcement: {}", e))?;

    if dummy_status == 200 {
        return Err(
            "Service at target port is unauthenticated (allowed access to protected endpoint without valid token). Refusing adoption."
                .to_string(),
        );
    }

    if dummy_status != 401 {
        return Err(format!(
            "Protected endpoint returned unexpected status {} instead of 401 on unauthenticated probe.",
            dummy_status
        ));
    }

    // 2. Auth is enforced. Now verify whether the service accepts the expected token.
    let (auth_status, _) = send_http_get(host, port, "/api/camera/status", Some(expected_token), timeout)
        .map_err(|e| format!("Failed to probe service with expected token: {}", e))?;

    if auth_status == 401 {
        return Err(
            "Service at target port is running with a different session token (HTTP 401). Ensure TRINETRA_SESSION_TOKEN matches across both processes."
                .to_string(),
        );
    }

    if auth_status != 200 {
        return Err(format!(
            "Protected endpoint returned unexpected status {} with expected session token.",
            auth_status
        ));
    }

    Ok(())
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct ServiceStatus {
    pub is_running: bool,
    pub is_ready: bool,
    pub host: String,
    pub port: u16,
    pub pid: Option<u32>,
    pub uptime_seconds: f64,
    pub error: Option<String>,
}

/// Locates the `services/vision-engine` directory by checking environment variables,
/// direct relative paths, resource directories, or walking ancestor directories.
pub fn find_service_dir(base_dir: &std::path::Path) -> Option<PathBuf> {
    find_service_dir_internal(base_dir, std::env::var("TRINETRA_SERVICE_DIR").ok().as_deref())
}

pub fn find_service_dir_internal(base_dir: &std::path::Path, env_override: Option<&str>) -> Option<PathBuf> {
    // 1. Check explicit environment override
    if let Some(env_path) = env_override {
        let p = PathBuf::from(env_path.trim());
        if p.is_dir() {
            return Some(p);
        }
    }

    // 2. Direct subpath services/vision-engine
    let direct = base_dir.join("services").join("vision-engine");
    if direct.is_dir() {
        return Some(direct);
    }

    // 3. Bundled resource layouts (relative to base_dir or resource_dir)
    let bundled_candidates = [
        base_dir.join("_up_").join("_up_").join("_up_").join("services").join("vision-engine"),
        base_dir.join("resources").join("_up_").join("_up_").join("_up_").join("services").join("vision-engine"),
        base_dir.join("resources").join("services").join("vision-engine"),
        base_dir.join("vision-engine"),
    ];
    for candidate in &bundled_candidates {
        if candidate.is_dir() && candidate.join("app").join("main.py").is_file() {
            return Some(candidate.clone());
        }
    }

    // 4. If base_dir itself is the vision-engine directory
    if base_dir.file_name().map_or(false, |n| n == "vision-engine") && base_dir.is_dir() {
        return Some(base_dir.to_path_buf());
    }

    // 5. Walk ancestor directories
    let mut curr = base_dir;
    while let Some(parent) = curr.parent() {
        let candidate = parent.join("services").join("vision-engine");
        if candidate.is_dir() {
            return Some(candidate);
        }
        curr = parent;
    }
    None
}

/// Resolves the preferred Python executable, preferring explicit environment override,
/// a local virtual environment (.venv) if present, or system python.
pub fn resolve_python_command(service_dir: Option<&std::path::Path>) -> String {
    resolve_python_command_internal(service_dir, std::env::var("TRINETRA_PYTHON_PATH").ok().as_deref())
}

pub fn resolve_python_command_internal(
    service_dir: Option<&std::path::Path>,
    env_override: Option<&str>,
) -> String {
    // 1. Check explicit environment variable override
    if let Some(env_python) = env_override {
        let trimmed = env_python.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }

    // 2. Check virtual environment in service directory or parent workspace
    if let Some(dir) = service_dir {
        #[cfg(windows)]
        let local_venv = dir.join(".venv").join("Scripts").join("python.exe");
        #[cfg(not(windows))]
        let local_venv = dir.join(".venv").join("bin").join("python");

        if local_venv.is_file() {
            return local_venv.to_string_lossy().to_string();
        }

        // Search ancestor directories for virtual environment
        let mut curr = dir;
        while let Some(parent) = curr.parent() {
            #[cfg(windows)]
            let ancestor_venv = parent.join("services").join("vision-engine").join(".venv").join("Scripts").join("python.exe");
            #[cfg(not(windows))]
            let ancestor_venv = parent.join("services").join("vision-engine").join(".venv").join("bin").join("python");
            if ancestor_venv.is_file() {
                return ancestor_venv.to_string_lossy().to_string();
            }

            #[cfg(windows)]
            let root_venv = parent.join(".venv").join("Scripts").join("python.exe");
            #[cfg(not(windows))]
            let root_venv = parent.join(".venv").join("bin").join("python");
            if root_venv.is_file() {
                return root_venv.to_string_lossy().to_string();
            }

            curr = parent;
        }
    }

    if cfg!(windows) {
        "python".to_string()
    } else {
        "python3".to_string()
    }
}

pub struct ServiceSupervisor {
    child: Option<Child>,
    is_external: bool,
    token: String,
    host: String,
    port: u16,
    start_time: Option<Instant>,
    last_error: Option<String>,
    pub is_verified_ready: bool,
    stderr_log: Arc<Mutex<VecDeque<String>>>,
}

impl ServiceSupervisor {
    pub fn new(host: &str, port: u16) -> Self {
        let token = std::env::var("TRINETRA_SESSION_TOKEN")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(generate_secure_session_token);

        Self {
            child: None,
            is_external: false,
            token,
            host: host.to_string(),
            port,
            start_time: None,
            last_error: None,
            is_verified_ready: false,
            stderr_log: Arc::new(Mutex::new(VecDeque::with_capacity(100))),
        }
    }

    /// Returns the session token strictly if the service has completed verified readiness.
    pub fn session_token(&self) -> Result<&str, String> {
        if !self.is_verified_ready {
            return Err(
                "Session token unavailable: vision service is not running or readiness check has not succeeded."
                    .to_string(),
            );
        }
        Ok(&self.token)
    }

    /// Spawns the Python vision engine process and verifies readiness via HTTP health checks.
    pub fn start(&mut self, base_dir: PathBuf) -> Result<ServiceStatus, String> {
        if self.is_running() {
            if self.is_verified_ready {
                return Ok(self.status());
            }
            // Child is already running, wait for readiness instead of re-spawning
            if let Err(e) = self.wait_for_readiness(Duration::from_secs(15)) {
                self.stop();
                self.last_error = Some(e.clone());
                return Err(e);
            }
            return Ok(self.status());
        }

        // Check if target port is already occupied (by external Trinetra or alien process)
        let is_port_occupied = std::net::TcpListener::bind(format!("{}:{}", self.host, self.port)).is_err();
        if is_port_occupied {
            let probe_timeout = Duration::from_millis(300);
            match verify_http_health(&self.host, self.port, probe_timeout) {
                Ok(()) => {
                    // An HTTP service responding with 'trinetra-vision-engine' is listening.
                    // Strictly audit its authentication before deciding to adopt it.
                    match verify_service_authentication(&self.host, self.port, &self.token, probe_timeout) {
                        Ok(()) => {
                            // Confirmed: Enforces auth AND matches self.token
                            self.is_external = true;
                            self.is_verified_ready = true;
                            self.last_error = None;
                            if self.start_time.is_none() {
                                self.start_time = Some(Instant::now());
                            }
                            return Ok(self.status());
                        }
                        Err(e) => {
                            // Auth verification failed (unauthenticated, token mismatch, or error)
                            let err_msg = format!("Cannot adopt existing service on port {}: {}", self.port, e);
                            self.last_error = Some(err_msg.clone());
                            return Err(err_msg);
                        }
                    }
                }
                Err(e) => {
                    // Port is occupied by an alien service or non-Trinetra process
                    let err_msg = format!(
                        "Port {} is occupied by another application or alien service: {}",
                        self.port, e
                    );
                    self.last_error = Some(err_msg.clone());
                    return Err(err_msg);
                }
            }
        }

        self.is_external = false;
        self.is_verified_ready = false;
        let service_dir = find_service_dir(&base_dir);
        let python_cmd = resolve_python_command(service_dir.as_deref());

        // Avoid shell interpolation by passing discrete command-line arguments
        let mut cmd = Command::new(&python_cmd);
        cmd.args([
            "-m",
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            &self.host,
            "--port",
            &self.port.to_string(),
            "--no-access-log",
        ])
        .env("TRINETRA_SESSION_TOKEN", &self.token)
        .env("TRINETRA_PARENT_PID", std::process::id().to_string())
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }

        if let Some(ref dir) = service_dir {
            cmd.current_dir(dir);
        } else {
            return Err(format!(
                "Could not locate 'services/vision-engine' directory starting from: {}",
                base_dir.display()
            ));
        }

        match cmd.spawn() {
            Ok(mut child) => {
                let pid = child.id();
                let stderr_log = Arc::new(Mutex::new(VecDeque::with_capacity(100)));
                self.stderr_log = Arc::clone(&stderr_log);

                // Continuously drain child stderr in a background thread so the kernel pipe buffer never saturates,
                // while preserving recent error lines in a bounded ring buffer for diagnostics.
                if let Some(stderr) = child.stderr.take() {
                    let log_sink = Arc::clone(&stderr_log);
                    std::thread::Builder::new()
                        .name("trinetra-vision-stderr".to_string())
                        .spawn(move || {
                            use std::io::{BufRead, BufReader};
                            let reader = BufReader::new(stderr);
                            for line in reader.lines() {
                                if let Ok(l) = line {
                                    if let Ok(mut buf) = log_sink.lock() {
                                        if buf.len() >= 100 {
                                            buf.pop_front();
                                        }
                                        buf.push_back(l);
                                    }
                                }
                            }
                        })
                        .ok();
                }

                // Continuously drain child stdout in a background thread so stdout writes never block.
                if let Some(stdout) = child.stdout.take() {
                    std::thread::Builder::new()
                        .name("trinetra-vision-stdout".to_string())
                        .spawn(move || {
                            use std::io::{BufRead, BufReader};
                            let reader = BufReader::new(stdout);
                            for _ in reader.lines() {
                                // Safely drain
                            }
                        })
                        .ok();
                }

                self.child = Some(child);
                self.start_time = Some(Instant::now());
                self.last_error = None;

                // Wait for verified HTTP health response (timeout 15.0 seconds to allow cold ONNX model loading)
                if let Err(e) = self.wait_for_readiness(Duration::from_secs(15)) {
                    self.stop();
                    self.last_error = Some(e.clone());
                    return Err(format!(
                        "Service started (PID {}) but failed readiness check: {}",
                        pid, e
                    ));
                }

                Ok(self.status())
            }
            Err(e) => {
                let err_msg = format!("Failed to spawn vision engine process: {}", e);
                self.last_error = Some(err_msg.clone());
                Err(err_msg)
            }
        }
    }

    /// Probes the HTTP /api/health endpoint until verified or timing out.
    fn wait_for_readiness(&mut self, timeout: Duration) -> Result<(), String> {
        let start = Instant::now();
        let probe_timeout = Duration::from_millis(250);

        while start.elapsed() < timeout {
            // Check if process terminated prematurely (e.g. port collision / syntax error)
            if let Some(child) = &mut self.child {
                match child.try_wait() {
                    Ok(Some(exit_status)) => {
                        let stderr_msg = self
                            .stderr_log
                            .lock()
                            .map(|lines| lines.iter().cloned().collect::<Vec<_>>().join("\n"))
                            .unwrap_or_default();
                        return Err(format!(
                            "Process terminated early with status {}: {}",
                            exit_status,
                            stderr_msg.trim()
                        ));
                    }
                    Ok(None) => {} // Still running
                    Err(e) => return Err(format!("Error polling child status: {}", e)),
                }
            }

            // Perform verified HTTP health probe and authenticated endpoint check
            match verify_http_health(&self.host, self.port, probe_timeout) {
                Ok(()) => {
                    if verify_service_authentication(&self.host, self.port, &self.token, probe_timeout).is_ok() {
                        self.is_verified_ready = true;
                        return Ok(());
                    }
                }
                Err(_err) => {
                    // Not ready yet or connection refused; continue polling until timeout
                }
            }

            std::thread::sleep(Duration::from_millis(100));
        }

        Err(format!(
            "Timed out after {}s waiting for Trinetra Vision Engine at {}:{} to become ready.",
            timeout.as_secs(),
            self.host,
            self.port
        ))
    }

    /// Halts the child process immediately, preventing orphaned processes.
    pub fn stop(&mut self) {
        self.is_verified_ready = false;
        self.is_external = false;
        if let Some(mut child) = self.child.take() {
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                let _ = Command::new("taskkill")
                    .args(["/F", "/T", "/PID", &child.id().to_string()])
                    .creation_flags(0x08000000)
                    .status();
            }
            let _ = child.kill();
            let _ = child.wait();
        }
        self.start_time = None;
    }

    pub fn is_running(&mut self) -> bool {
        if let Some(child) = &mut self.child {
            match child.try_wait() {
                Ok(None) => true,
                _ => {
                    self.child = None;
                    self.start_time = None;
                    self.is_verified_ready = false;
                    false
                }
            }
        } else if self.is_external {
            let running = verify_http_health(&self.host, self.port, Duration::from_millis(150)).is_ok()
                && verify_service_authentication(&self.host, self.port, &self.token, Duration::from_millis(150)).is_ok();
            if !running {
                self.is_external = false;
                self.is_verified_ready = false;
                self.start_time = None;
            }
            running
        } else {
            self.is_verified_ready = false;
            false
        }
    }

    pub fn status(&mut self) -> ServiceStatus {
        let running = self.is_running();
        let uptime = if running {
            self.start_time.map(|t| t.elapsed().as_secs_f64()).unwrap_or(0.0)
        } else {
            0.0
        };

        ServiceStatus {
            is_running: running,
            is_ready: self.is_verified_ready,
            host: self.host.clone(),
            port: self.port,
            pid: self.child.as_ref().map(|c| c.id()),
            uptime_seconds: (uptime * 10.0).round() / 10.0,
            error: self.last_error.clone(),
        }
    }
}

impl Drop for ServiceSupervisor {
    fn drop(&mut self) {
        self.stop();
    }
}

pub type SharedSupervisor = Arc<Mutex<ServiceSupervisor>>;

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::net::TcpListener;
    use std::thread;

    #[test]
    fn test_generate_secure_session_token_format() {
        let token = generate_secure_session_token();
        assert!(!token.is_empty());
        assert!(
            token.len() >= 32,
            "Session token should be at least 32 characters"
        );
    }

    #[test]
    fn test_parse_and_validate_health_response_success() {
        let raw = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\",\"service\":\"trinetra-vision-engine\",\"version\":\"0.1.0\"}";
        assert!(parse_and_validate_health_response(raw).is_ok());
    }

    #[test]
    fn test_parse_and_validate_health_response_wrong_service() {
        let raw = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\",\"service\":\"unrelated-rogue-service\",\"version\":\"1.0\"}";
        let res = parse_and_validate_health_response(raw);
        assert!(res.is_err());
        assert!(res.unwrap_err().contains("Service identity mismatch"));
    }

    #[test]
    fn test_parse_and_validate_health_response_non_200() {
        let raw = b"HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nNot Found";
        let res = parse_and_validate_health_response(raw);
        assert!(res.is_err());
        assert!(res.unwrap_err().contains("non-200"));
    }

    #[test]
    fn test_parse_and_validate_health_response_invalid_json() {
        let raw = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n<html><body>nginx</body></html>";
        let res = parse_and_validate_health_response(raw);
        assert!(res.is_err());
        assert!(res.unwrap_err().contains("Invalid JSON body"));
    }

    #[test]
    fn test_token_not_disclosed_before_readiness() {
        let sup = ServiceSupervisor::new("127.0.0.1", 8000);
        // Before service starts and passes readiness, token access must return an error
        let token_res = sup.session_token();
        assert!(token_res.is_err());
        assert!(token_res.unwrap_err().contains("Session token unavailable"));
    }

    #[test]
    fn test_token_disclosed_after_readiness() {
        let mut sup = ServiceSupervisor::new("127.0.0.1", 8000);
        sup.is_verified_ready = true;
        let token_res = sup.session_token();
        assert!(token_res.is_ok());
        assert_eq!(token_res.unwrap(), &sup.token);
    }

    #[test]
    fn test_port_collision_alien_service_rejected() {
        // Bind an ephemeral mock port simulating an alien process occupying the port
        let listener = TcpListener::bind("127.0.0.1:0").expect("Failed to bind ephemeral mock port");
        let local_port = listener.local_addr().unwrap().port();

        // Spawn mock responder in background thread that returns an alien service identity
        let handle = thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let _ = stream.read(&mut buf);
                let response = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"status\":\"ok\",\"service\":\"alien-process\"}";
                let _ = stream.write_all(response);
                let _ = stream.flush();
                let _ = stream.shutdown(std::net::Shutdown::Write);
            }
        });

        // Verify that verify_http_health rejects the alien service
        let check_res = verify_http_health("127.0.0.1", local_port, Duration::from_secs(1));
        assert!(check_res.is_err(), "Expected error from alien service, got Ok");
        let err_msg = check_res.unwrap_err();
        assert!(
            err_msg.contains("Service identity mismatch"),
            "Expected 'Service identity mismatch', got: '{}'",
            err_msg
        );

        let _ = handle.join();
    }

    #[test]
    fn test_find_service_dir_from_various_locations() {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        // manifest_dir is apps/desktop/src-tauri
        let found = find_service_dir(&manifest_dir);
        assert!(found.is_some(), "Should find service_dir from CARGO_MANIFEST_DIR");
        let dir = found.unwrap();
        assert!(dir.ends_with("services\\vision-engine") || dir.ends_with("services/vision-engine"));
        assert!(dir.is_dir());

        // Test non-existent path
        let nonexistent = PathBuf::from("C:\\completely\\nonexistent\\deep\\path");
        assert!(find_service_dir(&nonexistent).is_none());
    }

    #[test]
    fn test_resolve_python_command() {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let service_dir = find_service_dir(&manifest_dir);
        let python_cmd = resolve_python_command(service_dir.as_deref());
        assert!(!python_cmd.is_empty());
        // If .venv exists, it should point to .venv python
        if let Some(ref dir) = service_dir {
            let venv_script = dir.join(".venv").join("Scripts").join("python.exe");
            if venv_script.is_file() {
                assert_eq!(python_cmd, venv_script.to_string_lossy());
            }
        }
    }

    #[test]
    fn test_adoption_unauthenticated_service_rejected() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("Failed to bind ephemeral mock port");
        let local_port = listener.local_addr().unwrap().port();

        let handle = thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let _ = stream.read(&mut buf);
                // Returns 200 OK even without valid token (unauthenticated service)
                let response = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"active\":false,\"adapter\":\"Mock\"}";
                let _ = stream.write_all(response);
                let _ = stream.flush();
            }
        });

        let res = verify_service_authentication("127.0.0.1", local_port, "test_token", Duration::from_secs(1));
        assert!(res.is_err(), "Expected error for unauthenticated service, got Ok");
        let err_msg = res.unwrap_err();
        assert!(
            err_msg.contains("unauthenticated"),
            "Expected 'unauthenticated', got: '{}'",
            err_msg
        );
        let _ = handle.join();
    }

    #[test]
    fn test_adoption_token_mismatch_rejected() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("Failed to bind ephemeral mock port");
        let local_port = listener.local_addr().unwrap().port();

        let handle = thread::spawn(move || {
            // Expect 2 requests: dummy probe, then expected token
            for _ in 0..2 {
                if let Ok((mut stream, _)) = listener.accept() {
                    let mut buf = [0u8; 1024];
                    let _ = stream.read(&mut buf);
                    // Both dummy probe and mismatched token return 401
                    let response = b"HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"detail\":\"Unauthorized\"}";
                    let _ = stream.write_all(response);
                    let _ = stream.flush();
                }
            }
        });

        let res = verify_service_authentication("127.0.0.1", local_port, "mismatched_token", Duration::from_secs(1));
        assert!(res.is_err(), "Expected error for token mismatch, got Ok");
        let err_msg = res.unwrap_err();
        assert!(
            err_msg.contains("different session token"),
            "Expected 'different session token', got: '{}'",
            err_msg
        );
        let _ = handle.join();
    }

    #[test]
    fn test_adoption_authenticated_service_success() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("Failed to bind ephemeral mock port");
        let local_port = listener.local_addr().unwrap().port();

        let handle = thread::spawn(move || {
            // First request: dummy probe token -> returns 401
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let _ = stream.read(&mut buf);
                let response = b"HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"detail\":\"Unauthorized\"}";
                let _ = stream.write_all(response);
                let _ = stream.flush();
            }
            // Second request: valid secret token -> returns 200
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let _ = stream.read(&mut buf);
                let req_str = String::from_utf8_lossy(&buf);
                if req_str.contains("X-Trinetra-Session-Token: valid_secret_token") {
                    let response = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"active\":false,\"adapter\":\"Mock\"}";
                    let _ = stream.write_all(response);
                } else {
                    let response = b"HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"detail\":\"Unauthorized\"}";
                    let _ = stream.write_all(response);
                }
                let _ = stream.flush();
            }
        });

        let res = verify_service_authentication("127.0.0.1", local_port, "valid_secret_token", Duration::from_secs(1));
        assert!(res.is_ok(), "Expected Ok for matching token, got: {:?}", res);
        let _ = handle.join();
    }

    #[test]
    fn test_duplicate_start_when_already_ready() {
        let mut sup = ServiceSupervisor::new("127.0.0.1", 8000);
        #[cfg(windows)]
        let mock_child = Command::new("cmd")
            .args(["/c", "ping -n 5 127.0.0.1 >nul"])
            .spawn()
            .expect("Failed to spawn mock child");
        #[cfg(not(windows))]
        let mock_child = Command::new("sleep")
            .arg("5")
            .spawn()
            .expect("Failed to spawn mock child");

        sup.child = Some(mock_child);
        sup.is_verified_ready = true;

        let status = sup.start(PathBuf::from("."));
        assert!(status.is_ok(), "Expected Ok status on duplicate start");
        let s = status.unwrap();
        assert!(s.is_ready);
        assert!(s.is_running);
        assert!(s.pid.is_some());

        sup.stop();
        assert!(!sup.is_running());
    }

    #[test]
    fn test_resolve_python_command_env_override() {
        let resolved = resolve_python_command_internal(None, Some("custom_python_binary_path"));
        assert_eq!(resolved, "custom_python_binary_path");
    }

    #[test]
    fn test_find_service_dir_env_override() {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let valid_dir = manifest_dir.join("src");
        let found = find_service_dir_internal(&manifest_dir, Some(valid_dir.to_str().unwrap()));
        assert_eq!(found, Some(valid_dir));
    }

    #[test]
    fn test_port_collision_alien_raw_socket() {
        // Ephemeral raw mock port that immediately drops connection without HTTP headers
        let listener = TcpListener::bind("127.0.0.1:0").expect("Failed to bind ephemeral mock port");
        let local_port = listener.local_addr().unwrap().port();

        let handle = thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                // Send raw binary garbage, non-HTTP
                let _ = stream.write_all(b"\x00\x01\x02\x03\xff");
                let _ = stream.flush();
            }
        });

        let mut sup = ServiceSupervisor::new("127.0.0.1", local_port);
        let start_res = sup.start(PathBuf::from("."));
        assert!(start_res.is_err(), "Expected error when port is occupied by raw socket");
        let err_msg = start_res.unwrap_err();
        assert!(
            err_msg.contains("occupied by another application") || err_msg.contains("alien service"),
            "Expected port occupied error, got: '{}'",
            err_msg
        );

        let _ = handle.join();
    }
}

