"""
Unit and Regression Tests for Priority 3.7: Controlled YuNet Face Detection & DetectionFusion
Verifies:
1. Human face previously classified as cat is converted to human/person evidence without cat announcements.
2. Genuine cat remains detectable.
3. Full-body person detection remains unchanged.
4. Face inside person box does not create duplicate tracks.
5. Face-only evidence does not fabricate a full-body bounding box.
6. Human beside a genuine cat preserves both detections.
7. Uncertain classifications do not trigger confident speech.
"""

import os
import sys
import time
from typing import List

import cv2
import numpy as np
import pytest

from app.audio.speaker import FakeSpeechBackend, SpeechManager
from app.detection.decision import SceneDecisionEngine
from app.detection.face_detector import FaceDetection, YuNetFaceDetector
from app.detection.fusion import (
    DetectionFusion,
    compute_box_containment,
    compute_box_intersection,
    compute_box_iou,
)
from app.detection.scene import SceneAnalyzer
from app.detection.tracking import TemporalTracker, TrackState
from app.detection.types import BoundingBox, Detection, classify_sector


# ---------------------------------------------------------------------------
# Test 1: Geometry Helpers (Intersection, Containment, IoU)
# ---------------------------------------------------------------------------
def test_fusion_geometry_helpers():
    box1 = BoundingBox(0.2, 0.2, 0.6, 0.6)  # area = 0.16
    box2 = BoundingBox(0.3, 0.3, 0.5, 0.5)  # area = 0.04 (fully inside box1)

    inter = compute_box_intersection(box2, box1)
    assert pytest.approx(inter, abs=1e-4) == 0.04

    containment = compute_box_containment(box2, box1)
    assert pytest.approx(containment, abs=1e-4) == 1.0  # box2 is 100% inside box1

    containment_rev = compute_box_containment(box1, box2)
    assert pytest.approx(containment_rev, abs=1e-4) == 0.25  # 0.04 / 0.16

    iou = compute_box_iou(box1, box2)
    assert pytest.approx(iou, abs=1e-4) == 0.04 / 0.16  # 0.25


# ---------------------------------------------------------------------------
# Test 2: Human Face Previously Classified as Cat
# ---------------------------------------------------------------------------
def test_human_face_previously_classified_as_cat_resolved_to_person():
    """
    When YOLOX produces a spurious cat candidate (conf=0.38) on a human face,
    and YuNet detects a high-confidence face (conf=0.88), the spurious cat must
    be suppressed and replaced with honest human evidence (person).
    """
    fusion = DetectionFusion(enabled=True)

    face_box = BoundingBox(0.35, 0.20, 0.65, 0.50)
    spurious_cat_box = BoundingBox(0.30, 0.18, 0.70, 0.55)

    yolox_dets = [
        Detection(class_name="cat", confidence=0.38, box=spurious_cat_box, sector="center")
    ]
    face_dets = [
        FaceDetection(box=face_box, confidence=0.88)
    ]

    fused = fusion.fuse(yolox_dets, face_detections=face_dets)

    # Must contain exactly 1 detection, which is person, NOT cat
    assert len(fused) == 1
    det = fused[0]
    assert det.class_name == "person"
    assert det.confidence == 0.88
    # Face-only box: must NOT fabricate full-body box
    assert det.box == face_box
    assert all(d.class_name != "cat" for d in fused)


# ---------------------------------------------------------------------------
# Test 3: Genuine Cat Remains Detectable
# ---------------------------------------------------------------------------
def test_genuine_cat_remains_detectable():
    """
    A genuine cat detected by YOLOX (conf=0.78) with no face detection
    must be preserved completely intact without interference.
    """
    fusion = DetectionFusion(enabled=True)

    cat_box = BoundingBox(0.15, 0.50, 0.45, 0.85)
    yolox_dets = [
        Detection(class_name="cat", confidence=0.78, box=cat_box, sector="left")
    ]
    face_dets: List[FaceDetection] = []  # No human face on a real cat

    fused = fusion.fuse(yolox_dets, face_detections=face_dets)

    assert len(fused) == 1
    assert fused[0].class_name == "cat"
    assert fused[0].confidence == 0.78
    assert fused[0].box == cat_box


