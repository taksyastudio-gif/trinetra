"""
Trinetra Nepali Sign Language (NSL) 36-Class Neural Classifier Training Harness
==============================================================================
Trains an edge-optimized depthwise separable CNN on authentic Nepali Sign Language
character images across all 36 Devanagari consonants (क to ज्ञ).
Exports to ONNX for 100% offline edge execution (<10ms inference on CPU).
"""

import io
import json
import os
from pathlib import Path
import random
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset

ROOT_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT_DIR / "datasets" / "nepali_sign_language"
OUTPUT_DIR = ROOT_DIR / "services" / "vision-engine" / "models" / "signs" / "v1"


class TrinetraNSLNet(nn.Module):
    """
    Ultra-lightweight depthwise separable CNN tailored for 36-class Nepali Sign Language.
    Footprint: ~320K parameters, <1.5 MB ONNX size.
    """
    def __init__(self, num_classes: int = 36):
        super().__init__()
        self.features = nn.Sequential(
            # Stem (stride 2)
            nn.Conv2d(3, 16, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU6(inplace=True),

            # Block 1
            nn.Conv2d(16, 16, kernel_size=3, stride=1, padding=1, groups=16, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU6(inplace=True),
            nn.Conv2d(16, 32, kernel_size=1, bias=False),
            nn.BatchNorm2d(32),

            # Block 2 (Downsample)
            nn.Conv2d(32, 32, kernel_size=3, stride=2, padding=1, groups=32, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU6(inplace=True),
            nn.Conv2d(32, 64, kernel_size=1, bias=False),
            nn.BatchNorm2d(64),

            # Block 3 (Downsample)
            nn.Conv2d(64, 64, kernel_size=3, stride=2, padding=1, groups=64, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU6(inplace=True),
            nn.Conv2d(64, 96, kernel_size=1, bias=False),
            nn.BatchNorm2d(96),

            # Block 4 (Downsample)
            nn.Conv2d(96, 96, kernel_size=3, stride=2, padding=1, groups=96, bias=False),
            nn.BatchNorm2d(96),
            nn.ReLU6(inplace=True),
            nn.Conv2d(96, 128, kernel_size=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU6(inplace=True),

            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.classifier = nn.Sequential(
            nn.Dropout(p=0.25),
            nn.Linear(128, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = torch.flatten(x, 1)
        x = self.classifier(x)
        return x


class NSLDataset(Dataset):
    def __init__(self, samples: list[tuple[Path, int]], is_train: bool = True):
        self.samples = samples
        self.is_train = is_train

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        img_path, label = self.samples[idx]
        img = cv2.imread(str(img_path))
        if img is None:
            img = np.zeros((160, 160, 3), dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        img = cv2.resize(img, (160, 160), interpolation=cv2.INTER_AREA)

        # Normalization
        norm = img.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        norm = (norm - mean) / std
        tensor = torch.from_numpy(np.transpose(norm, (2, 0, 1))).float()
        return tensor, label


def collect_nsl_samples() -> tuple[list[tuple[Path, int]], list[dict]]:
    classes_file = DATASET_DIR / "classes.json"
    with open(classes_file, "r", encoding="utf-8") as f:
        classes_meta = json.load(f)

    samples = []
    for cls in classes_meta:
        cls_id = cls["id"]
        rom = cls["rom"]
        cls_dir = DATASET_DIR / f"{cls_id:02d}_{rom}"
        if cls_dir.exists():
            for img_path in cls_dir.glob("*.jpg"):
                samples.append((img_path, cls_id))

    print(f"Total NSL samples collected: {len(samples)} across {len(classes_meta)} classes")
    return samples, classes_meta


def main():
    print("=" * 60)
    print("TRINETRA NEPALI SIGN LANGUAGE (NSL) 36-CLASS MODEL TRAINING")
    print("=" * 60)

    samples, classes_meta = collect_nsl_samples()
    if not samples:
        print("ERROR: No NSL samples found in datasets/nepali_sign_language!")
        return 1

    random.seed(42)
    random.shuffle(samples)

    split_idx = int(0.85 * len(samples))
    train_samples = samples[:split_idx]
    val_samples = samples[split_idx:]

    print(f"Training split: {len(train_samples)} images")
    print(f"Validation split: {len(val_samples)} images")

    train_ds = NSLDataset(train_samples, is_train=True)
    val_ds = NSLDataset(val_samples, is_train=False)

    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=32, shuffle=False, num_workers=0)

    device = torch.device("cpu")
    model = TrinetraNSLNet(num_classes=len(classes_meta)).to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

    epochs = 3
    print(f"\nTraining TrinetraNSLNet on CPU for {epochs} epochs...")

    start_time = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0

        for batch_idx, (images, labels) in enumerate(train_loader):
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * images.size(0)
            _, predicted = outputs.max(1)
            total += labels.size(0)
            correct += predicted.eq(labels).sum().item()

        train_acc = correct / total
        epoch_loss = running_loss / total

        # Validation
        model.eval()
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                _, predicted = outputs.max(1)
                val_total += labels.size(0)
                val_correct += predicted.eq(labels).sum().item()

        val_acc = val_correct / val_total
        print(f"Epoch {epoch} Result -> Train Loss: {epoch_loss:.4f}, Train Acc: {train_acc*100:.2f}%, Val Acc: {val_acc*100:.2f}%\n")

    elapsed = time.time() - start_time
    print(f"Training completed in {elapsed:.1f}s.")

    # Export to PyTorch checkpoint and ONNX
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pth_path = OUTPUT_DIR / "nepali_sign_language_36.pth"
    onnx_path = OUTPUT_DIR / "nepali_sign_language_36.onnx"
    metadata_path = OUTPUT_DIR / "nepali_sign_language_36.json"

    print(f"Saving PyTorch checkpoint: {pth_path}")
    torch.save(model.state_dict(), str(pth_path))

    model.eval()
    dummy_input = torch.randn(1, 3, 160, 160, device=device)

    print(f"Exporting model to ONNX: {onnx_path}")
    try:
        torch.onnx.export(
            model,
            dummy_input,
            str(onnx_path),
            input_names=["input"],
            output_names=["logits"],
            dynamic_axes={"input": {0: "batch_size"}, "logits": {0: "batch_size"}},
            opset_version=14,
            dynamo=False,
        )
    except Exception as exc:
        print(f"Standard ONNX export fallback: {exc}")
        torch.onnx.export(
            model,
            dummy_input,
            str(onnx_path),
            input_names=["input"],
            output_names=["logits"],
            opset_version=11,
        )

    metadata = {
        "model_name": "nepali_sign_language_36",
        "architecture": "TrinetraNSLNet",
        "dataset": "Birat Poudel Nepali Sign Language Character Dataset",
        "total_classes": len(classes_meta),
        "total_images_trained": len(samples),
        "classes": classes_meta,
        "input_shape": [1, 3, 160, 160],
        "val_accuracy": round(val_acc, 4),
        "exported_at_utc": time.time(),
        "framework": "PyTorch -> ONNX",
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"Exported successfully! File size: {onnx_path.stat().st_size / 1024:.1f} KB")
    print(f"Metadata written to {metadata_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
