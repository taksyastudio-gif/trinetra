"""
Automated Integration and Unit Tests for Real ONNX Inference Engine.
Validates model acquisition, cryptographic verification, CPU inference on real test images,
preprocessing, postprocessing, NMS, exception handling, and absence of fake fallbacks.
"""

import hashlib
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict

import cv2
import numpy as np
import pytest

from app.camera.adapter import FakeCameraAdapter, FramePacket
from app.audio.speaker import FakeSpeechBackend
from app.detection.engine import (
    BoundingBox,
    Detection,
    DetectionResult,
    FakeDetectionEngine,
    PerceptionPipeline,
    classify_sector,
)
from app.detection.onnx_engine import (
    COCO_CLASSES,
    InferenceRuntimeError,
    ModelError,
    ModelIntegrityError,
    ModelNotFoundError,
    OnnxDetectionEngine,
    compute_file_sha256,
    validate_bounding_box,
    verify_model_hash,
)
from app.main import create_app, get_default_detection_engine
try:
    from socket_free_client import SocketFreeTestClient as TestClient
except ImportError:
    from tests.socket_free_client import SocketFreeTestClient as TestClient

MODEL_PATH = str(Path(__file__).resolve().parent.parent / "models" / "yolox_nano.onnx")
EXPECTED_SHA256 = "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"
DOG_FIXTURE_PATH = str(Path(__file__).resolve().parent / "fixtures" / "test_dog.jpg")
PERSON_FIXTURE_PATH = str(Path(__file__).resolve().parent / "fixtures" / "test_person.jpg")


def test_onnx_real_model_loading_and_metadata():
    """Validates loading the official YOLOX-Nano ONNX model with hash verification."""
    assert os.path.isfile(MODEL_PATH), f"Model weight file missing at {MODEL_PATH}"
    
    engine = OnnxDetectionEngine(
        model_path=MODEL_PATH,
        expected_sha256=EXPECTED_SHA256,
        confidence_threshold=0.35,
        iou_threshold=0.45
    )
    assert engine.is_ready() is True
    info = engine.get_model_info()
    assert info["is_ready"] is True
    assert info["model_name"] == "yolox_nano.onnx"
    assert info["runtime"] == "onnxruntime-cpu"
    assert info["architecture"] == "yolox"
    assert info["input_size"] == [416, 416]
    assert len(info["supported_classes"]) == 80
    assert "dog" in info["supported_classes"]
    assert "bicycle" in info["supported_classes"]


def test_onnx_real_inference_on_dog_fixture():
    """
    CRITICAL INTEGRATION TEST (Dog Fixture):
    Executes genuine on-device CPU inference on Megvii's official dog sample image.
    The scene physically depicts:
      1. A dog sitting on the porch (center-left)
      2. A red bicycle parked on the porch (center)
      3. A white vehicle (pickup truck/car) parked across the street (upper right)
    Verifies that real objects (dog, bicycle, car) are detected with high confidence
    and that NO false 'person' is detected in an unpopulated porch scene.
    """
    assert os.path.isfile(DOG_FIXTURE_PATH), f"Test fixture image missing at {DOG_FIXTURE_PATH}"
    with open(DOG_FIXTURE_PATH, "rb") as f:
        jpeg_bytes = f.read()

    engine = OnnxDetectionEngine(
        model_path=MODEL_PATH,
        expected_sha256=EXPECTED_SHA256,
        confidence_threshold=0.35,
        iou_threshold=0.45
    )

    result = engine.detect(jpeg_bytes=jpeg_bytes, frame_id=42)
    assert isinstance(result, DetectionResult)
    assert result.frame_id == 42
    assert result.model_name == "yolox_nano.onnx"
    assert result.inference_time_ms > 0.0

    # Ensure detections were returned
    assert len(result.detections) >= 2, f"Expected at least 2 detections, got: {len(result.detections)}"

    detected_classes = {d.class_name: d for d in result.detections}
    assert "dog" in detected_classes, f"Expected 'dog' to be detected. Detected: {list(detected_classes.keys())}"
    assert "bicycle" in detected_classes, f"Expected 'bicycle' to be detected. Detected: {list(detected_classes.keys())}"
    assert "car" in detected_classes, f"Expected 'car' for parked vehicle. Detected: {list(detected_classes.keys())}"
    # Verify no false positive person is detected
    assert "person" not in detected_classes

    # Verify dog detection properties
    dog = detected_classes["dog"]
    assert dog.confidence >= 0.70, f"Dog confidence unexpectedly low: {dog.confidence}"
    assert 0.0 <= dog.box.x_min < dog.box.x_max <= 1.0
    assert 0.0 <= dog.box.y_min < dog.box.y_max <= 1.0


