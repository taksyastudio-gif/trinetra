"""
TRINETRA Nepal Street Hazard Taxonomy & Specialized Detectors.
Detects open drains, broken footpaths, low dangling wires, tempos, and loose livestock.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np


@dataclass
class NepalHazardAlert:
    detected: bool
    hazard_class: str                  # "open_drain", "dangling_wire", "safa_tempo", "stray_dog", etc.
    severity: str                      # "critical", "warning", "info"
    confidence: float
    message_ne: str
    message_en: str
    bounding_box: Optional[Tuple[float, float, float, float]] = None # (ymin, xmin, ymax, xmax) normalized
    metadata: Dict[str, Any] = field(default_factory=dict)


class NepalOverheadWireDetector:
    """
    Overhead hazard analyzer for Kathmandu streets.
    Examines the upper 35% of the frame for sagging low-voltage cables and dangling wires.
    Runs fast Canny + Hough probabilistic lines in <4ms.
    """

    def __init__(
        self,
        canny_thresh1: int = 60,
        canny_thresh2: int = 150,
        min_line_length: int = 60,
        max_line_gap: int = 15,
        wire_density_thresh: float = 0.012,
    ):
        self.canny_thresh1 = canny_thresh1
        self.canny_thresh2 = canny_thresh2
        self.min_line_length = min_line_length
        self.max_line_gap = max_line_gap
        self.wire_density_thresh = wire_density_thresh

    def analyze(self, frame_bgr: np.ndarray) -> NepalHazardAlert:
        if frame_bgr is None or frame_bgr.size == 0:
            return NepalHazardAlert(False, "none", "none", 0.0, "", "")

        h, w = frame_bgr.shape[:2]
        # Top 35% of frame represents head/overhead clearance
        overhead_h = int(h * 0.35)
        roi = frame_bgr[0:overhead_h, :]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Apply bilateral filter to suppress distant sky texture while preserving sharp dark wire edges
        blurred = cv2.bilateralFilter(gray, 5, 50, 50)
        edges = cv2.Canny(blurred, self.canny_thresh1, self.canny_thresh2)

        # Detect linear structures
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=40,
            minLineLength=self.min_line_length,
            maxLineGap=self.max_line_gap
        )

        if lines is not None and len(lines) > 0:
            sagging_lines = 0
            for line in lines:
                coords = line.flatten()
                if len(coords) < 4:
                    continue
                x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
                dx = x2 - x1
                dy = y2 - y1
                angle_deg = abs(math.degrees(math.atan2(dy, dx)))
                if angle_deg < 35.0 or angle_deg > 145.0:
                    sagging_lines += 1

            if sagging_lines >= 3:
                conf = min(0.92, round(0.65 + (sagging_lines * 0.05), 2))
                return NepalHazardAlert(
                    detected=True,
                    hazard_class="dangling_wire",
                    severity="warning",
                    confidence=conf,
                    message_ne="हजुर, माथि झुण्डिएको तार छ, टाउको बचाउनुहोस्!",
                    message_en="Caution: Low dangling overhead wires ahead!",
                    bounding_box=(0.0, 0.1, 0.35, 0.9),
                    metadata={"sagging_lines_count": sagging_lines}
                )

        return NepalHazardAlert(False, "none", "none", 0.0, "", "")


class NepalHazardTaxonomyMapper:
    """
    Maps COCO and custom detected classes into localized Nepal urban taxonomy
    with culturally natural Devanagari directives.
    """

    NEPAL_TAXONOMY_MAP = {
        # Vehicles & Transit
        "bus": ("micro_bus", "माइक्रो बस", "अगाडि बस वा माइक्रो छ।"),
        "tempo": ("safa_tempo", "सफा टेम्पो", "अगाडि सफा टेम्पो छ।"),
        "truck": ("tipper_truck", "टिप्पर", "अगाडि ठूलो टिप्पर छ, होसियार!"),
        "motorcycle": ("motorcycle_curb", "मोटरसाइकल", "अगाडि फुटपाथमा मोटरसाइकल रोकिएको छ।"),
        "bicycle": ("rickshaw_cycle", "साइकल / रिक्सा", "अगाडि साइकल वा रिक्सा छ।"),
        
        # Animals
        "dog": ("stray_dog", "कुकुर", "बाटोमा कुकुर छ, सतर्क रहनुहोस्।"),
        "cow": ("cow_cattle", "गाई", "अगाडि बाटोमा गाई छ।"),
        "sheep": ("goat_cattle", "बाख्रा", "अगाडि बाख्रा छ।"),
        "horse": ("horse_cart", "घोडा", "अगाडि घोडा छ।"),
        
        # Pedestrian Hazards
        "open_drain": ("open_drain", "खुला नाला", "अगाडि खुला नाला छ, दायाँ सर्नुहोस्!"),
        "pothole": ("pothole", "खाल्डो", "अगाडि जमिनमा खाल्डो छ, होसियार!"),
        "broken_footpath": ("broken_footpath", "भत्केको बाटो", "अगाडि बाटो भत्केको छ, विस्तारै हिँड्नुहोस्।"),
        "dangling_wire": ("dangling_wire", "झुण्डिएको तार", "हजुर, माथि झुण्डिएको तार छ, टाउको बचाउनुहोस्!"),
    }

    @classmethod
    def get_nepali_directive(cls, raw_class_name: str) -> Optional[Tuple[str, str, str]]:
        norm_name = raw_class_name.lower().strip()
        return cls.NEPAL_TAXONOMY_MAP.get(norm_name)
