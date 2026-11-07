"""
Trinetra Multi-Turn Conversational Assistant & Local Dialogue State Machine.

Maintains bounded conversational memory, resolves follow-up questions
(e.g., 'अगाडि के छ?', 'कति टाढा छ?', 'दायाँ के छ?', 'दोहोर्याउनुहोस्'),
supports mixed Nepali/English code-switching and cultural calendar queries,
and provides optional consent-based Cloud Gemini multimodal scene understanding.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.culture import BikramSambatConverter, NepaliPhrasing

logger = logging.getLogger("trinetra.assistant")

NEPALI_OBJECTS = {
    "person": "मान्छे",
    "chair": "कुर्सी",
    "table": "टेबुल",
    "bottle": "बोत्तल",
    "door": "ढोका",
    "stairs": "भर्‍याङ",
    "puddle": "पानीको खाल्डो",
    "vehicle": "गाडी",
    "dog": "कुकुर",
    "cell phone": "मोबाइल",
    "laptop": "ल्यापटप",
    "book": "किताब",
    "bed": "खाट",
    "bicycle": "साइकल",
    "motorcycle": "मोटरसाइकल",
    "car": "कार",
    "bus": "बस",
    "truck": "ट्रक",
    "traffic light": "ट्राफिक बत्ती",
    "stop sign": "रोकिने संकेत",
    "bench": "बेन्च",
}


class CodeSwitchingInterpreter:
    """
    Normalizes mixed Nepali, English, and Romanized-Nepali queries.
    Maps everyday spoken bilingual phrases to normalized intent tags.
    """

    INTENT_MAPPINGS: Dict[str, List[str]] = {
        "date_festival": [
            "मिति", "गते", "आज कति", "चाड", "चाडपर्व", "तिथि", "साल",
            "date", "today date", "which festival", "what festival", "aaja k ho",
            "aaja ko date", "kati gate", "tithi", "festival", "bikram sambat"
        ],
        "medication": [
            "औषधि", "दवा", "गोली खाने", "औषधिको समय", "तालिका",
            "medicine", "tablet", "pills", "medication", "routine", "aushadhi"
        ],
        "lost_guidance": [
            "हराएँ", "हरायो", "कहाँ छु", "बाटो कता", "घर जाने", "म कहाँ",
            "lost", "i am lost", "where am i", "guide home", "find way", "haraye"
        ],
        "emergency": [
            "आपतकालीन", "गुहार", "मद्दत गर", "प्रहरी", "एम्बुलेन्स",
            "emergency", "help me", "police", "ambulance", "sos"
        ],
        "repeat": [
            "दोहोर्या", "फेरि", "भन्नुहोस्", "के भन्नुभयो",
            "repeat", "again", "pardon", "what did you say", "feri bhandinu"
        ],
        "currency": [
            "पैसा", "रुपैयाँ", "रुपियाँ", "नोट", "दर", "कतिको नोट",
            "money", "cash", "rupee", "npr", "paisa", "kati ko note"
        ],
        "ocr": [
            "पढ", "पढ्नु", "लेखेको", "अक्षर", "बोर्ड",
            "read", "text", "written", "signboard", "padha", "k lekheko"
        ],
        "front": [
            "अगाडि", "सिधा",
            "front", "ahead", "straight", "agadi"
        ],
        "left": [
            "बायाँ", "देब्रे",
            "left", "bayan"
        ],
        "right": [
            "दायाँ", "दाहिने",
            "right", "dayan"
        ],
        "distance": [
            "टाढा", "दूरी", "नजिक", "कति टाढा",
            "distance", "how far", "close", "tadaha"
        ],
    }

    @classmethod
    def detect_intent(cls, query: str) -> Optional[str]:
        q = query.strip().lower()
        for intent, triggers in cls.INTENT_MAPPINGS.items():
            for t in triggers:
                if t.lower() in q:
                    return intent
        return None


@dataclass
class DialogueTurn:
    role: str
    text: str
    timestamp: float
    provider: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AssistantDialogueManager:
    """Thread-safe multi-turn assistant with bounded memory and deterministic Nepali dialogue trees."""

    def __init__(self, max_turns: int = 10, context_memory: Optional[Any] = None):
        self.max_turns = max_turns
        self.context_memory = context_memory
        self.turns: List[DialogueTurn] = []
        self.last_observations: List[Dict[str, Any]] = []
        self.last_currency: Optional[Dict[str, Any]] = None
        self.last_ocr: Optional[Dict[str, Any]] = None
        self.last_announcement: str = ""
        self._lock = threading.RLock()

    def update_telemetry(
        self,
        observations: Optional[List[Dict[str, Any]]] = None,
        currency: Optional[Dict[str, Any]] = None,
        ocr: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Updates real-time contextual knowledge from sensor pipelines."""
        with self._lock:
            if observations is not None:
                self.last_observations = observations
            if currency is not None:
                self.last_currency = currency
            if ocr is not None:
                self.last_ocr = ocr

    def query(
        self,
        question: str,
        detections: List[Any],
        jpeg_bytes: Optional[bytes] = None,
        cloud_consent: bool = False,
    ) -> Dict[str, Any]:
        """
        Main query entrypoint.
        Processes question using local multi-turn context or optional consent-based cloud Gemini.
        """
        question_clean = question.strip()
        now = time.time()

        # Update current frame observations
        current_obs = self._parse_detections(detections)
        with self._lock:
            if current_obs:
                self.last_observations = current_obs

        # Check for consent-based Cloud Gemini scene query
        if cloud_consent and os.environ.get("GEMINI_API_KEY") and jpeg_bytes:
            cloud_resp = self._query_gemini_cloud(question_clean, jpeg_bytes)
            if cloud_resp:
                self._record_turn("user", question_clean, "gemini_cloud")
                self._record_turn("assistant", cloud_resp["text"], "gemini_cloud", cloud_resp)
                self.last_announcement = cloud_resp["text"]
                return cloud_resp

        # Process locally with dialogue state machine
        local_resp = self._resolve_local_intent(question_clean, current_obs)
        with self._lock:
            self._record_turn("user", question_clean, "local_detection")
            self._record_turn("assistant", local_resp["text"], "local_detection", local_resp)
            self.last_announcement = local_resp["text"]

        return local_resp

    def _parse_detections(self, detections: List[Any]) -> List[Dict[str, Any]]:
        obs = []
        for det in detections[:6]:
            c_name = getattr(det, "class_name", str(det))
            label = NEPALI_OBJECTS.get(c_name, c_name)
            sector_raw = getattr(det, "sector", "center")
            sector = {"left": "बायाँ", "center": "अगाडि", "right": "दायाँ"}.get(sector_raw, "अगाडि")
            box = getattr(det, "box", None)
            proximity = "सामान्य"
            if box is not None:
                b_h = getattr(box, "y_max", 0.0) - getattr(box, "y_min", 0.0)
                b_area = getattr(box, "area", 0.0)
                if b_h > 0.55 or b_area > 0.25:
                    proximity = "नजिकै"
                elif b_h < 0.20 and b_area < 0.04:
                    proximity = "टाढा"

            obs.append({
                "label": label,
                "sector": sector,
                "proximity": proximity,
                "confidence": round(float(getattr(det, "confidence", 0.75)), 3),
            })
        return obs

    def _resolve_local_intent(
        self, question: str, current_obs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        q_lower = question.lower()
        active_obs = current_obs or self.last_observations
        detected_intent = CodeSwitchingInterpreter.detect_intent(question)

        # 1. Repeat / Echo ("दोहोर्याउनुहोस्", "repeat", "फेरि भन्नुहोस्")
        if detected_intent == "repeat" or any(w in question for w in ["दोहोर्या", "फेरि", "भन्नुहोस्"]) or any(w in q_lower for w in ["repeat", "again", "pardon"]):
            if self.last_announcement:
                return {
                    "text": f"मैले अघि भनेको थिएँ: {self.last_announcement}",
                    "confidence": 1.0,
                    "status": "repeated",
                    "provider": "local_dialogue",
                    "observations": active_obs,
                }
            return {
                "text": "अहिलेसम्म कुनै अघिल्लो सूचना उपलब्ध छैन।",
                "confidence": 0.5,
                "status": "empty",
                "provider": "local_dialogue",
                "observations": active_obs,
            }

        # 2. Bikram Sambat Date & Festival Inquiry
        if detected_intent == "date_festival" or any(w in question for w in ["मिति", "गते", "चाड", "तिथि"]):
            bs_data = BikramSambatConverter.get_current_bs()
            return {
                "text": bs_data.spoken_phrase_ne,
                "confidence": 0.98,
                "status": "cultural_calendar",
                "provider": "local_culture",
                "observations": [],
                "calendar": bs_data.to_dict(),
            }

        # 3. Caretaker / Medication Routine Inquiry
        if detected_intent == "medication":
            med_text = "अहिले कुनै औषधिको तालिका बाँकी छैन। तपाईंको दिन शुभ रहोस्।"
            if self.context_memory:
                try:
                    meds = self.context_memory.get_all_medications()
                    active = [m for m in meds if getattr(m, "is_active", True)]
                    if active:
                        names = ", ".join(f"{m.name} ({m.dosage_time})" for m in active)
                        med_text = f"तपाईंको औषधिको तालिका: {names}। कृपया समयमा औषधि लिनुहोला।"
                except Exception:
                    pass
            return {
                "text": med_text,
                "confidence": 0.92,
                "status": "medication_resolved",
                "provider": "local_caretaker",
                "observations": [],
            }

        # 4. Lost / Navigation Guidance
        if detected_intent == "lost_guidance":
            saved_places = ""
            if self.context_memory:
                try:
                    places = self.context_memory.get_all_places()
                    if places:
                        names = ", ".join(p.name for p in places[:3])
                        saved_places = f" तपाईंसँग सुरक्षित स्थानहरू: {names} छन्।"
                except Exception:
                    pass
            return {
                "text": f"नआत्तिनुहोस्, म तपाईंसँग छु। बाटोमा सुरक्षित ठाउँमा उभिनुहोस्।{saved_places} आपतकालीन मद्दत चाहिएमा 'आपतकालीन' भन्न सक्नुहुन्छ।",
                "confidence": 0.94,
                "status": "lost_guidance",
                "provider": "local_caretaker",
                "observations": [],
            }

        # 5. Emergency Hotline & Assistance
        if detected_intent == "emergency":
            return {
                "text": "नेपालका आपतकालीन नम्बरहरू: प्रहरी १००, एम्बुलेन्स १०२, दमकल १०१। हेरचाहकर्तालाई सूचित गर्न 'आपतकालीन पठाऊ' भन्नुहोस्।",
                "confidence": 0.98,
                "status": "emergency_guidance",
                "provider": "local_caretaker",
                "observations": [],
            }

        # 6. Sector Specific Questions (Front / Right / Left)
        if detected_intent == "front" or "अगाडि" in question or "front" in q_lower or "straight" in q_lower:
            front_items = [o for o in active_obs if o["sector"] == "अगाडि"]
            if front_items:
                desc = ", ".join(f"{it['proximity']} {it['label']}" for it in front_items)
                return {
                    "text": f"तपाईंको सीधा अगाडि: {desc} छ।",
                    "confidence": 0.88,
                    "status": "sector_resolved",
                    "provider": "local_dialogue",
                    "observations": front_items,
                }
            return {
                "text": "तपाईंको सीधा अगाडि कुनै ठूलो अवरोध देखिएको छैन। बाटो खाली छ।",
                "confidence": 0.85,
                "status": "clear",
                "provider": "local_dialogue",
                "observations": [],
            }

        if detected_intent == "right" or "दायाँ" in question or "right" in q_lower:
            right_items = [o for o in active_obs if o["sector"] == "दायाँ"]
            if right_items:
                desc = ", ".join(f"{it['proximity']} {it['label']}" for it in right_items)
                return {
                    "text": f"तपाईंको दायाँ तर्फ: {desc} छ।",
                    "confidence": 0.86,
                    "status": "sector_resolved",
                    "provider": "local_dialogue",
                    "observations": right_items,
                }
            return {
                "text": "दायाँ तर्फ कुनै मुख्य वस्तु देखिएको छैन।",
                "confidence": 0.80,
                "status": "clear",
                "provider": "local_dialogue",
                "observations": [],
            }

        if detected_intent == "left" or "बायाँ" in question or "left" in q_lower:
            left_items = [o for o in active_obs if o["sector"] == "बायाँ"]
            if left_items:
                desc = ", ".join(f"{it['proximity']} {it['label']}" for it in left_items)
                return {
                    "text": f"तपाईंको बायाँ तर्फ: {desc} छ।",
                    "confidence": 0.86,
                    "status": "sector_resolved",
                    "provider": "local_dialogue",
                    "observations": left_items,
                }
            return {
                "text": "बायाँ तर्फ कुनै मुख्य वस्तु देखिएको छैन।",
                "confidence": 0.80,
                "status": "clear",
                "provider": "local_dialogue",
                "observations": [],
            }

        # 7. Proximity / Distance ("कति टाढा छ?", "how far", "distance")
        if detected_intent == "distance" or any(w in question for w in ["टाढा", "दूरी", "नजिक"]) or any(w in q_lower for w in ["far", "distance", "close"]):
            if active_obs:
                closest = active_obs[0]
                return {
                    "text": f"मुख्य वस्तु {closest['sector']} रहेको {closest['label']} हो, जुन {closest['proximity']} देखिन्छ।",
                    "confidence": 0.85,
                    "status": "distance_resolved",
                    "provider": "local_dialogue",
                    "observations": [closest],
                }
            return {
                "text": "कुनै वस्तु पहिचान नभएकोले दूरी मापन गर्न सकिएन।",
                "confidence": 0.5,
                "status": "uncertain",
                "provider": "local_dialogue",
                "observations": [],
            }

        # 8. Currency Inquiries ("पैसा", "रुपैयाँ", "नोट", "money", "cash")
        if detected_intent == "currency" or any(w in question for w in ["पैसा", "रुपैयाँ", "नोट", "दर"]) or any(w in q_lower for w in ["cash", "money", "rupee", "npr"]):
            if self.last_currency and (time.time() - self.last_currency.get("time", 0)) < 45.0:
                c = self.last_currency
                return {
                    "text": f"भर्खरै पहिचान भएको नोट: रु {c.get('denomination')} ({c.get('nepali_text', '')}) हो।",
                    "confidence": c.get("confidence", 0.9),
                    "status": "currency_memory",
                    "provider": "local_dialogue",
                    "observations": [],
                }
            return {
                "text": "पैसा पहिचान गर्न नेपाली नोटलाई क्यामेराको केन्द्रमा समथर पारेर देखाउनुहोस्।",
                "confidence": 0.75,
                "status": "guide",
                "provider": "local_dialogue",
                "observations": [],
            }

        # 9. Reading Inquiries ("के लेखेको छ?", "पढ्नुहोस्", "read", "text")
        if detected_intent == "ocr" or any(w in question for w in ["लेखेको", "पढ्नु", "पढ", "अक्षर"]) or any(w in q_lower for w in ["read", "text", "written"]):
            if self.last_ocr and (time.time() - self.last_ocr.get("time", 0)) < 45.0 and self.last_ocr.get("text"):
                return {
                    "text": f"भर्खरै पढिएको अक्षर: '{self.last_ocr['text']}'।",
                    "confidence": 0.85,
                    "status": "ocr_memory",
                    "provider": "local_dialogue",
                    "observations": [],
                }
            return {
                "text": "अक्षर पढ्न कागजात वा साइनबोर्डलाई क्यामेरा अगाडि सिधा र नहल्लाई राख्नुहोस्।",
                "confidence": 0.75,
                "status": "guide",
                "provider": "local_dialogue",
                "observations": [],
            }

        # 10. Default Scene Overview
        if not active_obs:
            return {
                "text": "मलाई यस दृश्यमा कुनै स्पष्ट वस्तु वा अवरोध छुट्याउन गाह्रो भयो।",
                "confidence": 0.0,
                "status": "uncertain",
                "provider": "local_detection",
                "observations": [],
                "safety_note": "यो एकल फ्रेमको अवलोकन हो; बाटो पूर्ण सुरक्षित छ भन्ने निश्चित गर्दैन।",
            }

        phrase_parts = [
            f"{it['sector']} {it['proximity'] if it['proximity'] != 'सामान्य' else ''} {it['label']}".strip()
            for it in active_obs[:4]
        ]
        phrase = "; ".join(phrase_parts)
        return {
            "text": f"मैले देखेको अनुसार: {phrase}।",
            "confidence": min(x["confidence"] for x in active_obs),
            "status": "observed",
            "provider": "local_detection",
            "observations": active_obs,
            "safety_note": "यो एकल फ्रेमको अवलोकन हो; बाटो सुरक्षित छ भन्ने निष्कर्ष होइन।",
        }

    def _query_gemini_cloud(self, question: str, jpeg_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Optional consent-based call to Google Gemini for advanced multimodal assistance."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None

        import base64
        b64_image = base64.b64encode(jpeg_bytes).decode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

        prompt = (
            "You are Trinetra, an accessibility assistant in Nepal for users navigating real-world spaces. "
            "Answer the user's question briefly (1-2 sentences in conversational Nepali Devanagari) describing "
            "only the spatial layout, obstacles, or requested details. Do NOT make safety guarantees.\n"
            f"User Question: {question}"
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": b64_image,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 150},
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = (
                    data["candidates"][0]["content"]["parts"][0]["text"].strip()
                )
                return {
                    "text": text,
                    "confidence": 0.95,
                    "status": "observed",
                    "provider": "gemini_cloud",
                    "observations": [],
                    "safety_note": "यो क्लाउड एआई अवलोकन हो; बाटो सुरक्षित छ भन्ने निष्कर्ष होइन।",
                }
        except Exception as exc:
            logger.warning(f"Cloud Gemini scene query failed, falling back to local: {exc}")
            return None

    def _record_turn(
        self, role: str, text: str, provider: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        self.turns.append(
            DialogueTurn(
                role=role,
                text=text,
                timestamp=time.time(),
                provider=provider,
                metadata=metadata or {},
            )
        )
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]