# ---------------------------------------------------------------------------
# Test 4: Full-Body Person Detection Unchanged
# ---------------------------------------------------------------------------
def test_full_body_person_detection_unchanged():
    """
    A standard full-body person detection (conf=0.88) with no face detection
    (e.g. person turned around, wearing a hood, or far away) must remain unchanged.
    """
    fusion = DetectionFusion(enabled=True)

    person_box = BoundingBox(0.20, 0.10, 0.50, 0.90)
    yolox_dets = [
        Detection(class_name="person", confidence=0.88, box=person_box, sector="center")
    ]
    face_dets: List[FaceDetection] = []

    fused = fusion.fuse(yolox_dets, face_detections=face_dets)

    assert len(fused) == 1
    assert fused[0].class_name == "person"
    assert fused[0].confidence == 0.88
    assert fused[0].box == person_box


# ---------------------------------------------------------------------------
# Test 5: Face Inside Person Box Does Not Create Duplicate Tracks
# ---------------------------------------------------------------------------
def test_face_inside_person_box_does_not_create_duplicate_tracks():
    """
    When a person is fully detected by YOLOX and their face is detected by YuNet,
    the face must match the person box and NOT spawn a second detection or track.
    """
    fusion = DetectionFusion(enabled=True)
    tracker = TemporalTracker(min_hits=1)

    person_box = BoundingBox(0.25, 0.15, 0.55, 0.90)
    face_box = BoundingBox(0.35, 0.18, 0.45, 0.32)  # inside upper body of person

    yolox_dets = [
        Detection(class_name="person", confidence=0.82, box=person_box, sector="center")
    ]
    face_dets = [
        FaceDetection(box=face_box, confidence=0.92)
    ]

    fused = fusion.fuse(yolox_dets, face_detections=face_dets)

    # Exactly 1 fused detection
    assert len(fused) == 1
    assert fused[0].class_name == "person"
    assert fused[0].box == person_box
    # Confidence is reinforced by face
    assert fused[0].confidence == 0.92

    # Feed to TemporalTracker
    now = time.time()
    tracks = tracker.update(fused, now)

    # Exactly 1 track maintained
    active_tracks = [t for t in tracks if t.state in (TrackState.TENTATIVE, TrackState.CONFIRMED)]
    assert len(active_tracks) == 1
    assert active_tracks[0].class_name == "person"
    assert active_tracks[0].box == person_box


# ---------------------------------------------------------------------------
# Test 6: Face-Only Evidence Does Not Fabricate Full-Body Bounding Box
# ---------------------------------------------------------------------------
def test_face_only_evidence_does_not_fabricate_full_body_box():
    """
    When only a face is detected (e.g. user sitting close to webcam),
    the emitted detection must use the actual face bounding box and NOT
    fabricate an extrapolated or full-body box down to y=1.0.
    """
    fusion = DetectionFusion(enabled=True)

    face_box = BoundingBox(0.35, 0.30, 0.65, 0.60)
    yolox_dets: List[Detection] = []  # YOLOX missed or produced no detection
    face_dets = [
        FaceDetection(box=face_box, confidence=0.89)
    ]

    fused = fusion.fuse(yolox_dets, face_detections=face_dets)

    assert len(fused) == 1
    det = fused[0]
    assert det.class_name == "person"
    assert det.confidence == 0.89
    # Must match face box exactly, height = 0.30, NOT extrapolated to 1.0
    assert det.box == face_box
    assert det.box.y_max == 0.60
    assert (det.box.y_max - det.box.y_min) == pytest.approx(0.30, abs=1e-4)


