"""Build script to freeze services/vision-engine into an onedir distribution via PyInstaller."""
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
SPEC_FILE = BASE_DIR / "trinetra-vision-engine.spec"

def build():
    entry_script = BASE_DIR / "run_engine.py"
    models_dir = BASE_DIR / "models"
    runtime_dir = BASE_DIR / "runtime"

    sep = ";" if sys.platform.startswith("win") else ":"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name",
        "trinetra-vision-engine",
        f"--add-data={models_dir}{sep}models",
        f"--add-data={runtime_dir}{sep}runtime",
        "--collect-all=uvicorn",
        "--collect-all=fastapi",
        "--collect-all=onnxruntime",
        "--collect-all=trinetra_core",
        "--hidden-import=engineio.async_drivers.asgi",
        "--hidden-import=app.main",
        "--hidden-import=app.capabilities",
        "--hidden-import=app.localization",
        "--hidden-import=app.culture",
        "--hidden-import=app.qr_payment",
        "--hidden-import=app.assistant",
        "--hidden-import=app.ocr_enhancer",
        str(entry_script),
    ]

    print("Running PyInstaller command:")
    print(" ".join(cmd))
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    if res.returncode != 0:
        print("PyInstaller build failed!", file=sys.stderr)
        sys.exit(res.returncode)

    print("\nPyInstaller onedir build succeeded!")
    output_exe = DIST_DIR / "trinetra-vision-engine" / ("trinetra-vision-engine.exe" if sys.platform.startswith("win") else "trinetra-vision-engine")
    print(f"Output binary: {output_exe} (exists: {output_exe.is_file()})")

if __name__ == "__main__":
    build()
