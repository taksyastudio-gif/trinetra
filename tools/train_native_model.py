"""
Trinetra In-House Model Trainer
Trains TrinetraNet on real-world harvested images (People, Gestures, Ground Hazards, Floor).
100% In-House, Zero ONNX / Zero YOLO dependencies.
"""

import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from PIL import Image
from torch.utils.data import DataLoader, Dataset
import torchvision.transforms as T

# Add vision engine to sys.path
ROOT_DIR = Path(r"D:\trinetra")
ENGINE_DIR = ROOT_DIR / "services" / "vision-engine"
sys.path.insert(0, str(ENGINE_DIR))

from app.detection.model import CLASSES, TrinetraNet

DATASET_DIR = ROOT_DIR / "datasets" / "native_train"
MODEL_SAVE_PATH = ENGINE_DIR / "models" / "trinetra_native_model.pt"


class NativeImageDataset(Dataset):
    def __init__(self, items: list[tuple[Path, int]], transform=None):
        self.items = items
        self.transform = transform

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        img_path, label = self.items[idx]
        img = Image.open(img_path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, label


def prepare_datasets():
    all_items = []
    class_to_idx = {c: i for i, c in enumerate(CLASSES)}

    for cat in CLASSES:
        cat_dir = DATASET_DIR / cat
        if not cat_dir.is_dir():
            continue
        files = list(cat_dir.glob("*.jpg")) + list(cat_dir.glob("*.png"))
        for f in files:
            all_items.append((f, class_to_idx[cat]))

    random.seed(42)
    random.shuffle(all_items)

    split = int(len(all_items) * 0.8)
    train_items = all_items[:split]
    val_items = all_items[split:]

    train_transform = T.Compose([
        T.Resize((64, 64)),
        T.RandomHorizontalFlip(p=0.5),
        T.RandomRotation(degrees=15),
        T.ColorJitter(brightness=0.2, contrast=0.2),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    val_transform = T.Compose([
        T.Resize((64, 64)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    return (
        NativeImageDataset(train_items, train_transform),
        NativeImageDataset(val_items, val_transform),
        len(all_items),
    )


def train_model(epochs: int = 20, batch_size: int = 16, lr: float = 0.001):
    print("=" * 65)
    print("  TRINETRA IN-HOUSE MODEL TRAINING (Zero ONNX / Zero YOLO)")
    print("=" * 65)

    train_ds, val_ds, total_samples = prepare_datasets()
    print(f"Total dataset samples: {total_samples}")
    print(f"Train samples: {len(train_ds)}, Val samples: {len(val_ds)}")
    print(f"Classes ({len(CLASSES)}): {CLASSES}")

    if total_samples < 10:
        print("[Error] Not enough images in dataset. Run fetch_training_images.py first.")
        return False

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    device = torch.device("cpu")
    model = TrinetraNet(num_classes=len(CLASSES)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_val_acc = 0.0

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0

        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * images.size(0)
            _, preds = torch.max(outputs, 1)
            correct += torch.sum(preds == labels.data).item()
            total += labels.size(0)

        scheduler.step()

        train_loss = running_loss / max(total, 1)
        train_acc = correct / max(total, 1)

        # Validation phase
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                loss = criterion(outputs, labels)
                val_loss += loss.item() * images.size(0)
                _, preds = torch.max(outputs, 1)
                val_correct += torch.sum(preds == labels.data).item()
                val_total += labels.size(0)

        epoch_val_acc = val_correct / max(val_total, 1)

        if epoch_val_acc >= best_val_acc:
            best_val_acc = epoch_val_acc
            MODEL_SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), str(MODEL_SAVE_PATH))

        if epoch % 5 == 0 or epoch == epochs:
            print(
                f"Epoch [{epoch:02d}/{epochs:02d}] "
                f"Train Loss: {train_loss:.4f} | Train Acc: {train_acc * 100:.1f}% | "
                f"Val Acc: {epoch_val_acc * 100:.1f}%"
            )

    print("\n" + "=" * 65)
    print(f"  TRAINING COMPLETE! Best Validation Accuracy: {best_val_acc * 100:.1f}%")
    print(f"  Model saved directly to: {MODEL_SAVE_PATH}")
    print("=" * 65)
    return True


if __name__ == "__main__":
    train_model(epochs=35, lr=0.002)
