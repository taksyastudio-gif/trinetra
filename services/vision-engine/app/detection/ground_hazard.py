"""
Trinetra Ground Hazard & Surface Discontinuity Detector
Specialized computer vision analyzer for detecting street potholes, open drains,
and sudden ground drops in Nepal's urban pedestrian pathways.
Operates strictly on the lower walking path corridor in <3ms.
"""

from dataclasses import dataclass
import logging
from typing import Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger("trinetra.detection.ground")


@dataclass
class GroundHazard:
    detected: bool
    hazard_type: str  # "pothole", "open_trench", "surface_drop", or "none"
    severity: str     # "critical", "warning", or "none"
    confidence: float
    message_ne: str
    message_en: str
    bounding_box: Optional[Tuple[float, float, float, float]] = None  # (ymin, xmin, ymax, xmax) normalized


class GroundHazardDetector:
    """
    Fast geometric and photometric ground hazard detector.
    Analyzes the immediate pedestrian walking path directly ahead (bottom 40% of viewport).
    """

    def __init__(
        self,
        min_contour_area: float = 0.04,  # Minimum 4% of walking corridor area
        dark_pit_thresh: int = 55,       # Intensity threshold for dark trenches/holes
        edge_gradient_thresh: int = 120, # Sobel gradient threshold for sharp vertical drops
    ):
        self.min_contour_area = min_contour_area
        self.dark_pit_thresh = dark_pit_thresh
        self.edge_gradient_thresh = edge_gradient_thresh

    def analyze(self, frame_bgr: np.ndarray) -> GroundHazard:
        """
        Analyzes a camera frame for hazardous road surface defects.
        Returns a structured GroundHazard result.
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return GroundHazard(False, "none", "none", 0.0, "", "")

        h, w = frame_bgr.shape[:2]

        # Define walking corridor: bottom 40% height, central 60% width
        y_start = int(h * 0.58)
        y_end = h
        x_start = int(w * 0.20)
        x_end = int(w * 0.80)

        roi = frame_bgr[y_start:y_end, x_start:x_end]
        if roi.size == 0:
            return GroundHazard(False, "none", "none", 0.0, "", "")

        roi_h, roi_w = roi.shape[:2]
        roi_area = roi_h * roi_w

        # Convert to grayscale
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # 1. Dark Pit / Open Trench Detection (Missing manhole covers, deep mud pits)
        # Deep holes exhibit significantly lower luminance compared to ambient road surface
        # Compute Sobel edge magnitude to distinguish sharp asphalt fractures from soft fabric/pillows
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = cv2.magnitude(grad_x, grad_y)

        median_lum = np.median(gray)
        # Potholes in asphalt have extreme contrast and sharp boundary fractures
        pit_threshold = min(30, int(median_lum * 0.35))
        _, dark_mask = cv2.threshold(gray, pit_threshold, 255, cv2.THRESH_BINARY_INV)

        # Morphological noise filtering
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        cleaned_mask = cv2.morphologyEx(dark_mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(cleaned_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            area_ratio = area / roi_area
            if area_ratio >= 0.06:
                # Mask contour perimeter to check for sharp asphalt edge fracture
                cnt_mask = np.zeros(gray.shape, dtype=np.uint8)
                cv2.drawContours(cnt_mask, [cnt], -1, 255, 3)
                mean_edge_grad = float(np.mean(grad_mag[cnt_mask > 0])) if np.any(cnt_mask > 0) else 0.0
                # Soft pillows / blankets have smooth blurred gradients (< 60); real potholes have sharp fracture edges
                if mean_edge_grad < 60.0:
                    continue
                bx, by, bw, bh = cv2.boundingRect(cnt)
                # Normalize bounding box coordinates to full frame
                norm_box = (
                    (y_start + by) / h,
                    (x_start + bx) / w,
                    (y_start + by + bh) / h,
                    (x_start + bx + bw) / w,
                )
                conf = min(0.95, round(0.70 + (area_ratio * 1.5), 2))
                return GroundHazard(
                    detected=True,
                    hazard_type="pothole",
                    severity="critical" if area_ratio >= 0.08 else "warning",
                    confidence=conf,
                    message_ne="अगाडि जमिनमा खाल्डो छ, होसियार!",
                    message_en="Caution: Pothole or open hole on the ground ahead!",
                    bounding_box=norm_box,
                )

        # 2. Surface Drop / Sudden Trench Edge Detection (Broken slab / curb drop)
        # Uses vertical Sobel edge gradients to identify sharp horizontal drop boundaries
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        abs_sobel_y = np.absolute(sobel_y)
        edge_mask = np.uint8(abs_sobel_y > self.edge_gradient_thresh)

        edge_density = np.sum(edge_mask) / (roi_area * 255)
        if edge_density > 0.06:
            # Significant sharp gradient break spanning the walking corridor
            return GroundHazard(
                detected=True,
                hazard_type="surface_drop",
                severity="warning",
                confidence=0.82,
                message_ne="अगाडि सतह परिवर्तन वा खुड्किलो छ, होसियार!",
                message_en="Caution: Uneven road surface or step drop ahead!",
                bounding_box=((y_start / h), (x_start / w), 1.0, (x_end / w)),
            )

        return GroundHazard(False, "none", "none", 0.0, "", "")
