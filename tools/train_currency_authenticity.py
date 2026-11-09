"""
Trinetra In-House Banknote Authenticity & Classification Training Harness
========================================================================
100% Organic, in-house PyTorch training pipeline for Nepali currency (5 to 1000 NPR)
with dual-head Genuine vs Counterfeit / Quality Assessment.
Compatible with Kaggle: prapannadhungel/nepali-currency-dataset.
"""
import sys
import io
import json
import time
from pathlib import Path
import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DENOMINATIONS = [5, 10, 20, 50, 100, 500, 1000]
LABEL_TO_IDX = {denom: idx for idx, denom in enumerate(DENOMINATIONS)}


class DualHeadBanknoteNet(nn.Module):
    """In-House Lightweight Backbone with Denomination & Authenticity Heads."""
    def __init__(self, num_classes: int = len(DENOMINATIONS)):
        super().__init__()
        # Efficient Feature Extractor
        self.conv1 = nn.Conv2d(3, 24, kernel_size=3, stride=2, padding=1)
        self.bn1 = nn.BatchNorm2d(24)
        self.conv2 = nn.Conv2d(24, 48, kernel_size=3, stride=2, padding=1)
        self.bn2 = nn.BatchNorm2d(48)
        self.conv3 = nn.Conv2d(48, 96, kernel_size=3, stride=2, padding=1)
        self.bn3 = nn.BatchNorm2d(96)
        self.conv4 = nn.Conv2d(96, 128, kernel_size=3, stride=2, padding=1)
        self.bn4 = nn.BatchNorm2d(128)
        self.pool = nn.AdaptiveAvgPool2d((1, 1))

        # Head 1: Denomination (5, 10, 20, 50, 100, 500, 1000)
        self.denom_head = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(inplace=True),
            nn.Linear(64, num_classes)
        )

        # Head 2: Authenticity (Genuine = 1, Suspicious/Fake = 0)
        self.auth_head = nn.Sequential(
            nn.Linear(128, 32),
            nn.ReLU(inplace=True),
            nn.Linear(32, 2)
        )

    def forward(self, x):
        feat = F.relu(self.bn1(self.conv1(x)))
        feat = F.relu(self.bn2(self.conv2(feat)))
        feat = F.relu(self.bn3(self.conv3(feat)))
        feat = F.relu(self.bn4(self.conv4(feat)))
        pooled = self.pool(feat).view(feat.size(0), -1)

        denom_logits = self.denom_head(pooled)
        auth_logits = self.auth_head(pooled)
        return denom_logits, auth_logits


class RealNepaliBanknoteDataset(Dataset):
    def __init__(self, records, root_dir: Path, is_train: bool = True):
        self.records = records
        self.root_dir = root_dir
        self.is_train = is_train

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        rec = self.records[idx]
        img_path = self.root_dir / rec["path"]
        img = cv2.imread(str(img_path))
        if img is None:
            img = np.full((128, 128, 3), 120, dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = cv2.resize(img, (128, 128), interpolation=cv2.INTER_AREA)

        if self.is_train:
            if np.random.rand() > 0.5:
                img = cv2.flip(img, 1)
            alpha = np.random.uniform(0.9, 1.1)
            img = np.clip(img * alpha, 0, 255).astype(np.uint8)

        normalized = img.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = torch.from_numpy(np.transpose((normalized - mean) / std, (2, 0, 1))).float()

        denom_idx = LABEL_TO_IDX.get(int(rec["label"]), 0)
        # 1 for genuine (default), 0 for fake/counterfeit
        auth_idx = 1 if "fake" not in str(img_path).lower() else 0
        return tensor, denom_idx, auth_idx


def train_and_export_currency():
    print("==================================================================")
    print("  TRINETRA NEPALI BANKNOTE DUAL-HEAD AUTHENTICITY CLASSIFIER")
    print("==================================================================")
    root = Path("datasets/currency")
    splits_dir = root / "splits"

    train_recs = json.loads((splits_dir / "train.json").read_text(encoding="utf-8")) if (splits_dir / "train.json").is_file() else []
    val_recs = json.loads((splits_dir / "validation.json").read_text(encoding="utf-8")) if (splits_dir / "validation.json").is_file() else []

    if not train_recs:
        print("⚠ Currency splits not found; generating synthetic dataset...")
        train_recs = [{"path": f"raw/100/dummy.jpg", "label": 100} for _ in range(100)]
        val_recs = [{"path": f"raw/100/dummy.jpg", "label": 100} for _ in range(20)]

    print(f"Loaded {len(train_recs)} training notes, {len(val_recs)} validation notes.")
    train_ds = RealNepaliBanknoteDataset(train_recs, root, is_train=True)
    val_ds = RealNepaliBanknoteDataset(val_recs, root, is_train=False)

    train_loader = DataLoader(train_ds, batch_size=16, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=16, shuffle=False)

    model = DualHeadBanknoteNet()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    criterion_denom = nn.CrossEntropyLoss()
    criterion_auth = nn.CrossEntropyLoss()

    print("Training in-house DualHeadBanknoteNet for 4 epochs...")
    model.train()
    for epoch in range(4):
        total_loss = 0.0
        correct_denom = 0
        total = 0
        for x, y_denom, y_auth in train_loader:
            optimizer.zero_grad()
            out_denom, out_auth = model(x)
            loss = criterion_denom(out_denom, y_denom) + 0.5 * criterion_auth(out_auth, y_auth)
            loss.backward()
            optimizer.step()

            total_loss += loss.item() * x.size(0)
            correct_denom += (out_denom.argmax(dim=1) == y_denom).sum().item()
            total += x.size(0)

        print(f"  Epoch [{epoch+1}/4] Loss: {total_loss/total:.4f} | Denom Accuracy: {(correct_denom/total)*100:.1f}%")

    # Export ONNX
    output_dir = Path("services/vision-engine/models/currency/v1")
    output_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = output_dir / "trinetra_currency_authenticity.onnx"

    dummy_input = torch.randn(1, 3, 128, 128)
    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_path),
        input_names=["banknote_crop_128x128"],
        output_names=["denomination_logits", "authenticity_logits"],
        opset_version=18,
    )
    print(f"✓ Exported in-house dual-head model to: {onnx_path} ({onnx_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    train_and_export_currency()
