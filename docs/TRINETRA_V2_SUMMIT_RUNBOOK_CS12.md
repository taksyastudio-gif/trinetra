# TRINETRA v2 — Summit Presentation Runbook & Pitch Script
### Uniglobe Young Scientist Summit 3.0 (UYSS 2026) | Project CS-12
**Team:** TRINETRA Lead Engineering & Product Architecture  
**Allotted Time:** 3 Minutes Live Pitch + 2 Minutes Judge Q&A  
**Location:** Main Expo Arena / Computer Science Pavilion CS-12  

---

## 1. Physical Booth & Hardware Setup Checklist

Before judges visit Booth CS-12:
- [ ] **Laptop:** Windows laptop running offline vision engine (`python -m uvicorn app.main:app`) and Tauri desktop app.
- [ ] **Wearable:** Head-mounted or chest-mounted ESP32-CAM powered by 5V powerbank, streaming over local WiFi/Hotspot (`http://192.168.4.1/stream`).
- [ ] **Prop Table:**
  - 1x Long White Cane (decorated with tactile grip).
  - 3x Worn/folded Nepali banknotes (Rs 20, 100, 500).
  - 1x Laminated retail standee with FonePay / eSewa QR code.
  - 1x Hand-painted transit placard ("रत्नपार्क – साझा यातायात").
  - 1x Simulated overhead dangling black cable.
- [ ] **Audio Check:** External Bluetooth speaker or laptop speakers set to 80% volume, Piper neural TTS verified in Nepali.

---

## 2. The 3-Minute Live Summit Pitch Script

```
[0:00 – 0:35] ACT 1: THE REALITY GAP (THE "WHY")
```
*(Presenter stands with white cane in left hand, pointing laptop/wearable camera towards the floor)*

**Presenter:**  
> *"Namaste distinguished judges and scientists. Every year, global tech companies release AI glasses with shiny promises. But take those glasses onto a street in Kalanki or Ratna Park, and they immediately fall apart.  
> Why? Because they were trained on European sidewalks, Latin signs, and dollar bills. They cannot see an open drainage manhole, a sagging 33kV optical wire, a worn 50-rupee note, or a hand-painted Sajha bus board. And when the internet cuts out or the phone battery hits 10%, they become useless glass.  
> We built **TRINETRA (त्रिनेत्र)**: Nepal's first semi-autonomous, offline-first digital caretaker. It runs on ordinary laptops, budget Android phones, and low-cost 800-rupee ESP32 wearable cameras. 100% locally. Zero cloud."*

---

```
[0:35 – 1:20] ACT 2: NEPAL-NATIVE PERCEPTION IN ACTION
```
*(Presenter demonstrates live camera features on booth props)*

**Presenter:**  
> *"Watch how TRINETRA tackles the genuine Nepali environment:"*

1. **Overhead Cables & Ground Discontinuities:**  
   *(Wave simulated sagging cable in upper frame)*  
   **Trinetra (Audio in Nepali):** *"सावधान: माथि तार छ।"* (Inference: 5.1 ms on CPU).
2. **Public Transit Hubs (Bus Route OCR):**  
   *(Show hand-painted Ratna Park bus placard)*  
   **Trinetra (Audio):** *"बस गन्तव्य: रत्नपार्क, साझा यातायात।"*
3. **Financial Autonomy (Worn NPR Notes & FonePay QR):**  
   *(Hold up folded Rs 500 note, then scan retail QR)*  
   **Trinetra (Audio):** *"पाँच सय रुपैयाँ नोट... फोनपे भुक्तानी: हिमालयन बेकरी।"*

---

```
[1:20 – 2:15] ACT 3: THE SEMI-AUTONOMOUS CARETAKER & SAFETY GOVERNANCE
```
*(Presenter asks a conversational code-switched question and simulates emergency)*

**Presenter:**  
> *"TRINETRA is not just a passive tool; it is a semi-autonomous caretaker operating under an ethical L0-to-L4 autonomy model."*

1. **Code-Switched Cultural Assistant:**  
   **Presenter speaks:** *"आज कति गते हो?"*  
   **Trinetra (Devanagari):** *"आज २०८३ साल कात्तिक २२ गते, शनिबार। शुभ दिन!"*
2. **Fall Detection & Pre-Alert Window:**  
   *(Presenter gently tilts phone rapidly onto cushioned prop surface)*  
   **Trinetra (Urgent Alert):** *"चेतावनी: आपतकालीन सूचना १० सेकेन्डमा पठाइनेछ। रद्द गर्न स्क्रिन थिच्नुहोस्।"*  
   **Presenter:** *"Notice the 10-second audible cancellation window. If the user tripped harmlessly, they tap the screen or say 'म ठीक छु' (I'm OK). If they are unconscious, the timer ticks down, and an emergency SMS with coordinates is automatically sent to their family. All actions are cryptographically sealed in a local SHA-256 tamper-evident ledger."*

---

```
[2:15 – 3:00] ACT 4: HARDWARE RESILIENCE & THE ROAD AHEAD
```
*(Show live ESP32-CAM module and thermal/battery governor)*

**Presenter:**  
> *"What happens when load-shedding hits or the battery drops to 12%?  
> Our Device Health Governor automatically transitions to **LITE Mode**: throttling from 30 FPS down to 5 FPS to preserve battery life while keeping critical hazard reflexes alive.  
> TRINETRA has been rigorously benchmarked: 340 automated unit tests, 0 failures, sub-12ms hazard latency on basic CPU, and zero data leakage.  
> We are not replacing the white cane; we are giving our brothers and sisters in Nepal an intelligent, respectful digital eye. Thank you, and we welcome your questions!"*

---

## 3. Judge Q&A Defense Strategy (2 Minutes)

### Question 1: "How can you run neural models on a cheap laptop without a GPU?"
**Defense:**  
> *"We trained our localized models using quantized INT8/ONNX runtimes with structured pruning. Hazards like low-hanging wires use high-speed Canny edge and Hough line geometry executing in under 6 milliseconds. Our base detector is `trinetra_nano.onnx`, operating at 35 ms per frame on an ordinary Intel Core i5 CPU without spinning up power-hungry GPUs."*

### Question 2: "What happens if TRINETRA makes a mistake and misses an open drain?"
**Defense:**  
> *"That is our primary safety mandate (documented in `SAFETY_DISCLAIMER_NEPAL.md`). We explicitly instruct users that TRINETRA is an awareness supplement, NOT a replacement for the white cane. Surface drop-offs are always physically verified by the cane tip. Furthermore, in our engineering tradeoff register, we tune open drain detection for high recall ($\ge 95\%$), meaning the system prefers issuing a cautious advisory over missing an open hazard."*

### Question 3: "Why not use cloud models like GPT-4o or Gemini for everything?"
**Defense:**  
> *"In Nepal, mobile data costs money and 4G coverage drops the moment you enter an alley, basement market, or during power outages. Furthermore, sending a visually impaired user's live video stream to remote servers violates their personal privacy. TRINETRA operates 100% offline. We only offer Cloud Gemini as an explicit, user-consented opt-in feature for complex document reading."*

### Question 4: "What is your hardware cost?"
**Defense:**  
> *"Our software runs on any smartphone or laptop the family already owns. The optional wearable head module uses an ESP32-CAM board that costs under 1,000 Nepali Rupees (approx. $7.50 USD), compared to imported Western smart glasses that cost over $300."*
