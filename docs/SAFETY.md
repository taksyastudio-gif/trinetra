# Trinetra Safety Disclaimer and Operating Guidelines

## ⚠️ Critical Safety Notice

**Trinetra is an experimental assistive awareness prototype, NOT a certified medical device, protective equipment, or mobility aid.**

It is designed to supplement environmental awareness, not to guide safe travel or guarantee physical clearance.

---

## 1. Non-Negotiable Operating Principles

### A. Never Replace Traditional Mobility Aids
- **Mandatory White Cane / Guide Dog Rule:** Trinetra MUST NEVER be used as a replacement for a long white cane, guide dog, professional Orientation & Mobility (O&M) training, or human sighted guides.
- **Primary vs. Supplementary:** The user's primary physical detection tool for drop-offs, curbs, stairs, and immediate obstacles remains the white cane or guide dog. Trinetra provides supplemental contextual awareness only.

### B. The Monocular Depth Fallacy (Bounding-Box Warning)
- Surveyed open-source projects (e.g., `aid-for-blind`) frequently estimate obstacle distance by measuring 2D bounding-box pixel height.
- **Trinetra explicitly rejects this heuristic:** Monocular bounding-box estimation fails dangerously in everyday scenarios:
  - A small child or seated person produces a small bounding box, misleading naive systems into reporting them as "far away".
  - Low hazards (cables, uneven pavement, low tables) have minimal vertical height and may not trigger distance alerts.
  - Optical perspective distortion and camera tilt angles invalidate planar geometry.
- Trinetra will NEVER present monocular 2D bounding-box heuristics as certified metric distance or safe stopping thresholds.

### C. Prevention of Auditory Masking
- Blind and visually impaired pedestrians rely critically on subtle environmental auditory cues (sound of traffic flow, echolocation of walls, footsteps, approaching bicycles).
- **Audio Overload Hazard:** Continuous or loud synthesized speech masks these vital environmental cues, creating severe collision hazards.
- **Trinetra Protections:**
  - **Mandatory Cooldowns:** A 3.0-second per-object class cooldown prevents repetitive chatter while obstacles stay in view.
  - **Non-Prescriptive Vocabulary:** Spoken announcements are purely descriptive noun phrases (`"{label}, {sector}"`, e.g., "chair, center") rather than instructional commands. Trinetra will NEVER instruct the user ("Turn right", "Walk forward") or certify paths ("Clear ahead", "Safe to cross").
  - **Preemption of Non-Critical Speech:** Immediate emergency preemption terminates background informational chatter in under 150 ms when critical alerts arise.
  - **Instant User Silence:** The user can instantly kill ongoing speech with the Spacebar or toggle full audio mute with the `M` key.

### D. Qualitative Sectors vs. Path Planning
- Trinetra divides the horizontal visual field into three qualitative sectors: Left ($x < 0.33$), Center ($0.33 \le x \le 0.66$), and Right ($x > 0.66$).
- **Spatial Awareness Only:** These sectors provide orientation context regarding where an object appears in the camera frame. They do NOT calculate collision trajectories, walking paths, or obstacle clearances.
- The user's white cane remains the authoritative instrument for path clearance.

### E. Inability to Reliably Detect Drop-Offs & Negative Obstacles
- Downward elevation changes (descending stairs, subway platform edges, sidewalk curbs, potholes) are extremely difficult for forward-facing 2D cameras to segment reliably due to ground texture uniformity and perspective compression.
- Users must ALWAYS rely on the physical cane tip for surface elevation changes and drop-offs.

---

## 2. Technical Limitations & Sensor Boundaries

1. **Lighting & Optical Constraints:**
   - Deep shadows, blinding direct sunlight, backlighting, total darkness, and lens smudges can cause object detection models to miss obstacles completely or hallucinate false positives.
2. **Field of View Limitations:**
   - Standard webcams have a horizontal field of view of approximately 60°–75°. Obstacles, overhead hazards (tree branches, awnings), and lateral moving objects outside this cone are invisible to the camera.
3. **Latency & Motion Blur:**
   - Rapid head or body movement induces motion blur, degrading image sharpness and delaying detection. Rapidly approaching vehicles or bicycles cannot be tracked reliably.
4. **Software & Hardware Failure Modes:**
   - Operating system stalls, USB disconnects, battery depletion, or background process contention can freeze the video stream without immediate visual indication.

---

## 3. Mandatory Testing Protocol

---

## 4. Event-Aware Decision & Assistive Boundaries (Phase 2 Evolution)

### A. Honest AI & Sensory Boundary
Trinetra strictly distinguishes:
- **Direct Observations:** Bounding boxes and confidence scores output by the local ONNX model.
- **Estimated Persistence:** Track IDs and movement trajectory heuristics computed across consecutive frames.
- **Inferred Spatial Context:** Crowd presence, sector clearances, and path advisories.
- **Unknown Realities:** The system never fabricates safe routes when sectors are occluded or obstructed. If all sectors are blocked or evidence is inconclusive, it remains silent or issues concise cautions.

### B. Monocular Motion vs Metric Speed
Approaching movement is estimated from bounding box expansion rate over time ($\Delta h / \Delta t$) and lateral drift. This represents **apparent visual loom**, NOT calibrated physical speed or metric distance. It is designed solely for collision hazard prioritization.

### C. Incident Documentation & Non-Criminalization Safeguards
The incident snapshot feature records on-demand visual frames with SHA-256 cryptographic digests:
- **Tamper Evidence Only:** The cryptographic hash verifies that local files have not been modified post-capture. It does NOT confer legal admissibility or chain of custody in any judicial system.
- **Strict Anti-Criminalization:** Object detection is restricted to standard generic COCO classes (e.g. `person`, `car`, `motorcycle`). Trinetra contains **zero facial recognition, zero person identification, and zero criminal or suspect profiling**.

### D. Location Privacy & Anti-Hallucination
Location telemetry is disabled by default. If enabled or configured offline, coordinates are processed strictly locally. Trinetra **never guesses, fabricates, or hallucinates GPS coordinates** when hardware or satellite signals are unavailable.
- Field testing outdoors or in public transit environments is strictly prohibited until formal accessibility and safety verification protocols have been completed.
