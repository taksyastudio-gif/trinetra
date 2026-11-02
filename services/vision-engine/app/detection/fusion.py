"""
Trinetra Detection Fusion Layer
Fuses multi-modal detections (YOLOX general object detector + YuNet face detector)
immediately prior to temporal tracking.

Behavior:
1. Matches face detections to existing person detections spatially to prevent duplicate person tracks.
2. Represents unmatched face detections as face-only human evidence, not fabricated full-body detections.
3. Distinguishes false animal artifacts on human faces from genuine animal detections:
   - High-confidence animals (>= 0.60) are NEVER automatically suppressed.
   - Ambiguous detections are preserved as uncertain.
   - Verified false animal artifacts (< 0.60 with high-confidence face >= 0.65) are reclassified as person.
4. Preserves all other general object detections without alteration.
"""

import logging
from typing import List, Optional, Set, Tuple

import numpy as np

from app.detection.face_detector import FaceDetection, YuNetFaceDetector
from app.detection.types import BoundingBox, Detection, classify_sector

logger = logging.getLogger("trinetra.detection.fusion")

ANIMAL_CLASSES: Set[str] = {"cat", "dog"}


def compute_box_intersection(box_a: BoundingBox, box_b: BoundingBox) -> float:
    """Computes the 2D intersection area of two normalized bounding boxes."""
    x_left = max(box_a.x_min, box_b.x_min)
    y_top = max(box_a.y_min, box_b.y_min)
    x_right = min(box_a.x_max, box_b.x_max)
    y_bottom = min(box_a.y_max, box_b.y_max)

    if x_right <= x_left or y_bottom <= y_top:
        return 0.0
    return (x_right - x_left) * (y_bottom - y_top)


def compute_box_containment(inner: BoundingBox, outer: BoundingBox) -> float:
    """
    Computes fraction of inner box contained within outer box.
    Returns: Area(inner ∩ outer) / Area(inner).
    """
    inner_area = inner.area
    if inner_area <= 0.0:
        return 0.0
    inter = compute_box_intersection(inner, outer)
    return inter / inner_area


def compute_box_iou(box_a: BoundingBox, box_b: BoundingBox) -> float:
    """Computes standard Intersection-over-Union (IoU) overlap."""
    inter = compute_box_intersection(box_a, box_b)
    if inter <= 0.0:
        return 0.0
    union = box_a.area + box_b.area - inter
    if union <= 0.0:
        return 0.0
    return inter / union


