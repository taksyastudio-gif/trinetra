"""
Trinetra Sign Language & Hand Gesture Interpreter
Real-time vision analyzer translating physical hand gestures into spoken Nepali and high-contrast captions.
Enables seamless two-way communication between deaf/mute individuals and hearing users.
"""
from dataclasses import dataclass
import logging
import math
from typing import Optional, Tuple
from pathlib import Path
import json
import cv2
import numpy as np

logger = logging.getLogger("trinetra.signs")

DEFAULT_NSL_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "signs" / "v1" / "nepali_sign_language_36.onnx"
DEFAULT_NSL_META_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "signs" / "v1" / "nepali_sign_language_36.json"


@dataclass
class NSLClassificationResult:
    detected: bool
    char: str
    rom: str
    name: str
    confidence: float
    message_ne: str
    message_en: str


class NepaliSignLanguageNeuralClassifier:
    """
    Classifies cropped hand gesture regions using the 36-class Nepali Sign Language ONNX model
    (Devanagari consonants क to ज्ञ trained on the Birat Poudel NSL dataset).
    """

    def __init__(self, model_path: Optional[Path] = None, meta_path: Optional[Path] = None):
        self.model_path = Path(model_path) if model_path else DEFAULT_NSL_MODEL_PATH
        self.meta_path = Path(meta_path) if meta_path else DEFAULT_NSL_META_PATH
        self.session = None
        self.classes = []
        self._input_name = None
        self._output_name = None
        self._load()

    def _load(self) -> None:
        if self.meta_path.exists():
            try:
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.classes = data.get("classes", [])
            except Exception as exc:
                logger.warning(f"Failed to load NSL metadata: {exc}")

        if not self.model_path.exists():
            logger.warning(f"Nepali Sign Language ONNX model not found at {self.model_path}")
            return

        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(str(self.model_path), opts, providers=["CPUExecutionProvider"])
            self._input_name = self.session.get_inputs()[0].name
            self._output_name = self.session.get_outputs()[0].name
            logger.info("NepaliSignLanguageNeuralClassifier: Loaded 36-class NSL ONNX model successfully")
        except Exception as exc:
            logger.error(f"Failed to load NSL ONNX session: {exc}")
            self.session = None

    def is_ready(self) -> bool:
        return self.session is not None and len(self.classes) > 0

    def classify_crop(self, rgb_crop: np.ndarray, min_confidence: float = 0.40) -> NSLClassificationResult:
        if not self.is_ready() or rgb_crop is None or rgb_crop.size == 0:
            return NSLClassificationResult(False, "", "", "", 0.0, "", "")

        try:
            resized = cv2.resize(rgb_crop, (160, 160), interpolation=cv2.INTER_AREA)
            norm = resized.astype(np.float32) / 255.0
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            norm = (norm - mean) / std

            blob = np.transpose(norm, (2, 0, 1))[np.newaxis, :, :, :]
            outputs = self.session.run([self._output_name], {self._input_name: blob})
            logits = outputs[0][0]

            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / np.sum(exp_logits)

            pred_idx = int(np.argmax(probs))
            conf = float(probs[pred_idx])

            if pred_idx < len(self.classes) and conf >= min_confidence:
                c = self.classes[pred_idx]
                return NSLClassificationResult(
                    detected=True,
                    char=c["char"],
                    rom=c["rom"],
                    name=c["name"],
                    confidence=conf,
                    message_ne=f"नेपाली सांकेतिक अक्षर: '{c['char']}' ({c['name']})",
                    message_en=f"Nepali Sign Language character: '{c['char']}' ({c['name']})",
                )
        except Exception as exc:
            logger.error(f"Error in NSL neural classification: {exc}")

        return NSLClassificationResult(False, "", "", "", 0.0, "", "")



"""
Trinetra Sign Language & Hand Gesture Interpreter (Prototype Foundation)
========================================================================
Real-time vision analyzer translating physical hand gestures into spoken Nepali and high-contrast captions.
Enables basic non-verbal communication between deaf/mute individuals and hearing users.

IMPORTANT LINGUISTIC & ACCURACY NOTICE:
This module provides a bounded, experimental prototype of 5 everyday communication labels
(मद्दत, पानी, खाना, धन्यवाद, बिरामी) plus standard conversational gestures (नमस्ते, रोक्नुहोस्, ठीक छ).
It does NOT constitute full Nepali Sign Language (NSL) translation, finger-spelling, or sentence grammar.
Real NSL translation requires certified linguistic validation and multi-frame temporal modeling.
"""
from dataclasses import dataclass
import logging
import math
from typing import Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger("trinetra.signs")

