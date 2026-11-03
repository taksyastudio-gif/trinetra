"""Local-first assistive capability services.

All services accept a JPEG already acquired by the authoritative camera
adapter.  Optional models are lazy-loaded and absence is represented as an
explicit unavailable/uncertain result, never a fabricated prediction.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Optional


NEPALI_OBJECTS = {"person": "मान्छे", "chair": "कुर्सी", "car": "गाडी", "bicycle": "साइकल", "bus": "बस", "dog": "कुकुर"}


def decode_jpeg(jpeg: bytes):
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Camera returned an invalid JPEG frame.")
    return image


class SceneService:
    """Grounded local scene descriptions derived from the existing detector."""
    def describe(self, question: str, detections: list[Any]) -> dict[str, Any]:
        if not detections:
            return {"text": "मलाई यस फ्रेममा विश्वसनीय रूपमा केही छुट्याउन सकिनँ।", "confidence": 0.0,
                    "status": "uncertain", "provider": "local_detection", "observations": []}
        items = []
        for detection in detections[:4]:
            label = NEPALI_OBJECTS.get(detection.class_name, detection.class_name)
            sector = {"left": "बायाँ", "center": "अगाडि", "right": "दायाँ"}.get(detection.sector, "वरिपरि")
            items.append({"label": label, "sector": sector, "confidence": round(float(detection.confidence), 3)})
        phrase = "; ".join(f"{entry['sector']} {entry['label']}" for entry in items)
        return {"text": f"मैले देखेको अनुसार: {phrase}।", "confidence": min(x["confidence"] for x in items),
                "status": "observed", "provider": "local_detection", "observations": items,
                "safety_note": "यो एकल फ्रेमको अवलोकन हो; बाटो सुरक्षित छ भन्ने निष्कर्ष होइन।"}


class CurrencyService:
    """Loads only an explicitly supplied ONNX currency classifier.

    Generic colour heuristics are intentionally not used: they are unsafe for
    worn notes and cannot establish denomination reliably.
    """
    denominations = (5, 10, 20, 50, 100, 500, 1000)
    def __init__(self, model_path: Optional[str] = None, threshold: float = 0.82):
        self.model_path = Path(model_path or os.environ.get("TRINETRA_CURRENCY_MODEL", "")) if (model_path or os.environ.get("TRINETRA_CURRENCY_MODEL")) else None
        self.threshold = threshold
        self._session = None
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        return {"available": bool(self.model_path and self.model_path.is_file()), "model_path": self.model_path.name if self.model_path else None,
                "threshold": self.threshold, "denominations": list(self.denominations)}

    def identify(self, jpeg: bytes) -> dict[str, Any]:
        # A production classifier is deliberately opt-in until independently evaluated.
        if not self.status()["available"]:
            return {"status": "unavailable", "denomination": None, "confidence": 0.0,
                    "message": "स्थानीय मुद्रा मोडेल उपलब्ध छैन; रकम अनुमान गरिएन।",
                    "disclaimer": "यसले नोटको प्रामाणिकता जाँच गर्दैन।"}
        return {"status": "uncertain", "denomination": None, "confidence": 0.0,
                "message": "मुद्रा मोडेल तैनाथ छ तर यो निर्माणमा यसको इनपुट सम्झौता प्रमाणित गरिएको छैन।",
                "disclaimer": "यसले नोटको प्रामाणिकता जाँच गर्दैन।"}


class OCRService:
    def __init__(self, language: str = "nep+hin+eng"):
        self.language = language

    def read(self, jpeg: bytes) -> dict[str, Any]:
        try:
            import cv2
            import pytesseract
        except ImportError:
            return {"status": "unavailable", "text": "", "confidence": 0.0,
                    "message": "अफलाइन OCR इन्जिन स्थापना गरिएको छैन।", "regions": []}
        image = decode_jpeg(jpeg)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        try:
            data = pytesseract.image_to_data(gray, lang=self.language, output_type=pytesseract.Output.DICT)
        except Exception:
            return {"status": "unavailable", "text": "", "confidence": 0.0,
                    "message": "नेपाली OCR भाषा डेटा उपलब्ध छैन।", "regions": []}
        words = [(text.strip(), float(conf)) for text, conf in zip(data["text"], data["conf"]) if text.strip() and str(conf) != "-1"]
        text = re.sub(r"\s+", " ", " ".join(word for word, _ in words)).strip()
        confidence = sum(conf for _, conf in words) / (100 * len(words)) if words else 0.0
        return {"status": "ok" if text and confidence >= .35 else "uncertain", "text": text, "confidence": round(confidence, 3),
                "message": None if text else "पढ्न मिल्ने पाठ भेटिएन।", "regions": []}


class FaceRegistry:
    """Local metadata registry. Templates are accepted only from a verified embedder."""
    def __init__(self, path: Optional[Path] = None):
        self.path = path or Path(os.environ.get("TRINETRA_FACE_REGISTRY", Path.home() / ".trinetra" / "face_registry.json"))
        self._lock = threading.RLock()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file(): return {"people": []}
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError): return {"people": []}

    def list_people(self) -> list[dict[str, str]]:
        with self._lock:
            return [{"id": p["id"], "name": p["name"], "created_at": p["created_at"]} for p in self._load()["people"]]

    def delete(self, person_id: str) -> bool:
        with self._lock:
            data = self._load(); before = len(data["people"])
            data["people"] = [p for p in data["people"] if p["id"] != person_id]
            if len(data["people"]) == before: return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            try: os.chmod(self.path, 0o600)
            except OSError: pass
            return True

    def recognize(self, jpeg: bytes) -> dict[str, Any]:
        # Detection-only response is safer than identity without a configured SFace model.
        return {"status": "unavailable", "identity": None, "confidence": 0.0,
                "message": "स्थानीय अनुहार embedding मोडेल उपलब्ध छैन; कुनै पहिचान घोषणा गरिएन।"}
