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
NOTE_SUSPECT_CLASSES: Set[str] = {"cell phone", "book"}


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
        currency_classifier_path: Optional[str] = None,
        enabled: bool = True
    ):
        self.face_detector = face_detector
        self.face_person_containment_threshold = face_person_containment_threshold
        self.animal_face_overlap_threshold = animal_face_overlap_threshold
        self.genuine_animal_confidence_threshold = genuine_animal_confidence_threshold
        self.confirmed_face_confidence_threshold = confirmed_face_confidence_threshold
        self.currency_classifier_path = currency_classifier_path
        self._currency_session = None
        self.enabled = enabled

    def _get_currency_session(self):
        if self._currency_session is None and self.currency_classifier_path:
            from pathlib import Path
            p = Path(self.currency_classifier_path)
            if p.is_file():
                try:
                    import onnxruntime as ort
                    opts = ort.SessionOptions()
                    opts.intra_op_num_threads = 1
                    self._currency_session = ort.InferenceSession(str(p), opts, providers=["CPUExecutionProvider"])
                except Exception as exc:
                    logger.debug(f"Currency session init error in fusion: {exc}")
                    self._currency_session = False
            else:
                self._currency_session = False
        return self._currency_session if self._currency_session is not False else None

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

        # Work on a mutable copy
        active_yolox = list(yolox_detections)
        unmatched_faces: List[FaceDetection] = []
        matched_person_indices: Set[int] = set()
        suppressed_animal_indices: Set[int] = set()
        converted_ambiguous_indices: Set[int] = set()
        consumed_face_indices: Set[int] = set()

        if faces:
            # 2. Match faces to existing YOLOX "person" detections
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
                        pass
                    elif face.confidence >= self.confirmed_face_confidence_threshold and animal_det.confidence < self.genuine_animal_confidence_threshold:
                        consumed_face_indices.add(f_idx)
                        active_yolox[overlapping_animal_idx] = Detection(
                            class_name="person",
                            confidence=face.confidence,
                            box=face.box,
                            sector=classify_sector(face.box)
                        )
                    else:
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

        # 4b. Nepali Currency Fast Verification (Auto-inspect handheld rectangular suspects like 'cell phone')
        curr_session = self._get_currency_session()
        if curr_session is not None and (frame_bgr is not None or frame_bytes is not None):
            try:
                import cv2
                img = frame_bgr
                if img is None and frame_bytes:
                    img = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)

                if img is not None:
                    h, w = img.shape[:2]
                    for idx, det in enumerate(fused_results):
                        if det.class_name in NOTE_SUSPECT_CLASSES:
                            # Extract bounding box crop
                            x1 = max(0, int(det.box.x_min * w))
                            y1 = max(0, int(det.box.y_min * h))
                            x2 = min(w, int(det.box.x_max * w))
                            y2 = min(h, int(det.box.y_max * h))
                            if (x2 - x1) >= 40 and (y2 - y1) >= 40:
                                crop = img[y1:y2, x1:x2]
                                rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                                resized = cv2.resize(rgb_crop, (224, 224), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
                                mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
                                std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
                                tensor = np.transpose((resized - mean) / std, (2, 0, 1))[np.newaxis, ...]
                                inp_name = curr_session.get_inputs()[0].name
                                logits = curr_session.run(None, {inp_name: tensor})[0][0]
                                exp_l = np.exp(logits - np.max(logits))
                                probs = exp_l / np.sum(exp_l)
                                best_idx = int(np.argmax(probs))
                                best_conf = float(probs[best_idx])
                                denoms = [5, 10, 20, 50, 100, 500, 1000]

                                # If currency confidence is strong (>= 0.60), reclassify directly!
                                if best_conf >= 0.60:
                                    denom_val = denoms[best_idx]
                                    fused_results[idx] = Detection(
                                        class_name=f"nepali_note_{denom_val}",
                                        confidence=round(best_conf, 2),
                                        box=det.box,
                                        sector=det.sector
                                    )
                                    logger.info(f"Reclassified {det.class_name} -> nepali_note_{denom_val} ({best_conf*100:.1f}%)")
            except Exception as exc:
                logger.debug(f"Currency fusion check skipped: {exc}")

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
