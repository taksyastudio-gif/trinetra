"""
Trinetra ONNX Detection Engine
Production-grade CPU inference engine using ONNX Runtime.
Supports anchor-free YOLOX (including YOLOX-Nano) and YOLOv8 architectures.
Includes image decoding, adaptive letterbox preprocessing, non-maximum suppression (NMS),
tensor output validation, and cryptographic SHA-256 model integrity verification.
"""

import hashlib
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.detection.engine import (
    BoundingBox,
    Detection,
    DetectionEngine,
    DetectionResult,
    classify_sector,
)

logger = logging.getLogger("trinetra.detection.onnx")

# Standard 80 COCO Dataset Class Names
COCO_CLASSES: List[str] = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator",
    "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"
]


class ModelError(Exception):
    """Base exception for model-related errors."""
    pass


class ModelNotFoundError(ModelError, FileNotFoundError):
    """Raised when the specified model weight file cannot be located on disk."""
    pass


class ModelIntegrityError(ModelError):
    """Raised when the computed SHA-256 digest does not match the expected hash."""
    pass


class InferenceRuntimeError(ModelError):
    """Raised when onnxruntime is missing or fails during tensor evaluation."""
    pass


def compute_file_sha256(file_path: str) -> str:
    """Computes the SHA-256 hexadecimal digest of a local file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def verify_model_hash(file_path: str, expected_hash: str) -> bool:
    """Verifies that the file at file_path matches expected_hash (case-insensitive)."""
    if not os.path.isfile(file_path):
        return False
    actual_hash = compute_file_sha256(file_path)
    return actual_hash.lower() == expected_hash.strip().lower()


def validate_bounding_box(x_min: float, y_min: float, x_max: float, y_max: float) -> Optional[BoundingBox]:
    """
    Validates that normalized box coordinates are finite, well-ordered, and within [0.0, 1.0].
    Returns BoundingBox if valid, or None if malformed or non-finite.
    """
    # Check for NaN or Inf
    for val in (x_min, y_min, x_max, y_max):
        if val is None or not np.isfinite(val):
            return None

    # Clamp coordinates to [0.0, 1.0]
    clamped_x_min = max(0.0, min(1.0, float(x_min)))
    clamped_y_min = max(0.0, min(1.0, float(y_min)))
    clamped_x_max = max(0.0, min(1.0, float(x_max)))
    clamped_y_max = max(0.0, min(1.0, float(y_max)))

    # Reject inverted or degenerate boxes (min >= max)
    if clamped_x_min >= clamped_x_max or clamped_y_min >= clamped_y_max:
        return None

    return BoundingBox(
        x_min=round(clamped_x_min, 4),
        y_min=round(clamped_y_min, 4),
        x_max=round(clamped_x_max, 4),
        y_max=round(clamped_y_max, 4)
    )


class OnnxDetectionEngine(DetectionEngine):
    """
    Concrete detection engine executing ONNX models via onnxruntime on CPU.
    Requires an explicit model file path. Never silently substitutes mock detections.
    Supports YOLOX (e.g. YOLOX-Nano [1, 3549, 85]) and YOLOv8 ([1, 84, 8400]).
    """

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        expected_sha256: Optional[str] = None,
        input_size: Optional[Tuple[int, int]] = None,
        classes: Optional[List[str]] = None
    ):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.expected_sha256 = expected_sha256
        if classes is None:
            meta_path = os.path.join(os.path.dirname(model_path), "metadata.json")
            if os.path.isfile(meta_path):
                try:
                    import json
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    if meta.get("model_name") == os.path.basename(model_path) and "classes" in meta:
                        classes = meta["classes"]
                except Exception:
                    pass

        self.classes = classes or COCO_CLASSES
        self._session = None
        self._input_name = None
        self._output_name = None
        self.architecture = "unknown"
        self.input_size = input_size
        self._yolox_grid = None
        self._yolox_strides = None

        self._model_info: Dict[str, Any] = {
            "model_path": model_path,
            "model_name": os.path.basename(model_path),
            "runtime": "onnxruntime-cpu",
            "is_ready": False,
            "supported_classes": self.classes
        }

        self._initialize_session()

    def _initialize_session(self) -> None:
        """Loads and verifies the ONNX model session."""
        if not os.path.isfile(self.model_path):
            raise ModelNotFoundError(
                f"ONNX model file not found at: '{self.model_path}'. "
                f"Model weights must be staged locally before initializing real inference."
            )

        if self.expected_sha256:
            actual_sha256 = compute_file_sha256(self.model_path)
            if actual_sha256 != self.expected_sha256.strip().lower():
                raise ModelIntegrityError(
                    f"Model SHA-256 verification failed for '{self.model_path}'. "
                    f"Expected: {self.expected_sha256}, Got: {actual_sha256}"
                )
            logger.info("Model SHA-256 integrity verified successfully.")

        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise InferenceRuntimeError(
                "The 'onnxruntime' package is not installed. "
                "Install onnxruntime to enable real CPU inference."
            ) from exc

        try:
            # Enforce CPU execution provider for stability across Windows devices
            providers = ["CPUExecutionProvider"]
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            opts.inter_op_num_threads = 1
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self._session = ort.InferenceSession(self.model_path, opts, providers=providers)
            inp = self._session.get_inputs()[0]
            out = self._session.get_outputs()[0]

            self._input_name = inp.name
            self._output_name = out.name

            # Auto-detect input size from model metadata if not explicitly provided
            if self.input_size is None:
                if len(inp.shape) >= 4 and isinstance(inp.shape[2], int) and isinstance(inp.shape[3], int):
                    self.input_size = (inp.shape[2], inp.shape[3])
                else:
                    self.input_size = (416, 416)

            # Detect architecture from output tensor dimensions
            out_shape = out.shape
            if len(out_shape) == 3 and (out_shape[2] == (5 + len(self.classes)) or out_shape[2] == 25 or out_shape[2] == 85):
                # YOLOX output: [batch, num_candidates, 5 + num_classes] (4 box + 1 obj + classes)
                self.architecture = "yolox"
                self._precompute_yolox_grids()
            elif len(out_shape) == 3 and (out_shape[1] == (4 + len(self.classes)) or out_shape[1] == 84):
                # YOLOv8 output: [batch, 4 + classes, num_candidates]
                self.architecture = "yolov8"
            else:
                self.architecture = "generic"

            self._model_info["is_ready"] = True
            self._model_info["architecture"] = self.architecture
            self._model_info["input_size"] = list(self.input_size)
            self._model_info["input_name"] = self._input_name
            self._model_info["output_name"] = self._output_name
            logger.info(
                f"ONNX model '{os.path.basename(self.model_path)}' ({self.architecture}) "
                f"loaded on CPU with input size {self.input_size}."
            )
        except (ModelError, FileNotFoundError):
            raise
        except Exception as exc:
            raise InferenceRuntimeError(f"Failed to create ONNX InferenceSession: {exc}") from exc

    def _precompute_yolox_grids(self) -> None:
        """Precomputes grid offsets and stride expansions for YOLOX decoding."""
        strides = [8, 16, 32]
        grids = []
        expanded_strides = []
        target_h, target_w = self.input_size

        for stride in strides:
            hsize = target_h // stride
            wsize = target_w // stride
            xv, yv = np.meshgrid(np.arange(wsize), np.arange(hsize))
            grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
            grids.append(grid)
            expanded_strides.append(np.full((1, grid.shape[1], 1), stride))

        self._yolox_grid = np.concatenate(grids, 1)
        self._yolox_strides = np.concatenate(expanded_strides, 1)

    def is_ready(self) -> bool:
        return self._session is not None

    def get_model_info(self) -> Dict[str, Any]:
        return dict(self._model_info)

    def preprocess(self, jpeg_bytes: bytes) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Decodes JPEG bytes, performs appropriate resizing/padding,
        and converts to NCHW float32 tensor layout.
        Returns: (input_tensor, metadata_dict)
        """
        if not jpeg_bytes:
            raise ValueError("Empty image buffer.")

        try:
            import cv2
        except ImportError as exc:
            raise InferenceRuntimeError("OpenCV (cv2) is required for image preprocessing.") from exc

        nparr = np.frombuffer(jpeg_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Corrupt or invalid JPEG image buffer.")

        orig_h, orig_w = img.shape[:2]
        target_h, target_w = self.input_size

        if self.architecture == "yolox":
            # YOLOX standard preprocessing:
            # Scale while preserving aspect ratio, place at top-left (0, 0), pad remainder with 114
            # Keep BGR color order, float32, unnormalized [0, 255] range
            scale = min(target_h / orig_h, target_w / orig_w)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

            padded = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
            padded[:new_h, :new_w] = resized

            tensor = padded.transpose((2, 0, 1)).astype(np.float32)
            tensor = np.expand_dims(tensor, axis=0)

            meta = {
                "scale": scale,
                "pad_x": 0,
                "pad_y": 0,
                "orig_w": orig_w,
                "orig_h": orig_h,
                "architecture": "yolox"
            }
            return tensor, meta
        else:
            # YOLOv8 standard preprocessing:
            # Letterbox centered, neutral grey 114, BGR -> RGB, normalized to [0.0, 1.0]
            scale = min(target_w / orig_w, target_h / orig_h)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

            padded = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
            pad_x = (target_w - new_w) // 2
            pad_y = (target_h - new_h) // 2
            padded[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized

            rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
            tensor = rgb.astype(np.float32) / 255.0
            tensor = np.transpose(tensor, (2, 0, 1))
            tensor = np.expand_dims(tensor, axis=0)

            meta = {
                "scale": scale,
                "pad_x": pad_x,
                "pad_y": pad_y,
                "orig_w": orig_w,
                "orig_h": orig_h,
                "architecture": "yolov8"
            }
            return tensor, meta

    def postprocess(self, raw_output: np.ndarray, meta: Dict[str, Any]) -> List[Detection]:
        """
        Decodes raw ONNX output, filters by confidence,
        applies Non-Maximum Suppression (NMS), and maps to normalized spatial sectors.
        """
        try:
            import cv2
        except ImportError:
            return []

        orig_w = meta["orig_w"]
        orig_h = meta["orig_h"]
        scale = meta["scale"]
        pad_x = meta.get("pad_x", 0)
        pad_y = meta.get("pad_y", 0)
        arch = meta.get("architecture", self.architecture)

        boxes: List[List[int]] = []
        confidences: List[float] = []
        class_ids: List[int] = []

        if arch == "yolox":
            # Decode YOLOX grid-strides if needed
            if self._yolox_grid is not None and raw_output.shape[1] == self._yolox_grid.shape[1]:
                decoded = raw_output.copy()
                decoded[..., :2] = (decoded[..., :2] + self._yolox_grid) * self._yolox_strides
                decoded[..., 2:4] = np.exp(np.clip(decoded[..., 2:4], -10.0, 10.0)) * self._yolox_strides
                preds = decoded[0]
            else:
                preds = raw_output[0] if len(raw_output.shape) == 3 else raw_output

            # Layout: [N, 85] -> cx, cy, w, h, obj_conf, class_0..class_79
            raw_boxes = preds[:, :4]
            obj_conf = preds[:, 4:5]
            cls_scores = preds[:, 5:]
            scores = obj_conf * cls_scores

            max_scores = np.max(scores, axis=1)
            valid_mask = max_scores >= self.confidence_threshold

            for i in np.where(valid_mask)[0]:
                cx, cy, w, h = raw_boxes[i]
                score = float(max_scores[i])
                class_id = int(np.argmax(scores[i]))

                x1 = int((cx - w / 2) / scale)
                y1 = int((cy - h / 2) / scale)
                w_px = int(w / scale)
                h_px = int(h / scale)

                boxes.append([x1, y1, w_px, h_px])
                confidences.append(score)
                class_ids.append(class_id)
        else:
            # YOLOv8 layout: [1, 84, 8400] -> transpose to [8400, 84]
            if len(raw_output.shape) == 3:
                predictions = np.squeeze(raw_output, axis=0).T
            else:
                predictions = raw_output

            scores_matrix = predictions[:, 4:]
            max_scores = np.max(scores_matrix, axis=1)
            valid_mask = max_scores >= self.confidence_threshold

            for i in np.where(valid_mask)[0]:
                cx, cy, w, h = predictions[i, :4]
                score = float(max_scores[i])
                class_id = int(np.argmax(scores_matrix[i]))

                x1 = int((cx - w / 2 - pad_x) / scale)
                y1 = int((cy - h / 2 - pad_y) / scale)
                w_px = int(w / scale)
                h_px = int(h / scale)

                boxes.append([x1, y1, w_px, h_px])
                confidences.append(score)
                class_ids.append(class_id)

        if not boxes:
            return []

        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.confidence_threshold, self.iou_threshold)
        detections: List[Detection] = []

        if len(indices) > 0:
            for idx in np.array(indices).flatten():
                x1, y1, w_px, h_px = boxes[idx]
                score = confidences[idx]
                cid = class_ids[idx]
                label = self.classes[cid] if cid < len(self.classes) else f"class_{cid}"

                norm_xmin = x1 / orig_w
                norm_ymin = y1 / orig_h
                norm_xmax = (x1 + w_px) / orig_w
                norm_ymax = (y1 + h_px) / orig_h

                validated_box = validate_bounding_box(norm_xmin, norm_ymin, norm_xmax, norm_ymax)
                if validated_box is None:
                    continue

                sector = classify_sector(validated_box)
                detections.append(
                    Detection(
                        class_name=label,
                        confidence=round(score, 3),
                        box=validated_box,
                        sector=sector
                    )
                )

        return detections

    def detect(self, jpeg_bytes: bytes, frame_id: int) -> DetectionResult:
        if not self.is_ready():
            raise InferenceRuntimeError("ONNX detection engine is not ready for inference.")

        t0 = time.time()
        try:
            tensor, meta = self.preprocess(jpeg_bytes)
        except ValueError as exc:
            logger.warning(f"Frame {frame_id} preprocessing skipped: {exc}")
            return DetectionResult(
                frame_id=frame_id,
                timestamp=time.time(),
                detections=[],
                inference_time_ms=0.0,
                model_name=os.path.basename(self.model_path)
            )

        raw_outputs = self._session.run([self._output_name], {self._input_name: tensor})
        detections = self.postprocess(raw_outputs[0], meta)
        duration_ms = (time.time() - t0) * 1000.0

        return DetectionResult(
            frame_id=frame_id,
            timestamp=time.time(),
            detections=detections,
            inference_time_ms=round(duration_ms, 2),
            model_name=os.path.basename(self.model_path)
        )