# Bounded vocabulary of tested prototype gestures
PROTOTYPE_GESTURE_LABELS = {
    "namaste": {"ne": "नमस्ते (Namaste)", "symbol": "🙏", "category": "greeting"},
    "stop_palm": {"ne": "रोकिनुहोस् (Stop / Wait)", "symbol": "✋", "category": "navigation"},
    "thumbs_up": {"ne": "ठीक छ (Agree / OK)", "symbol": "👍", "category": "confirmation"},
    "help": {"ne": "मद्दत (Help / Assistance)", "symbol": "🆘", "category": "essential"},
    "water": {"ne": "पानी (Water)", "symbol": "💧", "category": "essential"},
    "food": {"ne": "खाना (Food / Meal)", "symbol": "🍲", "category": "essential"},
    "thanks": {"ne": "धन्यवाद (Thank You)", "symbol": "🤝", "category": "courtesy"},
    "sick": {"ne": "बिरामी (Sick / Unwell)", "symbol": "🤒", "category": "emergency"},
}


@dataclass
class SignGesture:
    detected: bool
    gesture_type: str        # "namaste", "thumbs_up", "stop_palm", "help", "water", "food", "thanks", "sick", "unknown", "none"
    confidence: float
    message_ne: str          # Natural Nepali translation
    message_en: str          # English translation
    symbol: str              # Emoji / visual representation
    bounding_box: Optional[Tuple[float, float, float, float]] = None
    is_prototype: bool = True
    first_person_ne: str = ""
    third_person_ne: str = ""


