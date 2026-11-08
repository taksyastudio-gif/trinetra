"""
TrinetraNet — 100% In-House Neural Vision Architecture
Lightweight, ultra-fast convolutional network for classifying human presence,
two-way sign language gestures, and spatial ground hazards.
Zero ONNX runtime. Pure PyTorch native inference.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

CLASSES = [
    "person",
    "sign_namaste",
    "sign_thumbs_up",
    "sign_fist",
    "hazard_pothole",
    "safe_ground",
    "stairs",
    "vehicle",
    "chair",
    "door",
]


class TrinetraNet(nn.Module):
    """
    Proprietary ultra-lightweight vision model designed for real-time edge CPU inference (<2ms).
    """

    def __init__(self, num_classes: int = len(CLASSES)):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2),  # 64 -> 32

            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2),  # 32 -> 16

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((4, 4)),  # 64 x 4 x 4
        )
        self.classifier = nn.Sequential(
            nn.Dropout(p=0.35),
            nn.Linear(64 * 4 * 4, 128),
            nn.ReLU(inplace=True),
            nn.Linear(128, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = torch.flatten(x, 1)
        return self.classifier(x)


class NativeClassifier:
    """Wrapper for fast, safe inference with TrinetraNet on CPU."""

    def __init__(self, model_path: Optional[str] = None):
        self.device = torch.device("cpu")
        self.classes = CLASSES
        self.model = TrinetraNet(num_classes=len(self.classes))
        self.is_loaded = False

        if model_path and Path(model_path).is_file():
            try:
                state_dict = torch.load(model_path, map_location=self.device)
                self.model.load_state_dict(state_dict)
                self.model.eval()
                self.is_loaded = True
            except Exception as e:
                print(f"[TrinetraNet] Failed to load weights: {e}")

    def predict_crop(self, bgr_crop: np.ndarray) -> Tuple[str, float]:
        """
        Runs inference on a proposed bounding box crop.
        Returns: (class_name, confidence)
        """
        if not self.is_loaded or bgr_crop is None or bgr_crop.size == 0:
            return ("unknown", 0.0)

        # Preprocess: RGB -> Resize(64, 64) -> Float32 -> Normalize
        rgb = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (64, 64), interpolation=cv2.INTER_LINEAR)
        tensor = torch.from_numpy(resized).permute(2, 0, 1).float() / 255.0

        # Standard ImageNet normalization
        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        tensor = (tensor - mean) / std
        tensor = tensor.unsqueeze(0)  # Shape: (1, 3, 64, 64)

        with torch.no_grad():
            logits = self.model(tensor)
            probs = F.softmax(logits, dim=1)[0]
            top_idx = torch.argmax(probs).item()
            conf = probs[top_idx].item()
            predicted_class = self.classes[top_idx]

        return (predicted_class, float(conf))
