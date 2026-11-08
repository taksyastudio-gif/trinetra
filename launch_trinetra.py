import os
import subprocess
import sys
import time
import urllib.request

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(ROOT_DIR, "services", "vision-engine")
VENV_PYTHON = os.path.join(ENGINE_DIR, ".venv", "Scripts", "python.exe")
PYTHON_EXE = VENV_PYTHON if os.path.isfile(VENV_PYTHON) else sys.executable


def is_engine_running() -> bool:
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/health")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_engine_if_needed():
    if is_engine_running():
        return None

    proc = subprocess.Popen(
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

    # Wait up to 10 seconds for the engine to initialize
    for _ in range(50):
        if is_engine_running():
            break
        time.sleep(0.2)

    return proc


def launch_browser_app():
    browser_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    browser_exe = next((b for b in browser_candidates if os.path.isfile(b)), None)

    profile_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", ROOT_DIR), "Trinetra", "AppProfile"
    )
    os.makedirs(profile_dir, exist_ok=True)

    if browser_exe:
        subprocess.Popen(
            [
                browser_exe,
                "--app=http://127.0.0.1:8000",
                "--window-size=1040,820",
                f"--user-data-dir={profile_dir}",
                "--class=TrinetraAssistive",
            ]
        )
    else:
        import webbrowser

        webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    start_engine_if_needed()
    if "--no-browser" not in sys.argv:
        launch_browser_app()