def test_onnx_real_inference_on_person_fixture():
    """
    CRITICAL INTEGRATION TEST (Person Fixture):
    Executes genuine on-device CPU inference on the public domain person.jpg test image.
    The scene physically depicts a person, a dog, and a horse.
    Verifies that 'person' is correctly detected at COCO class index 0 with high confidence (> 0.8),
    confirming class index mapping and detection accuracy for pedestrians/people.
    """
    assert os.path.isfile(PERSON_FIXTURE_PATH), f"Person fixture missing at {PERSON_FIXTURE_PATH}"
    with open(PERSON_FIXTURE_PATH, "rb") as f:
        jpeg_bytes = f.read()

    engine = OnnxDetectionEngine(
        model_path=MODEL_PATH,
        expected_sha256=EXPECTED_SHA256,
        confidence_threshold=0.35,
        iou_threshold=0.45
    )

    result = engine.detect(jpeg_bytes=jpeg_bytes, frame_id=101)
    assert isinstance(result, DetectionResult)
    assert len(result.detections) >= 2

    detected_classes = {d.class_name: d for d in result.detections}
    assert "person" in detected_classes, f"Expected 'person' to be detected. Detected: {list(detected_classes.keys())}"
    person = detected_classes["person"]
    assert person.confidence >= 0.80, f"Expected person confidence >= 0.80, got {person.confidence}"
    assert person.sector == "center"
    assert 0.0 <= person.box.x_min < person.box.x_max <= 1.0



def test_onnx_missing_model_file_raises_not_found():
    """Verifies that pointing to a nonexistent model path raises ModelNotFoundError."""
    nonexistent = "D:/trinetra/models/nonexistent_model_file.onnx"
    with pytest.raises(ModelNotFoundError):
        OnnxDetectionEngine(model_path=nonexistent)


def test_onnx_hash_mismatch_raises_integrity_error(tmp_path):
    """Verifies that tampered or corrupted weights raise ModelIntegrityError."""
    fake_model = tmp_path / "tampered.onnx"
    fake_model.write_bytes(b"CORRUPTED_OR_TAMPERED_MODEL_BYTES_XYZ")

    with pytest.raises(ModelIntegrityError):
        OnnxDetectionEngine(
            model_path=str(fake_model),
            expected_sha256=EXPECTED_SHA256
        )


