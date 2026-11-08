"""
Unit tests for Trinetra Sign Language & Hand Gesture Interpreter (sign_interpreter.py).
"""
import numpy as np
import pytest

from app.detection.sign_interpreter import (
    SignGestureInterpreter,
    SignGesture,
    PROTOTYPE_GESTURE_LABELS,
)


def test_prototype_labels_registry():
    assert "namaste" in PROTOTYPE_GESTURE_LABELS
    assert "stop_palm" in PROTOTYPE_GESTURE_LABELS
    assert "help" in PROTOTYPE_GESTURE_LABELS
    assert "water" in PROTOTYPE_GESTURE_LABELS
    assert "food" in PROTOTYPE_GESTURE_LABELS
    assert "thanks" in PROTOTYPE_GESTURE_LABELS
    assert "sick" in PROTOTYPE_GESTURE_LABELS


def test_empty_or_none_frame():
    interpreter = SignGestureInterpreter()
    res1 = interpreter.analyze(None)
    assert res1.detected is False
    assert res1.gesture_type == "none"

    res2 = interpreter.analyze(np.array([], dtype=np.uint8))
    assert res2.detected is False
    assert res2.gesture_type == "none"


def test_black_blank_frame_returns_none():
    interpreter = SignGestureInterpreter()
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    res = interpreter.analyze(blank)
    assert res.detected is False
    assert res.gesture_type == "none"


def test_simulated_namaste_gesture():
    interpreter = SignGestureInterpreter()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw vertical skin-tone ellipse (aspect ratio ~0.55) in center chest area (rel_y ~0.35)
    center = (320, 200)
    axes = (45, 90)
    # BGR for light brown/skin tone: Hue in [0, 25] in HSV
    skin_bgr = (140, 175, 220)
    import cv2
    cv2.ellipse(frame, center, axes, 0, 0, 360, skin_bgr, -1)

    res = interpreter.analyze(frame)
    assert res.detected is True
    assert res.gesture_type == "namaste"
    assert res.symbol == "🙏"
    assert res.confidence >= 0.80


def test_simulated_sick_gesture_near_forehead():
    interpreter = SignGestureInterpreter()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw horizontal hand near top of chest/head area (rel_y < 0.22)
    center = (320, 60)
    axes = (70, 40)
    skin_bgr = (140, 175, 220)
    import cv2
    cv2.ellipse(frame, center, axes, 0, 0, 360, skin_bgr, -1)

    res = interpreter.analyze(frame)
    assert res.detected is True
    assert res.gesture_type == "sick"
    assert res.symbol == "🤒"


def test_simulated_food_gesture_near_mouth():
    interpreter = SignGestureInterpreter()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw compact hand near mouth / upper chest (rel_y ~0.32)
    center = (320, 130)
    axes = (55, 60)
    skin_bgr = (140, 175, 220)
    import cv2
    cv2.ellipse(frame, center, axes, 0, 0, 360, skin_bgr, -1)

    res = interpreter.analyze(frame)
    assert res.detected is True
    assert res.gesture_type == "food"
    assert res.symbol == "🍲"
