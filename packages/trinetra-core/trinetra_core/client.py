"""
Trinetra Universal Integration Client (Python SDK)
==================================================
Empowers external developers, robotics engineers, and researchers to integrate
Trinetra's assistive vision, banknote recognition, Devanagari OCR, and Nepali TTS
with minimal boilerplate code.

Example Usage:
--------------
from trinetra_core.client import TrinetraClient

client = TrinetraClient(base_url="http://127.0.0.1:8000")

# 1. Announce speech in Nepali
client.speak("नमस्ते हजुर! म त्रिनेत्र प्रणाली हुँ।")

# 2. Identify in-hand currency note
with open("note.jpg", "rb") as f:
    result = client.identify_currency(f.read())
    print("Detected note:", result.get("message"))

# 3. Read Devanagari signboard text
with open("signboard.jpg", "rb") as f:
    text = client.read_text(f.read())
    print("Extracted text:", text.get("text"))
"""

import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


class TrinetraClient:
    """Universal lightweight Python client for Trinetra Vision Engine."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", session_token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.session_token = session_token

    def _request(self, endpoint: str, method: str = "GET", data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.session_token:
            headers["Authorization"] = f"Bearer {self.session_token}"

        body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Trinetra API Error [{exc.code}]: {err_body}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Could not connect to Trinetra engine at {self.base_url}: {exc.reason}") from exc

    def check_health(self) -> Dict[str, Any]:
        """Returns engine status and service version."""
        return self._request("/api/health")

    def speak(self, text: str, priority: str = "spatial_navigation", interrupt: bool = True, language: str = "ne") -> Dict[str, Any]:
        """Dispatches spoken announcement via local offline Piper TTS."""
        return self._request("/api/speech/announce", method="POST", data={
            "text": text,
            "priority": priority,
            "interrupt": interrupt,
            "language": language
        })

    def stop_speech(self) -> Dict[str, Any]:
        """Immediately silences any active TTS speech output."""
        return self._request("/api/speech/stop", method="POST")

    def get_latest_detections(self) -> Dict[str, Any]:
        """Fetches the latest real-time spatial obstacles, ground hazards, and sign gestures."""
        return self._request("/api/detection/latest")

    def set_auto_currency(self, enabled: bool) -> Dict[str, Any]:
        """Enables or disables automatic hands-free banknote recognition."""
        return self._request("/api/currency/auto-mode", method="POST", data={"enabled": enabled})

    def identify_currency(self, jpeg_bytes: Optional[bytes] = None, speak: bool = True) -> Dict[str, Any]:
        """Identifies Nepali banknote from JPEG bytes or current camera frame."""
        # If no bytes provided, triggers active camera frame identify
        return self._request("/api/currency/identify", method="POST", data={"speak": speak})

    def read_text(self, speak: bool = True) -> Dict[str, Any]:
        """Performs offline Devanagari/English OCR on the active camera view."""
        return self._request("/api/ocr/read", method="POST", data={"speak": speak})

    def query_scene(self, question: str = "के छ?", speak: bool = True) -> Dict[str, Any]:
        """Generates grounded scene description of the environment."""
        return self._request("/api/scene/query", method="POST", data={"question": question, "speak": speak})
