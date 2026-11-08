# TRINETRA v2: Field User-Testing Protocol (Nepal)
**Target Population:** Visually Impaired, Deaf / Hard-of-Hearing, Elderly, and Primary Caregivers  
**Institutional Partner Candidates:** Nepal Association of the Blind (NAB), Kathmandu Association of the Deaf (KAD), Laboratory School Kirtipur  
**Document Code:** TRINETRA-UTP-2026-NEPAL  
**Version:** 2.0 (Local-First Offline Architecture)

---

## 1. Objectives & Guiding Ethics

Most accessibility technologies fail when ported to South Asia because they assume structured Western sidewalks, English signage, reliable 5G, and high-end hardware.  
The objective of this field study is to measure the real-world usability, safety impact, and cognitive load of TRINETRA v2 under genuine Nepali environmental conditions.

### Core Testing Directives
1. **Never Replace the White Cane:** All mobility tests require participants with visual impairments to maintain primary cane contact at all times. TRINETRA is evaluated solely as a contextual awareness supplement.
2. **Zero Cloud Dependency:** All testing runs completely offline on local device tiers (laptop, Android phone via Hotspot, ESP32-CAM wearable). No personal data or video stream is transmitted over the internet.
3. **Inclusive Modality:** Instructions are provided in spoken Nepali (auditory), Nepali Sign Language (NSL), and plain-language printed/braille materials.

---

## 2. Participant Cohorts

| Cohort | Profile | Sample Size | Primary Workflows Evaluated |
|---|---|---|---|
| **Cohort A (Visually Impaired)** | Totally blind or low-vision students and working adults | 12–16 participants | Hazard warning (open drain, wires, potholes), Bus route board OCR, NPR cash & FonePay QR readout, Bikram Sambat date inquiry |
| **Cohort B (Deaf / Hard-of-Hearing)** | Deaf or non-verbal individuals fluent in NSL or everyday gestures | 8–10 participants | Sign-to-speech translation, Non-verbal icon AAC soundboard, visual hazard alerts |
| **Cohort C (Primary Caregivers)** | Family members or hostel wardens caring for elderly or disabled individuals | 8–10 participants | Routine medication reminders, fall alert reception via SMS, tamper-evident audit trail review |

---

## 3. Real-World Field Environments (Kathmandu Valley)

### Environment 1: Controlled Indoor Hall (Baseline Calibration)
- **Location:** NAB Multipurpose Hall / School Classroom.
- **Physical Obstacles:** Chairs, tables, narrow door frames, sudden step down.
- **Goals:** Calibrate baseline TTS speech rate (0.75x to 1.5x), verify directional haptics, test offline voice command spotting under low background noise.

### Environment 2: Urban Footpath & Mixed Transit Corridors
- **Location:** Ratna Park – New Road corridor or Kirtipur Ring Road footpath.
- **Authentic Nepali Hazards:** Broken pavement stones, open drainage grates, low sagging telecommunication cables (clearance < 2.1 m), street vendor carts, stationary motorbikes, stray dogs.
- **Goals:** Measure alert latency (target: < 150 ms), assess false-positive rate per kilometer walked, evaluate auditory masking against traffic noise.

### Environment 3: Public Transit Hub (Bus Stop)
- **Location:** Lagankhel or Kalanki micro-bus / Sajha Yatayat boarding stop.
- **Hazards & Tasks:** Hand-painted transit signs, crowded pedestrian zones, diesel engine rumble.
- **Goals:** Evaluate `BusRouteMatcher` on worn bus boards, verify `TrafficNoiseFilter` speech intelligibility.

### Environment 4: Local Retail Cash & Payment Counter
- **Location:** Kirana Pasal (neighbourhood grocery) / Fruit stall.
- **Tasks:** Identify worn/folded NPR 20, 50, 100, 500, 1000 notes; scan printed FonePay/eSewa QR standees.
- **Goals:** Measure recognition speed and accuracy without internet.

---

## 4. Structured Evaluation Tasks & Quantitative Metrics

### Task Matrix

| ID | Task Description | Success Criterion | Primary Metric |
|---|---|---|---|
| **T-01** | **Surface Hazard Warning:** Walking along uneven path with simulated/actual drain opening. | Audio warning emitted before participant reaches within 1.5 meters of obstacle. | Trigger distance (m), false alarms per 100 m |
| **T-02** | **Overhead Cable Detection:** Approaching dangling cable at head height (< 2.0 m). | Audio alert ("सावधान: माथि तार छ") delivered with > 1.0 s reaction buffer. | Cable recall %, latency (ms) |
| **T-03** | **Bus Board Reading:** Pointing camera at oncoming public vehicle signboard. | Correct transit hub spoken (e.g. "रत्नपार्क, साझा") within 2 seconds. | Transit match accuracy %, CER |
| **T-04** | **Cash & Retail QR Payment:** Identifying 5 randomized worn banknotes and 2 QR codes. | 100% correct cash identification and merchant name readout. | Denomination accuracy %, time to audio readout |
| **T-05** | **Fall Detection & Pre-Alert:** Participant tilts simulator or demonstrates controlled stumble. | Emergency pre-alert starts 10-second audible countdown; cancels on tap or voice command. | Pre-alert trigger accuracy %, cancellation usability |
| **T-06** | **Conversational Assistant:** Asking for current Bikram Sambat date or medication schedule. | Accurate Devanagari voice reply delivered locally in < 250 ms. | Intent accuracy %, participant clarity rating |

---

## 5. Subjective & Usability Assessment

At the conclusion of field testing, participants complete the **System Usability Scale (SUS)** and the **NASA Task Load Index (TLX)** adapted for accessibility:

1. **System Usability Scale (SUS):** 10 standardized questions rated 1 to 5. Target benchmark: **SUS score $\ge 82/100$**.
2. **Cognitive Load & Auditory Fatigue:**
   - Did the voice announcements feel overwhelming or interfere with hearing street traffic? (Yes / No / Just right)
   - Was the speech rate comfortable?
   - Did the 10-second emergency cancellation window feel safe and manageable?
3. **Cultural & Linguistic Authenticity:**
   - Did the Nepali phrasing sound natural and respectful (*"तपाईंको सीधा अगाडि..."*, *"कृपया समयमा औषधि लिनुहोला"*), or robotic?

---

## 6. Safety & Incident Protocol During Testing

1. **Dual Sighted Human Spotters:** Every participant navigating an outdoor route is accompanied by two trained sighted spotters walking within arm's reach (one on each side).
2. **Immediate Abort Command:** The word **"रोक" (HALT)** or physical contact immediately pauses the test.
3. **No Hazardous Live Manholes:** Tests involving open drains use simulated visual replicas or safely covered grates with clearly marked non-hazardous drop-offs.
