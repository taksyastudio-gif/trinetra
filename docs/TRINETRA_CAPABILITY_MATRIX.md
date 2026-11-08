# TRINETRA (त्रिनेत्र) v2 — Product Capability Matrix
**Milestone:** Uniglobe Young Scientist Summit 3.0 (UYSS 2026), Project CS-12  
**Architecture:** v2 Nepal-Native Semi-Autonomous Digital Caretaker  
**Updated:** November 2026  
**Honesty Standard:** Features are explicitly tagged as **Operational (Production-Grade)**, **Prototype (Bounded Scope)**, or **Out-of-Scope / Excluded by Design**.

---

## 1. Vision & Spatial Hazard Perception

| Capability | Scope / Implementation | Operational Level | Notes & Safety Boundaries |
| :--- | :--- | :--- | :--- |
| **Real-Time Object Detection** | YOLOX-Nano ONNX (CPU inference: ~35-50ms) | **Operational** | Detects people, vehicles, obstacles; maps into Left / Center / Right sectors. |
| **Nepal Hazard Taxonomy Mapping** | 10 Localized classes (open drain, pothole, tempo, etc.) | **Operational** | Maps general COCO predictions to genuine Kathmandu street hazards. |
| **Dangling Overhead Wire Detection** | Canny edge + probabilistic Hough transform in upper 35% clearance zone | **Operational** | Detects low sagging cables (<2.1m) in 5.1ms on CPU with high recall. |
| **Ground Discontinuity Detection** | Texture gradient & edge boundary analyzer | **Operational** | Alerts on potholes, curbs, steps down ("अगाडि जमिनमा खाल्डो छ"). |
| **Optical Flow Ego-Motion** | Lucas-Kanade sparse feature tracking | **Operational** | Compensates for camera bearer walking motion. |
| **Face Detection & Recognition** | OpenCV YuNet detector + Cosine embedding | **Operational** | Local consent-based recognition of trusted family/caregivers only. |
| **Night Vision / Infrared** | Standard visible spectrum only | *Out-of-Scope* | Relies on ambient illumination or external torch; no thermal IR. |

---

## 2. Reading, Transit & Financial Autonomy

| Capability | Scope / Implementation | Operational Level | Notes & Safety Boundaries |
| :--- | :--- | :--- | :--- |
| **Devanagari OCR & Signboards** | Tesseract 5 with trained Nepali (`nep.traineddata`) | **Operational** | Reads signboards, medicine labels, documents; outputs spoken Devanagari. |
| **Public Transit & Bus Board Matching** | Fuzzy Devanagari transit hub matcher (`BusRouteMatcher`) | **Operational** | Matches hand-painted transit signs to Kathmandu routes (Ratna Park, Lagankhel, Sajha). |
| **NPR Banknote Recognition** | Custom ONNX currency classifier (`models/currency/v1/`) | **Operational** | Identifies Rs 5, 10, 20, 50, 100, 500, 1000 notes in worn/folded condition with confidence gate (>0.65). |
| **Retail QR Payment Readout** | Pure offline EMVCo QR parser (`QRPaymentService`) | **Operational** | Decodes FonePay, eSewa, Khalti, and NepalQR standees and speaks merchant name. |
| **Cash Calculation & Change** | Interactive accumulator in desktop/mobile UI | **Operational** | Keeps running balance for marketplace transactions; calculates remaining change. |
| **Counterfeit Note Detection** | Surface color/pattern only | *Out-of-Scope* | Does NOT inspect UV watermark, magnetic ink, or security threads. |

---

## 3. Voice, Language & Cultural Integration

