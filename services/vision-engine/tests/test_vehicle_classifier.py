"""
Tests for NepaliVehicleClassifier (trained on 4,797 Nepali vehicle dataset images).
"""

from pathlib import Path
import cv2
import numpy as np

from app.detection.vehicle_classifier import (
    NepaliVehicleClassifier,
    VehicleClassificationResult,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT_DIR / "datasets" / "vehicles"


def test_vehicle_classifier_initialization():
    classifier = NepaliVehicleClassifier()
    assert classifier.is_ready() is True


def test_vehicle_classifier_two_wheeler_inference():
    classifier = NepaliVehicleClassifier()
    tw_dir = DATASET_DIR / "2wheelers"
    if tw_dir.exists():
        sample_img = next(tw_dir.glob("*.jpg"), None)
        if sample_img:
            img = cv2.imread(str(sample_img))
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            result = classifier.classify_crop(img_rgb)

            assert isinstance(result, VehicleClassificationResult)
            assert result.confidence > 0.5
            assert result.vehicle_type in ("two_wheeler", "four_wheeler")
            assert "मोटरसाइकल" in result.label_ne or "सवारी" in result.label_ne


def test_vehicle_classifier_four_wheeler_inference():
    classifier = NepaliVehicleClassifier()
    fw_dir = DATASET_DIR / "4wheelers"
    if fw_dir.exists():
        sample_img = next(fw_dir.glob("*.jpg"), None)
        if sample_img:
            img = cv2.imread(str(sample_img))
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            result = classifier.classify_crop(img_rgb)

            assert isinstance(result, VehicleClassificationResult)
            assert result.confidence > 0.5
            assert result.is_vehicle is True


def test_vehicle_classifier_blank_image():
    classifier = NepaliVehicleClassifier()
    blank = np.zeros((160, 160, 3), dtype=np.uint8)
    result = classifier.classify_crop(blank)
    assert isinstance(result, VehicleClassificationResult)