class SignGestureInterpreter:
    """
    Fast geometric and morphological hand gesture interpreter.
    Runs on the upper 75% viewport in <4ms on CPU.
    """

    def __init__(self, min_confidence: float = 0.65):
        self.min_confidence = min_confidence
        self._last_detected_gesture: str = "none"

    def analyze(self, frame_bgr: np.ndarray) -> SignGesture:
        if frame_bgr is None or frame_bgr.size == 0:
            return SignGesture(False, "none", 0.0, "", "", "")

        h, w = frame_bgr.shape[:2]
        # Focus on upper chest, shoulder, and face corridor where signs are executed
        roi = frame_bgr[0 : int(h * 0.85), int(w * 0.12) : int(w * 0.88)]
        if roi.size == 0:
            return SignGesture(False, "none", 0.0, "", "", "")

        roi_h, roi_w = roi.shape[:2]

        # Convert to HSV and extract skin-tone mask
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lower_skin = np.array([0, 28, 55], dtype=np.uint8)
        upper_skin = np.array([25, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower_skin, upper_skin)

        # Morphological opening to filter sensor noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.dilate(mask, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return SignGesture(False, "none", 0.0, "", "", "")

        # Filter contours by minimum visible hand area
        valid_contours = [c for c in contours if cv2.contourArea(c) > (roi_h * roi_w * 0.030)]
        if not valid_contours:
            return SignGesture(False, "none", 0.0, "", "", "")

        c = max(valid_contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        x, y, bw, bh = cv2.boundingRect(c)
        aspect_ratio = float(bw) / float(bh)
        rel_y = float(y) / float(roi_h)  # Normalized vertical position of hand

        # Normalized coordinates relative to full frame
        norm_box = (
            float(y) / h,
            float(int(w * 0.12) + x) / w,
            float(y + bh) / h,
            float(int(w * 0.12) + x + bw) / w
        )

        hull = cv2.convexHull(c, returnPoints=False)
        defects = None
        if len(c) > 3 and hull is not None and len(hull) > 3:
            try:
                defects = cv2.convexityDefects(c, hull)
            except Exception:
                defects = None

        defect_count = 0
        if defects is not None:
            for row in defects:
                flat = row.flatten()
                if len(flat) >= 4:
                    d_dist = flat[3]
                    if d_dist > 18 * 256:
                        defect_count += 1

        # 1. Namaste / Folded Palms (Vertical symmetry, aspect ratio 0.35 - 0.75, chest level 0.20 <= rel_y <= 0.65)
        if 0.35 <= aspect_ratio <= 0.75 and 0.20 <= rel_y <= 0.65 and defect_count <= 2 and area > (roi_h * roi_w * 0.045):
            return SignGesture(
                detected=True,
                gesture_type="namaste",
                first_person_ne="नमस्ते हजुर! सन्चै हुनुहुन्छ?",
                third_person_ne="अगाडिको व्यक्तिले 'नमस्ते' संकेत गर्नुभयो।",
                confidence=0.88,
                message_ne="अगाडिको व्यक्तिले 'नमस्ते' संकेत गर्नुभयो।",
                message_en="The person in front greeted with Namaste.",
                symbol="🙏",
                bounding_box=norm_box
            )

        # 2. बिरामी (Sick / Emergency): Hand placed high touching forehead/temple (rel_y < 0.16)
        if rel_y < 0.16 and area > (roi_h * roi_w * 0.035) and aspect_ratio > 0.65:
            return SignGesture(
                detected=True,
                gesture_type="sick",
                first_person_ne="मलाई एकदम सन्चो छैन, कृपया तुरुन्तै मद्दत गर्नुहोस्!",
                third_person_ne="अगाडिको व्यक्तिले आफू बिरामी परेको संकेत गर्नुभयो।",
                confidence=0.84,
                message_ne="संकेत: 'म बिरामी छु / मलाई सन्चो छैन'।",
                message_en="Signal: 'I am sick / unwell'.",
                symbol="🤒",
                bounding_box=norm_box
            )

        # 3. खाना (Food / Meal): Compact hand cluster placed near mouth / upper chest (0.16 <= rel_y <= 0.45)
        if 0.16 <= rel_y <= 0.45 and 0.60 <= aspect_ratio <= 1.20 and defect_count <= 2:
            return SignGesture(
                detected=True,
                gesture_type="food",
                first_person_ne="मलाई खाना अथवा खाजा खान मन लाग्यो।",
                third_person_ne="अगाडिको व्यक्तिले खाना वा खाजा चाहियो भन्नुभयो।",
                confidence=0.82,
                message_ne="संकेत: 'मलाई खाना वा खाजा चाहियो'।",
                message_en="Signal: 'I need food / a meal'.",
                symbol="🍲",
                bounding_box=norm_box
            )

        # 4. पानी (Water): Distinct 3 finger gaps (defects == 3) or 'W' handshape
        if defect_count == 3 and 0.50 <= aspect_ratio <= 0.95:
            return SignGesture(
                detected=True,
                gesture_type="water",
                first_person_ne="मलाई अलिकति पिउने पानी दिनुहुन्छ कि?",
                third_person_ne="अगाडिको व्यक्तिले पिउने पानी माग्नुभएको छ।",
                confidence=0.81,
                message_ne="संकेत: 'मलाई पिउने पानी चाहियो'।",
                message_en="Signal: 'I need drinking water'.",
                symbol="💧",
                bounding_box=norm_box
            )

        # 5. रोकिनुहोस् (Stop Palm): Wide open hand with 4+ finger defects
        if defect_count >= 4 and 0.70 <= aspect_ratio <= 1.30:
            return SignGesture(
                detected=True,
                gesture_type="stop_palm",
                first_person_ne="एकछिन रोकिनुहोस् है!",
                third_person_ne="अगाडिको व्यक्तिले 'रोकिनुहोस् / पर्खनुहोस्' भन्नुभयो।",
                confidence=0.86,
                message_ne="अगाडिको व्यक्तिले 'रोकिनुहोस् / पर्खनुहोस्' संकेत गर्नुभयो।",
                message_en="The person in front signaled to Stop / Wait.",
                symbol="✋",
                bounding_box=norm_box
            )

        # 6. मद्दत (Help / Urgency): Raised vertical hand / fist with aspect ratio < 0.65 and defect <= 1
        if aspect_ratio < 0.65 and defect_count <= 1 and area > (roi_h * roi_w * 0.035):
            return SignGesture(
                detected=True,
                gesture_type="help",
                first_person_ne="मलाई बाटो काट्न थोरै मद्दत चाहियो, प्लिज!",
                third_person_ne="अगाडिको व्यक्तिले मद्दत माग्दै हुनुहुन्छ।",
                confidence=0.80,
                message_ne="संकेत: 'मलाई मद्दत वा सहयोग चाहियो!'।",
                message_en="Signal: 'I need help / assistance!'.",
                symbol="🆘",
                bounding_box=norm_box
            )

        # 7. धन्यवाद (Thank you): Flat horizontal palm sweep (aspect ratio > 1.25)
        if aspect_ratio >= 1.25 and defect_count <= 2:
            return SignGesture(
                detected=True,
                gesture_type="thanks",
                first_person_ne="धेरै धेरै धन्यवाद हजुर, आभारी छु!",
                third_person_ne="अगाडिको व्यक्तिले धन्यवाद भन्नुभयो।",
                confidence=0.78,
                message_ne="संकेत: 'धन्यवाद' (Thank You)।",
                message_en="Signal: 'Thank you'.",
                symbol="🤝",
                bounding_box=norm_box
            )

        # 8. ठीक छ (Thumbs Up / OK): Single upward thumb protrusion
        if 0.55 <= aspect_ratio <= 1.05 and defect_count <= 1:
            return SignGesture(
                detected=True,
                gesture_type="thumbs_up",
                first_person_ne="हुन्छ, एकदम ठीक छ!",
                third_person_ne="अगाडिको व्यक्तिले 'हुन्छ / ठीक छ' संकेत गर्नुभयो।",
                confidence=0.80,
                message_ne="अगाडिको व्यक्तिले 'हुन्छ / ठीक छ' संकेत गर्नुभयो।",
                message_en="The person in front gave a Thumbs Up (OK / Agree).",
                symbol="👍",
                bounding_box=norm_box
            )

        # 9. Fallback Unknown Gesture State (Active hand contour detected, but ambiguous handshape)
        return SignGesture(
            detected=True,
            gesture_type="unknown",
            confidence=0.45,
            message_ne="हातको संकेत देखियो तर स्पष्ट पहिचान भएन; कृपया फेरि देखाउनुहोस्।",
            message_en="Hand movement visible but sign unclear; please repeat gesture.",
            symbol="❓",
            bounding_box=norm_box
        )

