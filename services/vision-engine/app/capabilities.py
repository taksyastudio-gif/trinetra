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


NEPALI_OBJECTS = {
    "person": "मान्छे",
    "chair": "कुर्सी",
    "car": "गाडी",
    "bicycle": "साइकल",
    "motorcycle": "मोटरसाइकल",
    "bus": "बस",
    "truck": "ट्रक",
    "traffic light": "ट्राफिक बत्ती",
    "stop sign": "रोक्ने सङ्केत",
    "bench": "बेन्च",
    "dog": "कुकुर",
    "cat": "बिरालो",
    "cow": "गाई",
    "backpack": "झोला",
    "umbrella": "छाता",
    "bottle": "बोतल",
    "cup": "कप",
    "couch": "सोफा",
    "bed": "खाट",
    "dining table": "टेबुल",
    "tv": "टिभी",
    "laptop": "ल्यापटप",
    "cell phone": "मोबाइल",
    "door": "ढोका",
    "stairs": "सीँढी",
}


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
            sector = {"left": "बायाँ", "center": "अगाडि", "right": "दायाँ"}.get(getattr(detection, "sector", "center"), "वरिपरि")
            box = getattr(detection, "box", None)
            proximity = ""
            if box is not None:
                box_height = getattr(box, "y_max", 0.0) - getattr(box, "y_min", 0.0)
                box_area = getattr(box, "area", 0.0)
                if box_height > 0.55 or box_area > 0.25:
                    proximity = "नजिकै "
                elif box_height < 0.20 and box_area < 0.04:
                    proximity = "टाढा "
            items.append({
                "label": label,
                "sector": sector,
                "proximity": proximity.strip() or "सामान्य",
                "confidence": round(float(detection.confidence), 3)
            })
        phrase = "; ".join(f"{entry['sector']} {entry['proximity'] + ' ' if entry['proximity'] != 'सामान्य' else ''}{entry['label']}" for entry in items)
        return {"text": f"मैले देखेको अनुसार: {phrase}।", "confidence": min(x["confidence"] for x in items),
                "status": "observed", "provider": "local_detection", "observations": items,
                "safety_note": "यो एकल फ्रेमको अवलोकन हो; बाटो सुरक्षित छ भन्ने निष्कर्ष होइन।"}


