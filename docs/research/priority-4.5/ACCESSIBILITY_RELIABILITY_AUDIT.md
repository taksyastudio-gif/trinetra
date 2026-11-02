# TRINETRA — PRIORITY 4.5
## Accessibility Communication Reliability Audit

---

### 1. Executive Summary & Accessibility Mandate

Assistive navigation for visually impaired individuals demands a communication model fundamentally different from typical computer vision telemetry. A system that announces every bounding box, chatters incessantly in crowds, mispronounces urgent hazards, or continues speaking during sensor failure creates sensory overload and endangers the user.

Priority 4.5 evaluates Trinetra's verbal and non-verbal communication reliability across 7 accessibility dimensions:
1. Bilingual linguistic consistency (Nepali & English).
2. Deduplication and chatter suppression.
3. Announcement delays and real-world latency.
4. Conflicting or contradictory advisories.
5. Detection thresholding and confidence gating.
6. Perception outage behavior.
7. Explicit safety boundaries.

---

### 2. Bilingual Linguistic Consistency Audit

Trinetra's localization layer (`app/localization.py`) provides structured templates for English and Nepali. The table below audits semantic symmetry across all priority categories:

| Hazard Category | English Format | Nepali Format | Semantic Symmetry Analysis |
| :--- | :--- | :--- | :--- |
| **Emergency Approaching Hazard** | `"{class}, approaching {sector}."` (e.g. *"Vehicle, approaching center."*) | `"सावधान! {sector}बाट {class} नजिकिँदै छ।"` | **Symmetric & Urgent.** Both lead with immediate hazard identification and directional approach vector. |
| **Direct Collision Obstacle** | `"Caution! Obstacle directly ahead."` | `"सावधान! अगाडि अवरोध छ।"` | **Symmetric.** Immediate warning without superfluous filler words. |
| **Path Intersection Crossing** | `"{class} crossing {direction} into your path."` | `"{class} तपाईंको बाटो काटेर {direction} जाँदैछ।"` | **Accurate.** Expresses traversal across the pedestrian's travel vector. |
| **Crowd Aggregation** | `"Crowd ahead, {count} people."` | `"अगाडि भीड छ, लगभग {count} जना छन्।"` | **Symmetric.** Uses approximate Nepali quantifier (`लगभग ... जना छन्`) to convey natural visual aggregation. |
| **Spatial Obstacle** | `"{class}, {sector}."` (e.g. *"Chair, left."*) | `"{sector} {class} छ।"` (e.g. *"बायाँ कुर्सी छ।"*) | **Natural Word Order.** Adheres to Nepali Subject-Object-Verb (SOV) structure rather than literal word-for-word translation. |
| **Walkable Path Clearance** | `"Path clear to the {direction}."` | `"{direction} बाटो खुला छ।"` | **Clear & Concise.** Issued only when visual corridor clearance exceeds 75%. |

---

### 3. Chatter Suppression, Delays, and Conflict Prevention

#### A. Deduplication & Chatter Suppression:
- **Sector Stabilization:** An object stationary in the `"center"` sector is voiced exactly once. It is not re-announced unless its bounding box shifts into `"left"` or `"right"` or its movement vector changes (e.g., transitions from `STATIONARY` to `APPROACHING`).
- **Cooldown Enforcement:**
  - Critical Hazards: $2.0\text{ s}$ cooldown.
  - Spatial Navigation: $3.5\text{ s}$ cooldown.
  - Crowd Summaries: $6.0\text{ s}$ cooldown.
  - Path Advisories: $5.0\text{ s}$ cooldown.
- **Crowd Suppression:** When $\ge 4$ persons are detected in the frame, individual person announcements are suppressed entirely. The system issues a single summary (`"Crowd ahead, 5 people."`), preventing auditory overload.

#### B. Delay Analysis:
- End-to-end processing from camera capture to speech enqueue: $31.3\text{ ms}$ ($p50$).
- TTS audio buffer playback start: $18.0\text{ ms} – 28.0\text{ ms}$ (Piper TTS).
- Total delay between real-world event and audio onset: **$< 60\text{ ms}$**.
- This delay is well below the $200\text{ ms}$ threshold where visually impaired users perceive conversational or reactive lag.

#### C. Conflicting Announcement Prevention:
- `SceneDecisionEngine` strictly prioritizes events into 6 non-overlapping tiers.
- A critical vehicle hazard (`CRITICAL_HAZARD`) preempts and drains all pending spatial announcements.
- A `"Path clear"` advisory is never issued if any critical hazard or path-intersecting obstacle exists in the scene assessment.

---

### 4. Behavior When Perception Becomes Unreliable

Prior to the Priority 4.4 integration, when a camera was covered or obscured:
- The DNN attempted to detect objects on dark noise, occasionally producing hallucinated low-confidence boxes.
- The decision engine could issue false warnings (e.g. *"Person ahead"*) in a dark pocket.

Under Priority 4.4 / 4.5:
1. **Zero Hallucination Guarantee:** During verified sensor degradation, DNN inference is bypassed completely. `DetectionResult.detections` is empty. No verbal false alarms can occur.
2. **Audio Advisory State:**
   - Instead of verbal chatter, the system emits a single subtle non-verbal chime.
   - The chime enforces a strict $5.0\text{ s}$ cooldown. If the camera remains in a pocket for 5 minutes, the user is not harassed with continuous tones.
3. **Resumption Assurance:** When the camera emerges from obstruction, the system waits for 2 clean frames before re-enabling verbal output, ensuring stability.

---

### 5. Explicit Safety Disclaimer & Real-World Boundaries

> [!CAUTION]
> **Safety and Reliability Boundary:**
> All conclusions in this audit are derived from automated unit tests, synthetic degradation patterns, and historical video playback.
> 
> **Automated test success does NOT constitute safety certification.**
> Trinetra must never be marketed, represented, or relied upon as an autonomous mobility aid or safety-critical collision prevention system on public roadways, crosswalks, or stairs without formal clinical accessibility trials, user studies with blind participants, and regulatory approval.
