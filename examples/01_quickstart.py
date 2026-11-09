"""
Trinetra Integration Quickstart (5 Lines of Code)
================================================
Demonstrates how easy it is to plug Trinetra's assistive intelligence
into any external Python app, robot, or custom hardware project.
"""
import sys
from pathlib import Path

# Add trinetra-core package to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "trinetra-core"))

from trinetra_core import TrinetraClient


def main():
    # 1. Connect to local Trinetra Vision Engine (runs offline on port 8000)
    client = TrinetraClient(base_url="http://127.0.0.1:8000")

    # 2. Check system status
    health = client.check_health()
    print("✓ Connected to Trinetra Engine:", health.get("service"), f"(v{health.get('version')})")

    # 3. Speak out loud in natural Nepali using offline Piper TTS
    print("🔊 Speaking announcement...")
    client.speak("नमस्ते हजुर! म त्रिनेत्र सहायक प्रणाली हुँ।")

    # 4. Turn on hands-free autonomous banknote recognition
    client.set_auto_currency(True)
    print("✓ Auto currency detection activated.")

    # 5. Fetch real-time spatial detections
    detections = client.get_latest_detections()
    print("📍 Active spatial detections:", len(detections.get("detections", [])))
    if detections.get("ground_hazard"):
        print("⚠️ Ground hazard alert:", detections["ground_hazard"]["message"])
    if detections.get("auto_currency"):
        print("💵 In-hand banknote:", detections["auto_currency"]["message"])


if __name__ == "__main__":
    main()