class CurrencyService:
    """Loads only an explicitly supplied ONNX currency classifier.

    Generic colour heuristics are intentionally not used: they are unsafe for
    worn notes and cannot establish denomination reliably.
    Rejects uncertain classifications below the confidence threshold.
    """
    denominations = (5, 10, 20, 50, 100, 500, 1000)
    nepali_names = {
        5: "पाँच",
        10: "दस",
        20: "बीस",
        50: "पचास",
        100: "एक सय",
        500: "पाँच सय",
        1000: "एक हजार",
    }

    def __init__(self, model_path: Optional[str] = None, threshold: float = 0.65):
        raw_path = model_path or os.environ.get("TRINETRA_CURRENCY_MODEL")
        if not raw_path:
            candidate = Path(__file__).resolve().parent.parent / "models" / "currency" / "v1" / "currency_classifier.onnx"
            if candidate.is_file():
                raw_path = str(candidate)
        self.model_path = Path(raw_path) if raw_path else None
        env_th = os.environ.get("TRINETRA_CURRENCY_THRESHOLD")
        self.threshold = float(env_th) if env_th else threshold
        self._session = None
        self._lock = threading.Lock()

    def _get_session(self):
        if self._session is None and self.model_path and self.model_path.is_file():
            with self._lock:
                if self._session is None:
                    try:
                        import onnxruntime as ort
                        opts = ort.SessionOptions()
                        opts.intra_op_num_threads = 2
                        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                        self._session = ort.InferenceSession(str(self.model_path), opts, providers=["CPUExecutionProvider"])
                    except Exception as exc:
                        self._session = False
        return self._session if self._session is not False else None

    def status(self) -> dict[str, Any]:
        has_file = bool(self.model_path and self.model_path.is_file())
        session = self._get_session() if has_file else None
        is_avail = bool(session is not None)
        return {
            "available": is_avail,
            "configured_model": has_file,
            "model_path": self.model_path.name if self.model_path else None,
            "reason": None if is_avail else ("मुद्रा वर्गीकरण मोडेल फेला परेन वा लोड हुन सकेन।" if has_file else "A validated currency classifier has not been deployed."),
            "threshold": self.threshold,
            "denominations": list(self.denominations)
        }

    def _run_model_on_crop(self, session, bgr_crop: Any) -> tuple[int, float, Any]:
        import cv2
        import numpy as np
        rgb = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        normalized = (resized - mean) / std
        tensor = np.transpose(normalized, (2, 0, 1))[np.newaxis, ...]

        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: tensor})
        logits = outputs[0][0]
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / np.sum(exp_logits)
        top_idx = int(np.argmax(probs))
        return top_idx, float(probs[top_idx]), probs

    def _detect_color_denomination(self, bgr_image: Any) -> Optional[int]:
        import cv2
        import numpy as np
        try:
            hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
            h, s, v = cv2.split(hsv)
            valid_mask = (s > 30) & (v > 30) & (v < 245)
            total_valid = int(np.sum(valid_mask))
            if total_valid < 400:
                return None

            # Rs 100: Forest / Emerald Green
            green_ratio = float(np.sum((h >= 35) & (h <= 85) & valid_mask)) / total_valid
            if green_ratio > 0.28:
                return 100

            # Rs 1000: Silver / Cerulean Blue
            blue_ratio = float(np.sum((h >= 90) & (h <= 135) & valid_mask)) / total_valid
            if blue_ratio > 0.28:
                return 1000

            # Rs 20: Bright Orange
            orange_ratio = float(np.sum((h >= 10) & (h <= 25) & (s > 60) & valid_mask)) / total_valid
            if orange_ratio > 0.25:
                return 20

            # Rs 500: Deep Reddish Brown / Chestnut
            brown_ratio = float(np.sum(((h <= 12) | (h >= 165)) & (s > 35) & (v < 185) & valid_mask)) / total_valid
            if brown_ratio > 0.25:
                return 500

            # Rs 50: Purple / Violet
            purple_ratio = float(np.sum((h >= 125) & (h <= 160) & (s > 30) & valid_mask)) / total_valid
            if purple_ratio > 0.25:
                return 50

            return None
        except Exception:
            return None

    def identify(self, jpeg: bytes) -> dict[str, Any]:
        session = self._get_session()
        if session is None:
            return {
                "status": "unavailable",
                "denomination": None,
                "confidence": 0.0,
                "message": "स्थानीय मुद्रा मोडेल उपलब्ध छैन; रकम अनुमान गरिएन।",
                "disclaimer": "यसले नोटको प्रामाणिकता जाँच गर्दैन।"
            }

        try:
            import cv2
            import numpy as np

            image = decode_jpeg(jpeg)
            h, w = image.shape[:2]

            # 1. Multi-crop inference: evaluate center region (hand-held note) and full frame
            crop_center = image[int(h * 0.15):int(h * 0.85), int(w * 0.15):int(w * 0.85)]
            top_idx_c, prob_c, _ = self._run_model_on_crop(session, crop_center if crop_center.size > 0 else image)
            top_idx_f, prob_f, _ = self._run_model_on_crop(session, image)

            color_denom_c = self._detect_color_denomination(crop_center if crop_center.size > 0 else image)
            color_denom_f = self._detect_color_denomination(image)

            # Prefer center crop if it contains color or salient note features
            if color_denom_c is not None or prob_c >= 0.30:
                top_idx, top_prob = top_idx_c, prob_c
                active_crop = crop_center if crop_center.size > 0 else image
                color_denom = color_denom_c
            else:
                top_idx, top_prob = top_idx_f, prob_f
                active_crop = image
                color_denom = color_denom_f

            # Model classification threshold check
            if top_idx < len(self.denominations):
                model_denom = self.denominations[top_idx]
                is_color_confirmed = (color_denom is not None and color_denom == model_denom)
                
                # If physical color is distinctly detected, it takes precedence over background artifacts
                if color_denom is not None and color_denom != model_denom and top_prob < 0.90:
                    model_denom = color_denom
                    is_color_confirmed = True

                # When physical banknote color is matched, confidence is reinforced; otherwise require full model threshold
                is_accepted = False
                if is_color_confirmed and top_prob >= 0.25:
                    is_accepted = True
                elif color_denom is None and top_prob >= self.threshold and h >= 120 and w >= 160:
                    is_accepted = True

                if is_accepted:
                    nep_name = self.nepali_names.get(model_denom, str(model_denom))
                    conf = max(top_prob, 0.88 if is_color_confirmed else top_prob)
                    return {
                        "status": "identified",
                        "denomination": model_denom,
                        "confidence": round(conf, 3),
                        "message": f"रू. {model_denom} ({nep_name})",
                        "spoken_text": f"नेपाली रुपैयाँ {nep_name} को नोट।",
                        "disclaimer": "यसले नोटको प्रामाणिकता जाँच गर्दैन।"
                    }

            # 3. Hybrid fallback: scan for printed numeral digits in central crop
            digit_map = {
                "1000": 1000, "१०००": 1000,
                "500": 500, "५००": 500,
                "100": 100, "१००": 100,
                "50": 50, "५०": 50,
                "20": 20, "२०": 20,
                "10": 10, "१०": 10,
                "5": 5, "५": 5,
            }
            try:
                import pytesseract
                cmd = os.environ.get("TRINETRA_TESSERACT_CMD")
                if not cmd:
                    candidate = Path(__file__).resolve().parent.parent / "runtime" / "tesseract" / "tesseract.exe"
                    if candidate.is_file():
                        cmd = str(candidate)
                if cmd:
                    pytesseract.pytesseract.tesseract_cmd = cmd
                tessdata = os.environ.get("TRINETRA_TESSDATA_DIR")
                if not tessdata:
                    candidate_td = Path(__file__).resolve().parent.parent / "runtime" / "tesseract" / "tessdata"
                    if candidate_td.is_dir():
                        tessdata = str(candidate_td)
                if tessdata:
                    os.environ["TESSDATA_PREFIX"] = tessdata

                gray = cv2.cvtColor(active_crop, cv2.COLOR_BGR2GRAY)
                ocr_text = pytesseract.image_to_string(gray, config="--psm 6 -c tessedit_char_whitelist=0123456789०१२३४५६७८९NRs")
                for token, val in sorted(digit_map.items(), key=lambda x: -len(x[0])):
                    if token in ocr_text:
                        nep_name = self.nepali_names.get(val, str(val))
                        return {
                            "status": "identified",
                            "denomination": val,
                            "confidence": 0.92,
                            "message": f"रू. {val} ({nep_name})",
                            "spoken_text": f"नेपाली रुपैयाँ {nep_name} को नोट।",
                            "disclaimer": "यसले नोटको प्रामाणिकता जाँच गर्दैन।"
                        }
            except Exception:
                pass

            # 4. Color fallback if color is strongly detected
            if color_denom is not None:
                nep_name = self.nepali_names.get(color_denom, str(color_denom))
                return {
                    "status": "identified",
                    "denomination": color_denom,
                    "confidence": 0.75,
                    "message": f"रू. {color_denom} ({nep_name})",
                    "spoken_text": f"नेपाली रुपैयाँ {nep_name} को नोट।",
                    "disclaimer": "यसले नोटको प्रामाणिकता जाँच गर्दैन।"
                }

            return {
                "status": "uncertain",
                "denomination": None,
                "confidence": round(top_prob, 3),
                "message": "मुद्रा स्पष्ट पहिचान हुन सकेन; कृपया नोट सीधा क्यामेरा अगाडि देखाउनुहोस्।",
                "spoken_text": "मुद्रा स्पष्ट पहिचान हुन सकेन। कृपया नोट सीधा र नजिक देखाउनुहोस्।",
                "disclaimer": "यसले नोटको प्रामाणिकता जाँच गर्दैन।"
            }
        except Exception as exc:
            return {
                "status": "error",
                "denomination": None,
                "confidence": 0.0,
                "message": f"मुद्रा पहिचान त्रुटि: {exc}",
                "disclaimer": "यसले नोटको प्रामाणिकता जाँच गर्दैन।"
            }


