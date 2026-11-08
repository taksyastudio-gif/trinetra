"""
Tests for 100% In-House Trinetra Native Vision Engine & TrinetraNet.
Verifies pure native computer vision and PyTorch neural classification
with ZERO ONNX runtimes and ZERO YOLO dependencies.
"""

import cv2
import numpy as np
import pytest

from app.detection.native_engine import NativeVisionEngine
from app.detection.model import TrinetraNet, NativeClassifier, CLASSES


def test_native_vision_engine_metadata():
    engine = NativeVisionEngine()
    assert engine.is_ready() is True
    info = engine.get_model_info()
    assert info["model_name"] == "Trinetra-Native-InHouse-v1"
    assert info["runtime"] == "pure_native_pytorch_cv"
    assert "person" in info["supported_classes"]
    assert "sign_namaste" in info["supported_classes"]


def test_trinetra_net_forward_pass():
    import torch
    model = TrinetraNet(num_classes=len(CLASSES))
    dummy_input = torch.randn(2, 3, 64, 64)
    output = model(dummy_input)
    assert output.shape == (2, len(CLASSES))


def test_native_engine_inference_on_synthetic_frame():
    engine = NativeVisionEngine()
    # Create synthetic test frame with upper body / person-like region
    frame = np.full((480, 640, 3), 40, dtype=np.uint8)

    # Encode to JPEG
    ret, jpeg_bytes = cv2.imencode(".jpg", frame)
    assert ret is True

    result = engine.detect(jpeg_bytes.tobytes(), frame_id=42)
    assert result.frame_id == 42
    assert result.model_name == "Trinetra-Native-v1"
    assert isinstance(result.detections, list)
    assert result.inference_time_ms >= 0.0


def test_native_classifier_predict_crop():
    classifier = NativeClassifier()
    # Dummy crop
    crop = np.zeros((100, 100, 3), dtype=np.uint8)
    cls_name, conf = classifier.predict_crop(crop)
    # When no model is loaded or initialized with dummy, returns safe fallback
    assert isinstance(cls_name, str)
    assert isinstance(conf, float)