| Capability | Scope / Implementation | Operational Level | Notes & Safety Boundaries |
| :--- | :--- | :--- | :--- |
| **Nepali Neural TTS** | Piper TTS (`ne_NP-google-x_low.onnx`) | **Operational** | High-fidelity offline Devanagari neural synthesis on CPU with pre-rendered safety fast-path. |
| **Dynamic Speech Rate Scaling** | Pacing control from 0.5x to 2.5x (`SpeechManager`) | **Operational** | Piper `length_scale` adjustment for elderly (slower) and power users (faster). |
| **Traffic Noise Preprocessor** | 1st-order IIR high-pass (<200Hz) + spectral subtraction | **Operational** | Filters Kathmandu diesel micro-bus rumble and ambient din without external DSP. |
| **Offline Speech Recognition (STT)** | Local VAD + Acoustic Signature Classifier | **Operational** | Triggers on core commands: "पैसा", "के छ", "पढ", "याद राख", "चुप", "मद्दत". |
| **Bikram Sambat Calendar & Festivals** | Calibrated AD-to-BS date engine (`BikramSambatConverter`) | **Operational** | Formats Devanagari dates, weekdays, and active festivals (Dashain, Tihar, Chhath). |
| **Code-Switching Interpreter** | Mixed Nepali/English/Romanized parser (`CodeSwitchingInterpreter`) | **Operational** | Handles "aaja ko date", "aushadhi time", "paisa kati ho", "lost", "emergency". |
| **Sign Language Recognition** | Bounded geometric contour & defect classifier | **Prototype** | **Bounded vocabulary (Help, Water, Food, Thanks, Sick, Namaste, Stop).** Disclaims full NSL dictionary coverage. |
| **Live Subtitle Bridge & Non-Verbal AAC** | Visual subtitle cards + symbol soundboard | **Operational** | Instant accessible communication for deaf and non-verbal participants. |

---

## 4. Caretaker Engine & Autonomy Governance

| Capability | Scope / Implementation | Operational Level | Notes & Safety Boundaries |
| :--- | :--- | :--- | :--- |
| **Local Context Memory** | SQLite with SHA-256 hash chaining (`ContextMemory`) | **Operational** | Stores contacts, places, routines, and tamper-evident audit logs locally. |
| **Graded Autonomy Supervisor** | L0 (Inform) to L4 (Emergency) state machine | **Operational** | Governs pre-approved routines, user confirmations, and emergency escalation. |
| **Fall & Inactivity Detection** | IMU acceleration threshold + optical flow collapse | **Operational** | Detects freefall impact and prolonged immobility during waking hours. |
| **10-Second Audible Pre-Alert Window** | Audible countdown before family notification | **Operational** | Gives user 10 seconds to cancel false alarms via voice or tap before SMS dispatch. |
| **Caregiver SMS Link** | SIM-based cellular SMS protocol (`CaregiverLink`) | **Operational** | Dispatches emergency coordinates without requiring internet or data plans. |
| **Autonomous Rescue Guarantee** | Restricted by architectural philosophy | *Excluded by Design* | Does NOT promise automated ambulance dispatch; alerts family caregivers. |

---

## 5. Supported Hardware, HAL & Device Health

| Hardware / Platform | Supported Adapter | Operational Status | Notes & Power Governance |
| :--- | :--- | :--- | :--- |
| **Windows Desktop (x86_64)** | Tauri 2.0 native container + FastAPI | **Production** | Tested on Windows 10/11; low memory footprint (<220MB). |
| **Mobile PWA (Android / iOS)** | Responsive Touch/Voice Viewport + Service Worker | **Production** | 1-click install via browser Add to Home Screen; offline cache. |
| **ESP32-CAM (Wearable Module)** | HTTP MJPEG Stream Adapter + Ring Buffer | **Production** | Tested at 640x480 @ 15 FPS; auto-reconnect with exponential backoff. |
| **Smart Glasses (Reference)** | `SmartGlassesAdapter` with dual temple haptics | **Specification** | Supports directional vibration cues (turn left/right, urgent obstacle stop). |
| **Device Health & Thermal Governor** | `DeviceHealthSupervisor` with battery/temp rules | **Production** | Auto-downgrades to **LITE Mode** (5 FPS) when battery $\le 15\%$ or temp $\ge 75^\circ\text{C}$. |