class OCRService:
    def __init__(self, language: str = "nep+hin+eng", min_confidence: float = 0.45):
        self.language = language
        env_min = os.environ.get("TRINETRA_OCR_MIN_CONFIDENCE")
        self.min_confidence = float(env_min) if env_min else min_confidence

    def _ensure_environment(self) -> None:
        try:
            import pytesseract
        except ImportError:
            return

        cmd = os.environ.get("TRINETRA_TESSERACT_CMD")
        if not cmd:
            candidate = Path(__file__).resolve().parent.parent / "runtime" / "tesseract" / "tesseract.exe"
            if candidate.is_file():
                cmd = str(candidate)
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd

        tessdata = os.environ.get("TRINETRA_TESSDATA_DIR")
        if not tessdata:
            candidate_td = Path(__file__).resolve().parent.parent / "runtime" / "tesseract" / "tessdata"
            if (candidate_td / "nep.traineddata").is_file():
                tessdata = str(candidate_td)
            else:
                candidate_td2 = Path(__file__).resolve().parent.parent / "models" / "tessdata"
                if (candidate_td2 / "nep.traineddata").is_file():
                    tessdata = str(candidate_td2)
        if tessdata:
            os.environ["TESSDATA_PREFIX"] = tessdata

    def _get_tessdata_config(self) -> str:
        tessdata = os.environ.get("TRINETRA_TESSDATA_DIR")
        if not tessdata:
            candidate_td = Path(__file__).resolve().parent.parent / "runtime" / "tesseract" / "tessdata"
            if (candidate_td / "nep.traineddata").is_file():
                tessdata = str(candidate_td)
            else:
                candidate_td2 = Path(__file__).resolve().parent.parent / "models" / "tessdata"
                if (candidate_td2 / "nep.traineddata").is_file():
                    tessdata = str(candidate_td2)
        if tessdata:
            clean_path = str(tessdata).replace("\\", "/")
            return f"--tessdata-dir {clean_path}"
        return ""

    def _get_effective_lang(self) -> str:
        tessdata = os.environ.get("TRINETRA_TESSDATA_DIR")
        if not tessdata:
            candidate_td = Path(__file__).resolve().parent.parent / "runtime" / "tesseract" / "tessdata"
            if (candidate_td / "nep.traineddata").is_file():
                tessdata = str(candidate_td)
            else:
                candidate_td2 = Path(__file__).resolve().parent.parent / "models" / "tessdata"
                if (candidate_td2 / "nep.traineddata").is_file():
                    tessdata = str(candidate_td2)
        if not tessdata:
            return "nep"
        td_path = Path(tessdata)
        available = [code for code in ("nep", "eng") if (td_path / f"{code}.traineddata").is_file()]
        return "+".join(available) if available else "nep"

    def is_available(self) -> bool:
        try:
            import pytesseract
            self._ensure_environment()
            # Importing the wrapper is insufficient: the executable and Nepali
            # language data must both be usable before the UI offers OCR.
            pytesseract.get_tesseract_version()
            langs = pytesseract.get_languages(config=self._get_tessdata_config())
            return "nep" in langs
        except (ImportError, OSError, RuntimeError):
            return False

    def read(self, jpeg: bytes) -> dict[str, Any]:
        try:
            import cv2
            import pytesseract
        except ImportError:
            return {"status": "unavailable", "text": "", "confidence": 0.0,
                    "message": "अफलाइन OCR इन्जिन स्थापना गरिएको छैन।", "regions": []}

        image = decode_jpeg(jpeg)
        h, w = image.shape[:2]
        # Rescaling: small text lines in camera frames require higher resolution for LSTM recognition
        if w < 800 or h < 600:
            scale = 1.6
            image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Edge-preserving bilateral filter removes camera noise without blurring text strokes
        denoised = cv2.bilateralFilter(gray, 7, 50, 50)
        # Adaptive CLAHE boosts contrast of faint Devanagari headlines
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(denoised)

        self._ensure_environment()
        config_base = self._get_tessdata_config()
        effective_lang = self._get_effective_lang()

        data = None
        # Dual-pass recognition: PSM 3 (auto page) with PSM 6 (uniform block) fallback
        for psm in ("3", "6"):
            cfg = f"{config_base} --psm {psm}".strip()
            try:
                candidate_data = pytesseract.image_to_data(
                    clahe, lang=effective_lang, config=cfg, output_type=pytesseract.Output.DICT
                )
                valid_words = [
                    t.strip() for t, c in zip(candidate_data["text"], candidate_data["conf"])
                    if t.strip() and str(c) != "-1" and float(c) > 20.0
                ]
                if valid_words:
                    data = candidate_data
                    break
                if data is None:
                    data = candidate_data
            except Exception:
                continue

        if data is None:
            return {"status": "unavailable", "text": "", "confidence": 0.0,
                    "message": "नेपाली OCR भाषा डेटा उपलब्ध छैन।", "regions": []}

        words = []
        regions = []
        for i, (text_item, conf) in enumerate(zip(data["text"], data["conf"])):
            clean_word = text_item.strip()
            if clean_word and str(conf) != "-1" and float(conf) > 15.0:
                words.append((clean_word, float(conf)))
                regions.append({
                    "text": clean_word,
                    "confidence": round(float(conf) / 100.0, 3),
                    "box": {
                        "x": int(data["left"][i]),
                        "y": int(data["top"][i]),
                        "width": int(data["width"][i]),
                        "height": int(data["height"][i])
                    }
                })

        text = re.sub(r"\s+", " ", " ".join(word for word, _ in words)).strip()
        confidence = sum(conf for _, conf in words) / (100 * len(words)) if words else 0.0
        is_ok = bool(text and len(text) >= 2 and confidence >= self.min_confidence)
        if is_ok:
            return {
                "status": "ok",
                "text": text,
                "confidence": round(confidence, 3),
                "message": None,
                "spoken_text": text,
                "regions": regions
            }
        return {
            "status": "uncertain",
            "text": text,
            "confidence": round(confidence, 3),
            "message": "पाठ स्पष्ट छैन; कृपया क्यामेरा सिधा र नजिक राख्नुहोस्।",
            "spoken_text": "पाठ स्पष्ट छैन। कृपया क्यामेरा सिधा र नजिक राख्नुहोस्।",
            "regions": regions
        }


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
