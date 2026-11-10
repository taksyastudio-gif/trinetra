"""
Standalone Entrypoint for Frozen PyInstaller Trinetra Vision Engine Sidecar.
Parses --host and --port, initializes create_app(), and launches Uvicorn.
"""
import argparse
import os
import sys
from pathlib import Path

# Disable unvetted native C-extensions that trigger Windows Smart App Control (SAC)
os.environ["MARKUPSAFE_NO_SPEEDUPS"] = "1"
os.environ["WEBSOCKETS_NO_EXTENSIONS"] = "1"

# In PyInstaller bundles, _MEIPASS points to the extracted bundle root
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    bundle_dir = Path(sys._MEIPASS)
else:
    bundle_dir = Path(__file__).resolve().parent

if str(bundle_dir) not in sys.path:
    sys.path.insert(0, str(bundle_dir))

import uvicorn
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description="Trinetra Vision Engine Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    args, _ = parser.parse_known_args()

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