class DetectionFusion:
    """
    Deterministic detection fusion engine integrating YOLOX and YuNet detections.
    Operates immediately before TemporalTracker.
    """

    def __init__(
        self,
        face_detector: Optional[YuNetFaceDetector] = None,
        face_person_containment_threshold: float = 0.45,
        animal_face_overlap_threshold: float = 0.35,
        genuine_animal_confidence_threshold: float = 0.60,
        confirmed_face_confidence_threshold: float = 0.65,
        enabled: bool = True
    ):
        self.face_detector = face_detector
        self.face_person_containment_threshold = face_person_containment_threshold
        self.animal_face_overlap_threshold = animal_face_overlap_threshold
        self.genuine_animal_confidence_threshold = genuine_animal_confidence_threshold
        self.confirmed_face_confidence_threshold = confirmed_face_confidence_threshold
        self.enabled = enabled

    def fuse(
        self,
        yolox_detections: List[Detection],
        frame_bytes: Optional[bytes] = None,
        frame_bgr: Optional[np.ndarray] = None,
        face_detections: Optional[List[FaceDetection]] = None
    ) -> List[Detection]:
        """
        Executes spatial and evidence fusion between YOLOX detections and face detections.
        Accepts pre-computed face_detections (e.g. for offline testing) or invokes face_detector.
        """
        if not self.enabled:
            return list(yolox_detections)

        # 1. Obtain face detections
        faces: List[FaceDetection] = []
        if face_detections is not None:
            faces = list(face_detections)
        elif self.face_detector and self.face_detector.is_ready():
            if frame_bgr is not None:
                faces = self.face_detector.detect_frame(frame_bgr)
            elif frame_bytes is not None:
                faces = self.face_detector.detect(frame_bytes)

        if not faces:
            return list(yolox_detections)

        # Work on a mutable copy
        active_yolox = list(yolox_detections)
        unmatched_faces: List[FaceDetection] = []

        # 2. Match faces to existing YOLOX "person" detections
        matched_person_indices: Set[int] = set()

        for face in faces:
            matched_person_idx = -1
            best_containment = 0.0

            for p_idx, det in enumerate(active_yolox):
                if det.class_name != "person":
                    continue

                containment = compute_box_containment(face.box, det.box)
                # Also check if face center is enclosed by person box
                center_in_person = (
                    det.box.x_min <= face.box.center_x <= det.box.x_max
                    and det.box.y_min <= face.box.center_y <= det.box.y_max
                )

                if (containment >= self.face_person_containment_threshold or center_in_person) and containment > best_containment:
                    best_containment = containment
                    matched_person_idx = p_idx

            if matched_person_idx >= 0:
                # Face matches existing person: reinforce confidence, do NOT spawn duplicate
                matched_person_indices.add(matched_person_idx)
                existing_p = active_yolox[matched_person_idx]
                boosted_conf = max(existing_p.confidence, face.confidence)
                active_yolox[matched_person_idx] = Detection(
                    class_name="person",
                    confidence=round(boosted_conf, 3),
                    box=existing_p.box,
                    sector=existing_p.sector
                )
            else:
                unmatched_faces.append(face)

        # 3. Analyze unmatched faces against animal detections (cat, dog)
        # Check for false animal artifacts vs genuine animals
        suppressed_animal_indices: Set[int] = set()
        converted_ambiguous_indices: Set[int] = set()
        consumed_face_indices: Set[int] = set()

        for f_idx, face in enumerate(unmatched_faces):
            overlapping_animal_idx = -1
            best_overlap = 0.0

            for a_idx, det in enumerate(active_yolox):
                if det.class_name not in ANIMAL_CLASSES:
                    continue
                if a_idx in suppressed_animal_indices or a_idx in converted_ambiguous_indices:
                    continue

                iou = compute_box_iou(face.box, det.box)
                containment = compute_box_containment(face.box, det.box)
                overlap = max(iou, containment)

                if overlap >= self.animal_face_overlap_threshold and overlap > best_overlap:
                    best_overlap = overlap
                    overlapping_animal_idx = a_idx

            if overlapping_animal_idx >= 0:
                animal_det = active_yolox[overlapping_animal_idx]

                if animal_det.confidence >= self.genuine_animal_confidence_threshold:
                    # Genuine animal (e.g. cat with conf >= 0.60): NEVER suppress
                    # Keep the animal intact; face remains as distinct human evidence
                    pass
                elif face.confidence >= self.confirmed_face_confidence_threshold and animal_det.confidence < self.genuine_animal_confidence_threshold:
                    # Verified false animal artifact on a human face
                    consumed_face_indices.add(f_idx)
                    # Replace with honest face-only human evidence
                    active_yolox[overlapping_animal_idx] = Detection(
                        class_name="person",
                        confidence=face.confidence,
                        box=face.box,
                        sector=classify_sector(face.box)
                    )
                else:
                    # Ambiguous detection (neither animal nor face is convincingly dominant)
                    # Preserve as uncertain: do not make unsupported claims
                    consumed_face_indices.add(f_idx)
                    active_yolox[overlapping_animal_idx] = Detection(
                        class_name="uncertain",
                        confidence=round(max(face.confidence, animal_det.confidence), 3),
                        box=animal_det.box,
                        sector=animal_det.sector
                    )

        # 4. Filter suppressed animal detections
        fused_results: List[Detection] = [
            det for idx, det in enumerate(active_yolox)
            if idx not in suppressed_animal_indices
        ]

        # 5. Add remaining unmatched faces as face-only human evidence
        # (NOT fabricated full-body boxes: bounding box is strictly face.box)
        for f_idx, face in enumerate(unmatched_faces):
            if f_idx in consumed_face_indices:
                continue

            fused_results.append(
                Detection(
                    class_name="person",
                    confidence=face.confidence,
                    box=face.box,
                    sector=classify_sector(face.box)
                )
            )

        return fused_results
