<div align="center">

# 👁️ TRINETRA (त्रिनेत्र) — Assistive Vision & Navigation Platform
### *Empowering Independence Through 100% In-House, Privacy-First Assistive Intelligence*

[![Version](https://img.shields.io/badge/Release-v0.2.0-blue.svg?style=for-the-badge)](https://github.com/taksyastudio-gif/trinetra/releases)
[![Tests Passing](https://img.shields.io/badge/Automated%20Tests-320%20Passed-success?style=for-the-badge)](services/vision-engine/tests)
[![100% Offline](https://img.shields.io/badge/Cloud%20Dependencies-0%20(100%25%20Offline)-emerald?style=for-the-badge)](#)
[![Accessibility](https://img.shields.io/badge/WCAG%202.1-AAA%20Compliant-purple?style=for-the-badge)](#)
[![License](https://img.shields.io/badge/License-MIT-amber.svg?style=for-the-badge)](LICENSE)

[**🌐 Official Website & Live Portal**](https://taksyastudio-gif.github.io/trinetra) • [**⬇️ Download Windows (.exe)**](https://github.com/taksyastudio-gif/trinetra/releases/latest/download/Trinetra.exe) • [**📖 Integration Guide**](examples/README.md) • [**📜 Dataset Registry**](datasets/SOURCES.md)

</div>

---

> ⚠️ **CRITICAL SAFETY DISCLAIMER**: Trinetra is an experimental assistive research platform designed to augment, **never replace**, primary mobility aids (white cane, guide dog, orientation and mobility training, or sighted guides).

---

## 🌟 What is Trinetra?

**Trinetra** (त्रिनेत्र — "The Third Eye") is a standalone, local-first assistive computer vision platform built specifically for blind, visually impaired, deaf, and non-verbal individuals. 

Built strictly from first principles:
- **100% In-House Neural Engine (`TrinetraNet`)**: Zero proprietary YOLO weights. Zero cloud API calls. Deterministic contour topology fused with custom deep neural perception.
- **Eyes-Free Blind Accessibility**: Full audio walkthrough on launch. Single-key tactile hotkeys (`1`–`4`, `Space`, `H`).
- **Autonomous Nepali Banknote Recognition**: Hands-free detection of authentic & counterfeit notes (5, 10, 20, 50, 100, 500, 1000 NPR) with intelligent anti-spam speech debouncing.
- **Two-Way Sign Language & AAC**: Real-time sign translation into natural Nepali colloquial speech, plus speech-to-Devanagari live subtitles for deaf individuals.
- **Spatial Audio Radar & Ground Hazard Perception**: Real-time auditory obstacle panning (stereo) and pothole/open-drain drop-off warnings.

---

## 🏛 System Architecture

```
+-----------------------------------------------------------------------------------+
|                                  USER INTERFACE                                    |
|                                                                                   |
|  +-------------------------------+         +-----------------------------------+  |
|  |  React + TypeScript Host      |         |  Eyes-Free Audio & Web Audio Cues |  |
|  |  - High-Contrast WCAG AAA UI  | <=====> |  - Zero-latency acoustic earcons  |  |
|  |  - Spatial Audio Radar (HRTF) |         |  - Speech walkthrough on startup  |  |
|  |  - Two-Way Sign AAC Subtitles |         |  - Tactile hotkeys [1] [2] [3] [4]|  |
|  +---------------+---------------+         +-----------------------------------+  |
|                  |                                                                |
|                  | Local Loopback REST / WebSockets (127.0.0.1:8000)              |
|                  v                                                                |
|  +-----------------------------------------------------------------------------+  |
|  |                         LOCAL PYTHON VISION ENGINE                          |  |
|  |                                                                             |  |
|  |  +---------------------------+  +-----------------------------------------+ |  |
|  |  |   TrinetraNet (In-House)  |  |   Ground Hazard & Surface Discontinuity | |  |
|  |  |   - 10-class native model |  |   - Pothole & open drain detection      | |  |
|  |  |   - Kalman trajectory     |  |   - Contour topology gradient analysis  | |  |
|  |  +---------------------------+  +-----------------------------------------+ |  |
|  |                                                                             |  |
|  |  +---------------------------+  +-----------------------------------------+ |  |
|  |  |   Auto Currency Engine    |  |   Two-Way Sign & Gesture Interpreter    | |  |
|  |  |   - Authentic NPR notes   |  |   - Real-time gesture recognition       | |  |
|  |  |   - De-bounced voice TTS  |  |   - Colloquial Nepali first/third person| |  |
|  |  +---------------------------+  +-----------------------------------------+ |  |
|  |                                                                             |  |
|  |  +---------------------------+  +-----------------------------------------+ |  |
|  |  |   Offline Devanagari OCR  |  |   Caretaker Engine (Local SQLite)       | |  |
|  |  |   - Tesseract nep model   |  |   - Incident bookmarks & recovery       | |  |
|  |  +---------------------------+  +-----------------------------------------+ |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## ⌨️ Tactile & Voice Controls for Blind Users

Trinetra is designed to be operated **completely eyes-free** without looking at or aiming on a screen:

### 📱 Touchscreen & Gestures (Zero-Aiming on Glass)
- **Double-Tap Anywhere on Screen**: Trinetra instantly analyzes what is in front of the camera and reads text or describes the environment (*"के छ?"*).
- **Swipe Left / Right Anywhere on Screen**: Cycles between **Navigation**, **Currency/Reader**, and **Sign Language** modes with instant acoustic earcons and spoken voice announcement.
- **Voice Commands**: Say **« पैसा »** (Currency), **« के छ »** (Scene), **« पढ »** (Read text), or **« बाटो »** (Navigation) into the microphone hands-free.

### 💻 Physical Keyboard Shortcuts
| Key | Mode / Action | Spoken Feedback |
| :---: | :--- | :--- |
| **`Space`** | **Instant Scene Description** | Grounded answer to *"के छ? (What is in front?)"* |
| **`C`** | **Toggle Auto-Currency Mode** | Toggles hands-free continuous banknote scanning on/off. |
| **`1`** | **Obstacle & Path Navigation** | *"बाटो नेभिगेसन सक्रिय। / Navigation mode active."* |
| **`2`** | **Currency Recognition** | Reads in-hand banknote denomination (*"रू. १०० (एक सय)"*). |
| **`3`** | **Book & Signboard Reader (OCR)** | Reads printed text in Devanagari or English aloud. |
| **`4`** | **Two-Way Sign Language & AAC** | *"सांकेतिक भाषा अनुवादक सक्रिय। / Sign language active."* |
| **`R`** | **Spatial Audio Radar** | Stereo panning acoustic radar for obstacle proximity. |
| **`M`** | **Mute / Unmute** | Immediately stops all ongoing spoken speech output. |
| **`H`** | **Help Walkthrough** | Speaks the entire voice guide aloud anytime. |

---

## 🤟 Two-Way Sign Language & Natural Nepali Phrasing

Unlike rigid literal dictionary translators, Trinetra uses warm, polite, and authentic Nepali colloquial phrasing:

| Gesture / Symbol | When Mute User Signs (First Person) | When Opposite Person Signs (Third Person) |
| :--- | :--- | :--- |
| 🙏 **Namaste** | *"नमस्ते हजुर! सन्चै हुनुहुन्छ?"* | *"अगाडिको व्यक्तिले नमस्ते संकेत गर्नुभयो।"* |
| 💧 **Water** | *"मलाई अलिकति पिउने पानी दिनुहुन्छ कि?"* | *"अगाडिको व्यक्तिले पिउने पानी माग्नुभएको छ।"* |
| 🍲 **Food** | *"मलाई खाना अथवा खाजा खान मन लाग्यो।"* | *"अगाडिको व्यक्तिले खाना वा खाजा चाहियो भन्नुभयो।"* |
| 🆘 **Help** | *"मलाई बाटो काट्न थोरै मद्दत चाहियो, प्लिज।"* | *"अगाडिको व्यक्तिले मद्दत माग्दै हुनुहुन्छ।"* |
| ✋ **Wait** | *"एकछिन रोकिनुहोस् है!"* | *"अगाडिको व्यक्तिले रोकिन संकेत गर्नुभयो।"* |
| 🤝 **Thanks** | *"धेरै धेरै धन्यवाद हजुर, आभारी छु!"* | *"अगाडिको व्यक्तिले धन्यवाद भन्नुभयो।"* |
| 🤒 **Sick** | *"मलाई एकदम सन्चो छैन, कृपया मद्दत गर्नुहोस्!"* | *"अगाडिको व्यक्ति बिरामी परेको संकेत देखियो।"* |
| 👍 **OK** | *"हुन्छ, एकदम ठीक छ!"* | *"अगाडिको व्यक्तिले हुन्छ भन्नुभयो।"* |

---

## 🚀 Quickstart & One-Click Launch

### Option 1: Standalone Direct Executable (No Python Required)
1. Download **[`Trinetra.exe`](https://github.com/taksyastudio-gif/trinetra/releases/latest/download/Trinetra.exe)** (or download the full standalone ZIP package from our [Releases](https://github.com/taksyastudio-gif/trinetra/releases)).
2. Double-click `Trinetra.exe` — the offline vision engine, accessible UI, and voice synthesizer boot up automatically.

### Option 2: Run From Source (Developers)
```powershell
# 1. Clone repository
git clone https://github.com/taksyastudio-gif/trinetra.git
cd trinetra

# 2. Start vision engine (Terminal 1)
cd services/vision-engine
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. Start accessible desktop app (Terminal 2)
cd apps/desktop
npm install
npm run dev
```

---

## 🔌 5-Line Universal Integration SDK

Any student, researcher, or roboticist can integrate Trinetra into an external project (Raspberry Pi, wearable smart glasses, ESP32-CAM, or robot) in 5 lines:

```python
from trinetra_core import TrinetraClient

# Connect to the local offline Trinetra engine
client = TrinetraClient(base_url="http://127.0.0.1:8000")

# Speak out loud in natural Nepali
client.speak("नमस्ते हजुर! म त्रिनेत्र सहायक प्रणाली हुँ।")

# Fetch real-time perception state
detections = client.get_latest_detections()
print("Banknote:", detections.get("auto_currency"))
print("Hazard:", detections.get("ground_hazard"))
```

See the [Developer Integration Guide](examples/README.md) for full REST and Python examples.

---

## 🧪 Comprehensive Automated Verification

Trinetra includes a comprehensive offline test suite covering perception, de-bouncing, rate-limiting, and error boundaries:

```powershell
python -m pytest services/vision-engine/tests -v
```
**Current Status**: `320 passed, 1 skipped, 0 failures` (Verified on Python 3.13 / Windows).

---

## 📜 License & Provenance
Trinetra is distributed under the **MIT License**. All neural model architectures, speech normalization logic, and spatial perception code are 100% in-house. External training datasets are cataloged in [`datasets/SOURCES.md`](datasets/SOURCES.md).