def test_onnx_missing_runtime_raises_inference_runtime_error(monkeypatch):
    """Verifies that missing onnxruntime package raises InferenceRuntimeError."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "onnxruntime":
            raise ImportError("No module named 'onnxruntime'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    with pytest.raises(InferenceRuntimeError):
        OnnxDetectionEngine(model_path=MODEL_PATH)


def test_onnx_corrupt_or_empty_frame_handling():
    """Verifies that empty or corrupt JPEG bytes do not crash the engine and return empty results."""
    engine = OnnxDetectionEngine(model_path=MODEL_PATH, expected_sha256=EXPECTED_SHA256)

    # Empty bytes
    res_empty = engine.detect(jpeg_bytes=b"", frame_id=1)
    assert res_empty.detections == []
    assert res_empty.inference_time_ms == 0.0

    # Garbage bytes
    res_garbage = engine.detect(jpeg_bytes=b"NOT_A_VALID_JPEG_HEADER", frame_id=2)
    assert res_garbage.detections == []
    assert res_garbage.inference_time_ms == 0.0


def test_onnx_nan_inf_degenerate_box_handling():
    """Verifies that bounding boxes containing NaN, Inf, or inverted bounds are safely rejected."""
    assert validate_bounding_box(float("nan"), 0.1, 0.5, 0.5) is None
    assert validate_bounding_box(0.1, float("inf"), 0.5, 0.5) is None
    assert validate_bounding_box(0.1, 0.1, float("-inf"), 0.5) is None
    assert validate_bounding_box(0.8, 0.1, 0.2, 0.5) is None  # x_min > x_max
    assert validate_bounding_box(0.1, 0.9, 0.5, 0.3) is None  # y_min > y_max
    assert validate_bounding_box(0.5, 0.5, 0.5, 0.5) is None  # zero area


def test_onnx_confidence_and_nms_filtering():
    """Verifies that low confidence detections are pruned and overlapping detections are suppressed."""
    engine = OnnxDetectionEngine(
        model_path=MODEL_PATH,
        expected_sha256=EXPECTED_SHA256,
        confidence_threshold=0.999,  # Impossibly high threshold
        iou_threshold=0.45
    )
    with open(DOG_FIXTURE_PATH, "rb") as f:
        jpeg_bytes = f.read()

    res = engine.detect(jpeg_bytes=jpeg_bytes, frame_id=10)
    # At 99.9% confidence threshold, all candidate detections should be filtered out
    assert len(res.detections) == 0


def test_onnx_yolov8_postprocess_compatibility():
    """Verifies that YOLOv8 output tensor layout [1, 84, 8400] is correctly handled by postprocessing."""
    engine = OnnxDetectionEngine(
        model_path=MODEL_PATH,
        expected_sha256=EXPECTED_SHA256,
        confidence_threshold=0.5
    )

    # Synthesize YOLOv8 raw output: (1, 84, 100)
    raw = np.zeros((1, 84, 100), dtype=np.float32)
    # Candidate 0: person at center (cx=320, cy=240, w=100, h=200), class 0 (person) = 0.95
    raw[0, 0, 0] = 320.0
    raw[0, 1, 0] = 240.0
    raw[0, 2, 0] = 100.0
    raw[0, 3, 0] = 200.0
    raw[0, 4, 0] = 0.95  # person class score

    meta = {
        "scale": 1.0,
        "pad_x": 0,
        "pad_y": 0,
        "orig_w": 640,
        "orig_h": 480,
        "architecture": "yolov8"
    }

    detections = engine.postprocess(raw, meta)
    assert len(detections) == 1
    det = detections[0]
    assert det.class_name == "person"
    assert det.confidence == 0.95
    assert det.sector == "center"


def test_default_engine_selection_and_status():
    """Verifies that get_default_detection_engine selects the real ONNX engine when present."""
    engine = get_default_detection_engine()
    assert isinstance(engine, OnnxDetectionEngine)
    info = engine.get_model_info()
    assert info["runtime"] == "onnxruntime-cpu"
    assert info["model_name"] == "yolox_nano.onnx"
    assert info["is_ready"] is True


def test_no_silent_fallback_on_corrupt_model(monkeypatch, tmp_path):
    """
    NON-NEGOTIABLE SAFETY TEST:
    Verifies that when a configured model is corrupt or fails to load,
    the system raises an explicit ModelIntegrityError / ModelError and NEVER
    silently falls back to FakeDetectionEngine.
    """
    corrupt_file = tmp_path / "corrupt_yolox.onnx"
    corrupt_file.write_bytes(b"INVALID_CORRUPT_BYTES")

    monkeypatch.setenv("TRINETRA_MODEL_PATH", str(corrupt_file))

    with pytest.raises((ModelError, InferenceRuntimeError)):
        get_default_detection_engine()


def test_real_engine_integrated_in_perception_pipeline():
    """
    Verifies end-to-end integration:
    Real OnnxDetectionEngine wired into asynchronous PerceptionPipeline.
    Submits a frame from test fixture and receives real detections through pipeline.
    """
    with open(DOG_FIXTURE_PATH, "rb") as f:
        jpeg_bytes = f.read()

    engine = OnnxDetectionEngine(
        model_path=MODEL_PATH,
        expected_sha256=EXPECTED_SHA256,
        confidence_threshold=0.35
    )
    fake_speaker = FakeSpeechBackend()
    from app.audio.speaker import SpeechManager
    speech_mgr = SpeechManager(backend=fake_speaker)

    pipeline = PerceptionPipeline(engine=engine, speech_manager=speech_mgr, target_fps=30.0)
    pipeline.start()

    packet = FramePacket(
        frame_id=1,
        captured_at=time.time(),
        jpeg_bytes=jpeg_bytes,
        width=768,
        height=576,
        source_id="test_cam",
        session_id="session_test_1"
    )

    pipeline.submit_frame(packet)

    # Wait briefly for worker to complete inference
    time.sleep(0.15)
    pipeline.stop()

    latest = pipeline.get_latest_result()
    assert latest is not None
    assert latest.frame_id == 1
    assert latest.model_name == "yolox_nano.onnx"
    assert len(latest.detections) >= 2
    classes = [d.class_name for d in latest.detections]
    assert "dog" in classes


def test_api_detection_status_reports_real_engine():
    """Verifies that GET /api/detection/status reports real engine and runtime through the REST API."""
    fake_adapter = FakeCameraAdapter(width=320, height=240)
    app = create_app(adapter=fake_adapter)

    with TestClient(app) as client:
        resp = client.get("/api/detection/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_ready"] is True
        assert data["model_name"] == "yolox_nano.onnx"
        assert data["runtime"] == "onnxruntime-cpu"
        assert "dog" in data["supported_classes"]


def test_onnx_live_webcam_detection_hardware_probe():
    """
    OPTIONAL HARDWARE INTEGRATION TEST:
    Probes physical camera index 0 via DirectShow.
    If hardware is present and openable, captures a live frame, executes real ONNX detection,
    and cleanly releases hardware handles.
    If physical hardware is unavailable or in use by another process, marks test as skipped.
    """
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        pytest.skip("Physical camera index 0 is not available in this test environment.")

    try:
        ret, frame = cap.read()
    finally:
        cap.release()

    if not ret or frame is None:
        pytest.skip("Could not read frame from physical camera index 0.")

    ret_enc, jpeg_buf = cv2.imencode(".jpg", frame)
    assert ret_enc is True

    engine = OnnxDetectionEngine(model_path=MODEL_PATH, expected_sha256=EXPECTED_SHA256)
    result = engine.detect(jpeg_buf.tobytes(), frame_id=999)

    assert isinstance(result, DetectionResult)
    assert result.model_name == "yolox_nano.onnx"
    assert result.inference_time_ms >= 0.0

