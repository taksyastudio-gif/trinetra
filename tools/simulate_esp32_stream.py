"""
Simulated ESP32-CAM MJPEG Stream Server
========================================
Emulates an AI-Thinker ESP32-CAM running Trinetra firmware over HTTP.
Serves multipart/x-mixed-replace JPEG streams at 15 FPS on http://127.0.0.1:81/stream
and JSON telemetry on http://127.0.0.1:81/status.

Usage:
  python tools/simulate_esp32_stream.py [--port 81] [--source webcam|synth]
"""

import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging
import socketserver
import sys
import threading
import time

try:
    import cv2
    import numpy as np
except ImportError:
    print("[ERROR] OpenCV (cv2) and numpy are required. Run in .venv.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ESP32-Simulator")


class FrameGenerator:
    """Produces test JPEG frames either from a local webcam or synthetic animation."""

    def __init__(self, mode: str = "synth"):
        self.mode = mode
        self.cap = None
        self.pos_x = 50
        self.dx = 6
        if self.mode == "webcam":
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                logger.warning("Webcam not accessible, falling back to synthetic generator.")
                self.mode = "synth"

    def get_jpeg(self) -> bytes:
        if self.mode == "webcam" and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                _, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                return enc.tobytes()

        # Synthetic generator with moving simulated obstacles and timestamp
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (35, 30, 25)

        # Draw grid
        for x in (213, 426):
            cv2.line(img, (x, 0), (x, 480), (70, 70, 70), 1)

        # Labels
        cv2.putText(img, "LEFT SECTOR", (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 1)
        cv2.putText(img, "CENTER SECTOR", (245, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 1)
        cv2.putText(img, "RIGHT SECTOR", (460, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 1)

        # Simulated obstacle moving back and forth
        self.pos_x += self.dx
        if self.pos_x > 540 or self.pos_x < 50:
            self.dx = -self.dx

        cv2.rectangle(img, (self.pos_x, 180), (self.pos_x + 90, 360), (0, 165, 255), -1)
        cv2.putText(img, "OBSTACLE", (self.pos_x + 5, 275), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

        # Telemetry overlay
        now_str = time.strftime("%H:%M:%S")
        cv2.putText(img, f"ESP32-CAM RIG SIMULATOR [OV2640] - {now_str}", (20, 455),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 180), 1)

        _, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return enc.tobytes()

    def close(self):
        if self.cap:
            self.cap.release()


generator: FrameGenerator = None


class ESP32HTTPHandler(BaseHTTPRequestHandler):
    """Handles ESP32-CAM MJPEG streaming and status endpoints."""

    def log_message(self, format, *args):
        # Suppress noisy per-frame access logs
        return

    def do_GET(self):
        if self.path == "/stream":
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()

            try:
                while True:
                    frame_bytes = generator.get_jpeg()
                    self.wfile.write(b"--frame\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame_bytes)))
                    self.end_headers()
                    self.wfile.write(frame_bytes)
                    self.wfile.write(b"\r\n")
                    time.sleep(0.066)  # ~15 FPS
            except (BrokenPipeError, ConnectionResetError):
                logger.info("Client disconnected from /stream.")

        elif self.path == "/capture":
            frame_bytes = generator.get_jpeg()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame_bytes)))
            self.end_headers()
            self.wfile.write(frame_bytes)

        elif self.path in ("/status", "/"):
            payload = {
                "device": "ESP32-CAM-AI-THINKER",
                "firmware": "Trinetra-Cam v1.0",
                "uptime_seconds": round(time.time() - start_time, 1),
                "wifi_rssi": -48,
                "free_heap": 412580,
                "stream_url": f"http://{self.headers.get('Host', '127.0.0.1:81')}/stream",
                "status": "online"
            }
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404, "Not Found")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    global generator, start_time
    parser = argparse.ArgumentParser(description="Simulate ESP32-CAM MJPEG Video Stream")
    parser.add_argument("--port", type=int, default=81, help="Stream HTTP port (default: 81)")
    parser.add_argument("--source", choices=["synth", "webcam"], default="synth", help="Source frame generator")
    args = parser.parse_args()

    generator = FrameGenerator(mode=args.source)
    start_time = time.time()

    server = ThreadedHTTPServer(("127.0.0.1", args.port), ESP32HTTPHandler)
    logger.info(f"============================================================")
    logger.info(f"  ESP32-CAM Simulator Running on http://127.0.0.1:{args.port}/stream")
    logger.info(f"  Status telemetry on http://127.0.0.1:{args.port}/status")
    logger.info(f"  Source mode: {args.source}")
    logger.info(f"  Ready for Trinetra Network Stream connection testing!")
    logger.info(f"============================================================")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down ESP32 simulator.")
    finally:
        generator.close()
        server.server_close()


if __name__ == "__main__":
    main()
