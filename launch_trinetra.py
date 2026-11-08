import os
import subprocess
import sys
import time
import urllib.request

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(ROOT_DIR, "services", "vision-engine")
VENV_PYTHON = os.path.join(ENGINE_DIR, ".venv", "Scripts", "python.exe")
PYTHON_EXE = VENV_PYTHON if os.path.isfile(VENV_PYTHON) else sys.executable

# 1. Start Vision Engine silently without console window
engine_proc = subprocess.Popen(
    [
        PYTHON_EXE,
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        ENGINE_DIR,
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ],
    cwd=ENGINE_DIR,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
)

# 2. Wait for health check to confirm server is ready
for _ in range(40):
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/health")
        with urllib.request.urlopen(req, timeout=1) as resp:
            if resp.status == 200:
                break
    except Exception:
        time.sleep(0.2)

# 3. Find Edge or Chrome to run in standalone App Mode
browser_candidates = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

browser_exe = None
for candidate in browser_candidates:
    if os.path.isfile(candidate):
        browser_exe = candidate
        break

profile_dir = os.path.join(
    os.environ.get("LOCALAPPDATA", ROOT_DIR), "Trinetra", "AppProfile"
)
os.makedirs(profile_dir, exist_ok=True)

if browser_exe:
    # Open as pure standalone desktop app window (no address bar, no tabs)
    try:
        subprocess.run(
            [
                browser_exe,
                "--app=http://127.0.0.1:8000",
                "--window-size=1040,820",
                f"--user-data-dir={profile_dir}",
                "--class=TrinetraAssistive",
            ]
        )
    except Exception:
        pass
else:
    import webbrowser
    webbrowser.open("http://127.0.0.1:8000")
    try:
        engine_proc.wait()
    except KeyboardInterrupt:
        pass

# 4. Clean shutdown: terminate background engine when app window is closed
try:
    engine_proc.terminate()
    engine_proc.wait(timeout=3)
except Exception:
    try:
        engine_proc.kill()
    except Exception:
        pass
