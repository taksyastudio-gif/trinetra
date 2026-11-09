"""
Trinetra Wearable Smart Glasses / Embedded Camera Pipeline
==========================================================
Demonstrates how to hook an external camera (OpenCV webcam, Raspberry Pi Camera,
or wearable smart glasses) to continuously send frames or poll Trinetra
for obstacle navigation and two-way sign language translation.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "trinetra-core"))

from trinetra_core import TrinetraClient


def run_wearable_loop():
    client = TrinetraClient(base_url="http://127.0.0.1:8000")
    print("=====================================================")
    print("  TRINETRA WEARABLE ASSISTIVE LOOP RUNNING")
    print("=====================================================")

    # Announce glasses activation in Nepali
    client.speak("स्मार्ट चस्मा क्यामेरा सक्रिय भयो। बाटो हेर्दैछ।")

    last_gesture = None
    try:
        while True:
            # Poll latest engine state (obstacles, hazards, signs)
            state = client.get_latest_detections()

            # 1. Check for real-time sign language gestures
            sign = state.get("sign_gesture")
            if sign and sign.get("detected") and sign.get("gesture_type") != last_gesture:
                last_gesture = sign.get("gesture_type")
                first_person = sign.get("first_person_ne", sign.get("message"))
                print(f"🤟 Detected Gesture [{last_gesture}]: {first_person}")
                # Speaks automatically if auto-announce is on

            # 2. Check for ground hazards (potholes, open drains, breaks)
            hazard = state.get("ground_hazard")
            if hazard and hazard.get("detected"):
                print(f"⚠️ Ground Hazard: {hazard.get('message')}")

            # 3. Check for automatic in-hand currency notes
            currency = state.get("auto_currency")
            if currency and currency.get("status") == "identified":
                print(f"💵 Banknote: {currency.get('message')}")

            time.sleep(0.1)  # 10 Hz loop
    except KeyboardInterrupt:
        print("\nStopping wearable client.")
        client.speak("प्रणाली बन्द गरियो।")


if __name__ == "__main__":
    run_wearable_loop()
