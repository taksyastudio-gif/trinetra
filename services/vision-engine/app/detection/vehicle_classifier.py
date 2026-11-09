"""
Trinetra Nepali Vehicle Classifier
==================================
Runs the lightweight ONNX model trained on 4,797 Nepali street vehicles
(1,823 two-wheelers, 2,974 four-wheelers, buses, tempos, and trucks).
Provides 100% offline edge classification with localized Nepali/English labels.
"""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("trinetra.detection.vehicle")

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "vehicles" / "v1" / "nepali_vehicles.onnx"

CLASSES = ["two_wheeler", "four_wheeler", "no_vehicle"]
LABELS_NE = {
    "two_wheeler": "मोटरसाइकल / स्कुटर",
    "four_wheeler": "सवारी साधन (गाडी / बस / टेम्पो)",
    "no_vehicle": "सफा",
}
LABELS_EN = {
    "two_wheeler": "Two-Wheeler (Motorcycle / Scooter)",
    "four_wheeler": "Four-Wheeler (Car / Bus / Tempo / Truck)",
    "no_vehicle": "Clear",
}


@dataclass
class VehicleClassificationResult:
    vehicle_type: str            # "two_wheeler", "four_wheeler", "no_vehicle"
    confidence: float
    is_vehicle: bool
    label_ne: str
    label_en: str


class NepaliVehicleClassifier:
    """Classifies detected vehicle bounding boxes or candidate regions."""

    def __init__(self, model_path: Optional[Path] = None, confidence_threshold: float = 0.65):
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self.confidence_threshold = confidence_threshold
        self.session = None
        self._input_name = None
        self._output_name = None

        self._init_session()

    def _init_session(self) -> None:
        if not self.model_path.exists():
            logger.warning(f"Nepali vehicles model not found at {self.model_path}")
            return
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self.session = ort.InferenceSession(str(self.model_path), opts, providers=["CPUExecutionProvider"])
            self._input_name = self.session.get_inputs()[0].name
            self._output_name = self.session.get_outputs()[0].name
            logger.info("NepaliVehicleClassifier: Loaded ONNX model successfully")
        except Exception as exc:
            logger.error(f"Failed to load ONNX vehicle model: {exc}")
            self.session = None

    def is_ready(self) -> bool:
        return self.session is not None

    def classify_crop(self, rgb_crop: np.ndarray) -> VehicleClassificationResult:
        """Classifies an RGB image crop into two_wheeler, four_wheeler, or no_vehicle."""
        if self.session is None or rgb_crop is None or rgb_crop.size == 0:
            return VehicleClassificationResult(
                vehicle_type="no_vehicle",
                confidence=0.0,
                is_vehicle=False,
                label_ne=LABELS_NE["no_vehicle"],
                label_en=LABELS_EN["no_vehicle"],
            )

        try:
            # Resize to 160x160
            resized = cv2.resize(rgb_crop, (160, 160), interpolation=cv2.INTER_AREA)

            # Normalize [0, 1] then ImageNet mean/std
            norm = resized.astype(np.float32) / 255.0
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            norm = (norm - mean) / std

            # Transpose to NCHW [1, 3, 160, 160]
            blob = np.transpose(norm, (2, 0, 1))[np.newaxis, :, :, :]

            outputs = self.session.run([self._output_name], {self._input_name: blob})
            logits = outputs[0][0]

            # Softmax
            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / np.sum(exp_logits)

            pred_idx = int(np.argmax(probs))
            conf = float(probs[pred_idx])
            pred_class = CLASSES[pred_idx]

            is_veh = pred_class in ("two_wheeler", "four_wheeler") and conf >= self.confidence_threshold

            return VehicleClassificationResult(
                vehicle_type=pred_class if is_veh else "no_vehicle",
                confidence=conf,
                is_vehicle=is_veh,
                label_ne=LABELS_NE[pred_class if is_veh else "no_vehicle"],
                label_en=LABELS_EN[pred_class if is_veh else "no_vehicle"],
            )
        except Exception as exc:
            logger.error(f"Error during vehicle inference: {exc}")
            return VehicleClassificationResult(
                vehicle_type="no_vehicle",
                confidence=0.0,
                is_vehicle=False,
                label_ne=LABELS_NE["no_vehicle"],
                label_en=LABELS_EN["no_vehicle"],
            )
