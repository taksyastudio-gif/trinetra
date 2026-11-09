"""
Tests for NepaliSignLanguageNeuralClassifier
Verifies 36-class Nepali Sign Language (NSL) inference trained on Birat Poudel's dataset.
"""

from pathlib import Path
import cv2
import numpy as np

from app.detection.sign_interpreter import (
    NepaliSignLanguageNeuralClassifier,
    NSLClassificationResult,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
NSL_DATASET_DIR = ROOT_DIR / "datasets" / "nepali_sign_language"


def test_nsl_classifier_initialization():
    classifier = NepaliSignLanguageNeuralClassifier()
    assert classifier.is_ready() is True
    assert len(classifier.classes) == 36
    assert classifier.classes[0]["char"] == "क"
    assert classifier.classes[35]["char"] == "ज्ञ"


def test_nsl_classifier_sample_inference():
    classifier = NepaliSignLanguageNeuralClassifier()
    # Pick a sample image from class 0 (क)
    class_0_dir = NSL_DATASET_DIR / "00_ka"
    if class_0_dir.exists():
        sample_img = next(class_0_dir.glob("*.jpg"), None)
        if sample_img:
            img = cv2.imread(str(sample_img))
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            result = classifier.classify_crop(img_rgb, min_confidence=0.01)

            assert isinstance(result, NSLClassificationResult)
            assert result.detected is True
            assert result.char != ""
            assert "नेपाली सांकेतिक अक्षर" in result.message_ne


def test_nsl_classifier_blank_image():
    classifier = NepaliSignLanguageNeuralClassifier()
    blank = np.zeros((160, 160, 3), dtype=np.uint8)
    result = classifier.classify_crop(blank)
    assert isinstance(result, NSLClassificationResult)
