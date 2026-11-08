# TRINETRA (त्रिनेत्र) — Safety Boundaries, Disclaimers & Tradeoff Register
### आधिकारिक सुरक्षा घोषणा तथा प्राविधिक सीमाहरू (Bilingual: English + नेपाली)

---

## खण्ड १: नेपाली आधिकारिक सुरक्षा घोषणा (Official Nepali Disclaimer)

> ### ⚠️ महत्वपूर्ण सुरक्षा सूचना (Critical Notice)
> **त्रिनेत्र (TRINETRA) एक प्रयोगात्मक सहायक प्रविधि (Assistive Technology) मात्र हो। यो कुनै प्रमाणित चिकित्सा उपकरण (Medical Device), जीवनरक्षक प्रणाली, वा सेतो छडीको विकल्प होइन।**

### १. सेतो छडी र मार्गदर्शकको अनिवार्य नियम
- दृष्टिविहीन तथा न्यून दृष्टियुक्त महानुभावहरूले हिंडडुल गर्दा आफ्नो **सेतो छडी (Long White Cane)**, मार्गदर्शक कुकुर वा व्यक्तिगत गतिशीलता तालिमलाई कहिल्यै त्याग्नु हुँदैन।
- भुइँको सतह, खाल्डाखुल्डी, खुड्किला तथा खुला नालीको भौतिक पहिचान गर्न सेतो छडी नै प्रमुख र भरपर्दो साधन हो। त्रिनेत्रले केवल क्यामेराको दृश्य दायरामा देखिएका वस्तुहरूको अतिरिक्त सूचना मात्र दिन्छ।

### २. हामीले दाबी नगर्ने कुराहरू (Honest AI Principles)
- **कुनै स्वचालित एम्बुलेन्स कल हुँदैन:** त्रिनेत्रले आफै अस्पताल वा एम्बुलेन्स बोलाउँदैन; यसले पूर्व-स्वीकृत पारिवारिक हेरचाहकर्तालाई मात्र सिमकार्ड-आधारित एसएमएस पठाउँछ।
- **पूर्ण सुरक्षा ग्यारेन्टी छैन:** क्यामेराको कोण, तीव्र घाम, अँध्यारो वा धूलोका कारण कुनै अवरोध छुट्न सक्छ। त्यसैले प्रणालीले बाटो "पूर्ण सुरक्षित छ" भनेर कहिल्यै घोषणा गर्दैन।
- **१० सेकेन्डको रद्द गर्ने समय:** यदि अचानक लडेको वा आपतकालीन अवस्था अनुमान गरिएमा, सन्देश पठाउनु अघि प्रयोगकर्तालाई १० सेकेन्डसम्म अडियो चेतावनी दिइन्छ र रोक्ने (Cancel) पूर्ण अधिकार हुन्छ।

---

## SECTION 2: English Safety Boundaries & Capabilities Register

### 1. Assistive Orientation Aid Classification
TRINETRA is classified as a low-risk, supplemental sensory enhancement application designed to elevate environmental awareness. It is explicitly NOT:
- A medical diagnostic or therapeutic device.
- A navigational clearance autopilot.
- A replacement for human vigilance, orientation & mobility (O&M) instruction, or white cane ground contact.

### 2. Autonomy Level Governance (L0 – L4)

| Level | Classification | Behavior & Safety Constraints |
|---|---|---|
| **L0** | **Inform Only** | Raw perception and spatial audio readout. Zero proactive intervention. |
| **L1** | **Suggest** | Provides contextual advice (e.g., "बायाँ बाटो खुला देखिन्छ") when asked. |
| **L2** | **Act After Confirmation** *(Default)* | Requests verbal or button confirmation before storing bookmarks or executing changes. |
| **L3** | **Pre-Approved Routines** | Delivers scheduled medication prompts, inactivity check-ins, and BS date alerts without prompting. |
| **L4** | **Emergency Protocol** | Triggers SIM-based SMS alert with location to family upon verified fall or panic gesture, preceded by an audible 10-second cancel window. |

---

## SECTION 3: False-Positive vs. False-Negative Engineering Tradeoff Register

In assistive navigation for high-stakes urban environments like Kathmandu, the penalty of a **False Negative (missed hazard)** is vastly higher than that of a **False Positive (annoying but harmless alert)**. Below is our formal engineering calibration register:

| Hazard Category | Target Metric Priority | Acceptable FP Rate | Engineering Justification |
|---|---|---|---|
| **Open Drains / Manholes** | High Recall ($\ge 95\%$) | $\le 1$ alert / 200m | A single missed open drainage grate can cause life-threatening trauma. A false alarm causes the user to sweep their cane cautiously, preserving physical safety. |
| **Dangling Overhead Wires** | High Recall ($\ge 90\%$) | $\le 2$ alerts / km | Sagging telecommunications and optical fiber cables across Kathmandu sidewalks pose serious strangulation or eye-injury risks that white canes cannot detect. Low-confidence overhead lines are announced with soft advisory tones. |
| **Moving Micro-Buses / Tempos** | High Precision ($\ge 90\%$) | Low FP (< 5%) | Alert fatigue: Announcing stationary parked vehicles as approaching hazards desensitizes users. Temporal optical flow tracking ensures only moving vehicles on collision paths trigger urgency. |
| **NPR Currency Identification** | High Precision ($\ge 98\%$) | Zero FP tolerance | Financial exploitation protection: A user must never be told a Rs 20 note is Rs 500. Under bad lighting or occlusion, the system outputs "अनिश्चित; नोट सिधा पार्नुहोस्" (Uncertain) rather than guessing. |
| **Fall Detection** | Balanced Recall & Precision | $\le 0.1$ false/day | Sudden phone drops or sitting down abruptly must not spam caregivers. Dual-stage detection (Freefall $\Delta a$ + high-g impact + 10s immobility + 10s audible cancellation window) filters false alarms. |

---

## SECTION 4: Cryptographic Tamper-Evident Audit Trail
To protect user rights and enable post-incident reviews without compromising privacy:
1. Every autonomous action, battery degradation, and emergency dispatch is recorded into a local SQLite ledger (`audit_log`).
2. Each log entry is cryptographically sealed with a **SHA-256 hash chain** ($H_i = \text{SHA256}(H_{i-1} \parallel \text{Entry}_i)$).
3. The ledger is stored 100% locally on the device, reviewable by the user or family, and protected against retro-active alteration.
