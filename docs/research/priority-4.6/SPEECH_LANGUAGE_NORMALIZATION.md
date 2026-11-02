# TRINETRA — PRIORITY 4.6
## Stage 2: Speech Language Normalization Audit & Implementation

---

### 1. Investigation & Audit Findings

Prior to Priority 4.6, language normalization was enforced inconsistently across the system:
- **`app/main.py` (`/api/speech/language`):** Called `normalize_language(payload.language)` prior to propagating values, canonicalizing `"ne-NP"` to `"ne"` and `"en-US"` to `"en"`.
- **`app/detection/engine.py` (`PerceptionPipeline.language` setter):** Normalized values via `normalize_language()` if supported.
- **`app/audio/speaker.py` (`SpeechManager.language` setter):** Bypassed the canonical normalization layer and stored raw lowercased strings (`value.strip().lower()`). As a result, setting `speech_manager.language = "ne-NP"` directly resulted in an internal state of `"ne-np"` rather than `"ne"`.
- **`SpeechManager.announce()`:** Did not normalize the per-request `language` argument, potentially enqueuing `SpeechItem` instances with non-canonical tags.

---

### 2. Implementation Details

In `services/vision-engine/app/audio/speaker.py`:

1. **`SpeechManager.__init__` Normalization:**
   ```python
   try:
       from app.localization import normalize_language, is_supported_language
       norm = normalize_language(language) if is_supported_language(language) else language.strip().lower()
   except Exception:
       norm = language.strip().lower()
   self._default_language: str = norm
   ```

2. **`SpeechManager.language` Setter Strict Contract:**
   ```python
   @language.setter
   def language(self, value: str) -> None:
       try:
           from app.localization import normalize_language
           norm = normalize_language(value)
       except Exception as exc:
           raise ValueError(f"Invalid language '{value}': {exc}") from exc

       with self._state_lock:
           self._default_language = norm
   ```
   Setting an unsupported language code (e.g. `"fr"`, `"de"`, `""`) now raises an explicit `ValueError`, matching the API contract and preventing corrupted language states.

3. **`SpeechManager.announce()` Canonical Normalization:**
   ```python
   raw_lang = (language or self.language).strip().lower()
   try:
       from app.localization import normalize_language, is_supported_language
       active_language = normalize_language(raw_lang) if is_supported_language(raw_lang) else raw_lang
   except Exception:
       active_language = raw_lang
   ```
   Ensures that every enqueued `SpeechItem.language` is canonicalized (`"ne"` or `"en"`).

---

### 3. Empirical Verification Results

A dedicated test suite was implemented in `tests/test_speech_normalization.py` covering:
- Canonical normalization of all recognized Nepali aliases (`ne`, `ne-NP`, `ne_np`, `nepali`) to `"ne"`.
- Canonical normalization of all recognized English aliases (`en`, `en-US`, `en_us`, `en-GB`, `english`) to `"en"`.
- Rejection of invalid language codes (`fr`, `es`, `de`, `zh`, `123`, `unknown_lang`) with explicit `ValueError`.
- State preservation: `SpeechManager` retains its prior valid state upon failed assignment attempts.
- Per-request normalization: `announce(..., language="ne-NP")` enqueues items with `language="ne"`.
- Concurrent thread-safety: 50 simultaneous worker threads switching between `"ne-NP"` and `"en-US"` maintained 100% state consistency.

**Result:** **4/4 tests passed in 0.13s** in `test_speech_normalization.py`, and **8/8 tests passed in 2.20s** in `test_bilingual_speech.py`.
