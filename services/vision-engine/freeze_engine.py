"""Build script to freeze services/vision-engine into an onedir distribution via PyInstaller."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
TAURI_BIN_DIR = ROOT_DIR / "apps" / "desktop" / "src-tauri" / "binaries"


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
    ]

    if runtime_dir.is_dir():
        cmd.append(f"--add-data={runtime_dir}{sep}runtime")

    cmd.extend([
        "--collect-all=uvicorn",
        "--collect-all=fastapi",
        "--collect-all=torch",
        "--collect-all=torchvision",
        "--collect-all=trinetra_core",
        "--hidden-import=engineio.async_drivers.asgi",
        "--hidden-import=app.main",
        "--hidden-import=app.capabilities",
        "--hidden-import=app.localization",
        "--hidden-import=app.culture",
        "--hidden-import=app.qr_payment",
        "--hidden-import=app.assistant",
        "--hidden-import=app.ocr_enhancer",
        "--hidden-import=app.detection.native_engine",
        "--hidden-import=app.detection.model",
        "--hidden-import=app.detection.engine",
        str(entry_script),
    ])

    print("=" * 65)
    print("  FREEZING TRINETRA VISION ENGINE (Native PyInstaller)")
    print("=" * 65)
    res = subprocess.run(cmd, cwd=str(BASE_DIR))
    if res.returncode != 0:
        print("PyInstaller build failed!", file=sys.stderr)
        sys.exit(res.returncode)

    print("\nPyInstaller build succeeded!")
    output_dir = DIST_DIR / "trinetra-vision-engine"
    output_exe = output_dir / ("trinetra-vision-engine.exe" if sys.platform.startswith("win") else "trinetra-vision-engine")
    print(f"Output binary: {output_exe} (exists: {output_exe.is_file()})")

    # Sync to Tauri external binaries directory
    if output_exe.is_file():
        TAURI_BIN_DIR.mkdir(parents=True, exist_ok=True)
        dest_exe = TAURI_BIN_DIR / output_exe.name
        dest_gnu = TAURI_BIN_DIR / "trinetra-vision-engine-x86_64-pc-windows-gnu.exe"
        dest_msvc = TAURI_BIN_DIR / "trinetra-vision-engine-x86_64-pc-windows-msvc.exe"

        print(f"Deploying binary to Tauri: {dest_exe}")
        shutil.copy2(output_exe, dest_exe)
        shutil.copy2(output_exe, dest_gnu)
        shutil.copy2(output_exe, dest_msvc)

        # Remove unvetted native C-extensions that trigger Windows Smart App Control (SAC)
        for pattern in ["markupsafe/_speedups*.pyd", "websockets/speedups*.pyd"]:
            for pyd_file in (output_dir / "_internal").glob(pattern):
                try:
                    pyd_file.unlink()
                    print(f"Removed SAC trigger: {pyd_file.name}")
                except Exception as e:
                    print(f"Warning removing {pyd_file}: {e}")

        # Copy _internal directory
        internal_src = output_dir / "_internal" 
        if internal_src.is_dir():
            internal_dest = TAURI_BIN_DIR / "_internal"
            if internal_dest.exists():
                shutil.rmtree(internal_dest)
            shutil.copytree(internal_src, internal_dest)
            print("Deployed _internal dependencies to Tauri.")

    print("=" * 65)
    print("  FREEZE & SYNC COMPLETE!")
    print("=" * 65)


if __name__ == "__main__":
    build()