# ---------------------------------------------------------------------------
# Test 7: Human Beside a Genuine Cat Preserves Both Detections
# ---------------------------------------------------------------------------
def test_human_beside_genuine_cat_preserves_both_detections():
    """
    When a scene has both a human face and a genuine cat in distinct locations,
    both detections must be preserved in the fused output.
    """
    fusion = DetectionFusion(enabled=True)

    cat_box = BoundingBox(0.05, 0.40, 0.35, 0.80)
    face_box = BoundingBox(0.60, 0.20, 0.85, 0.50)

    yolox_dets = [
        Detection(class_name="cat", confidence=0.76, box=cat_box, sector="left")
    ]
    face_dets = [
        FaceDetection(box=face_box, confidence=0.91)
    ]

    fused = fusion.fuse(yolox_dets, face_detections=face_dets)

    assert len(fused) == 2
    classes = {d.class_name for d in fused}
    assert classes == {"cat", "person"}

    cat_det = next(d for d in fused if d.class_name == "cat")
    assert cat_det.confidence == 0.76
    assert cat_det.box == cat_box

    person_det = next(d for d in fused if d.class_name == "person")
    assert person_det.confidence == 0.91
    assert person_det.box == face_box


# ---------------------------------------------------------------------------
# Test 8: Uncertain Classifications Do Not Trigger Confident Speech
# ---------------------------------------------------------------------------
def test_uncertain_classifications_do_not_trigger_confident_speech():
    """
    When an ambiguous detection (neither animal nor face is convincingly dominant)
    is marked as uncertain, SceneDecisionEngine must NOT voice confident obstacle alerts.
    """
    fusion = DetectionFusion(enabled=True)
    speech_backend = FakeSpeechBackend()
    speech_manager = SpeechManager(backend=speech_backend)
    decision_engine = SceneDecisionEngine(speech_manager=speech_manager, language="ne")
    analyzer = SceneAnalyzer()
    tracker = TemporalTracker(min_hits=1)

    box = BoundingBox(0.05, 0.40, 0.25, 0.70)
    # Marginal animal score and marginal face score
    yolox_dets = [
        Detection(class_name="cat", confidence=0.42, box=box, sector="left")
    ]
    face_dets = [
        FaceDetection(box=box, confidence=0.52)
    ]

    try:
        fused = fusion.fuse(yolox_dets, face_detections=face_dets)

        # Must be marked as uncertain
        assert len(fused) == 1
        assert fused[0].class_name == "uncertain"

        # Feed to tracking, scene analysis, and decision
        now = time.time()
        tracks = tracker.update(fused, now)
        assessment = analyzer.analyze_scene(tracks, frame_id=1, timestamp=now)
        dispatched = decision_engine.process_scene(assessment, current_time=now)

        # Must be suppressed: no confident obstacle announcements voiced
        assert dispatched is None
        assert len(speech_backend.spoken_history) == 0
    finally:
        speech_manager.shutdown()


# ---------------------------------------------------------------------------
# Test 9: Real YuNet Model Integration on Fixtures
# ---------------------------------------------------------------------------
def test_yunet_real_model_on_fixtures():
    """Verifies that the staged YuNet model weights execute cleanly via YuNetFaceDetector."""
    yunet_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models",
        "face_detection_yunet_2023mar.onnx"
    )
    if not os.path.exists(yunet_path):
        pytest.skip("YuNet model weights not staged.")

    detector = YuNetFaceDetector(model_path=yunet_path)
    assert detector.is_ready()

    # Empty dummy frame: 0 faces
    dummy = np.zeros((320, 320, 3), dtype=np.uint8)
    faces = detector.detect_frame(dummy)
    assert len(faces) == 0

    # Person fixture: full body from distance -> 0 or low-confidence face
    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests",
        "fixtures",
        "test_person.jpg"
    )
    if os.path.exists(fixture_path):
        img_person = cv2.imread(fixture_path)
        faces_person = detector.detect_frame(img_person)
        # Small person in distance should produce at most 1 face with valid coords
        for f in faces_person:
            assert 0.0 <= f.box.x_min < f.box.x_max <= 1.0
            assert 0.0 <= f.box.y_min < f.box.y_max <= 1.0
