"""Trains a MobileNetV3-Small classifier on real Nepali banknote splits and exports to ONNX."""

import sys
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import json
from pathlib import Path
import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models

DENOMINATIONS = [5, 10, 20, 50, 100, 500, 1000]
LABEL_TO_IDX = {denom: idx for idx, denom in enumerate(DENOMINATIONS)}

class BanknoteDataset(Dataset):
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
            # Fallback black image
            img = np.zeros((224, 224, 3), dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        img = cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA)

        # Simple data augmentation for training
        if self.is_train:
            if np.random.rand() > 0.5:
                img = cv2.flip(img, 1) # Horizontal flip
            # Random slight brightness
            alpha = np.random.uniform(0.85, 1.15)
            img = np.clip(img * alpha, 0, 255).astype(np.uint8)

        # Normalize with ImageNet mean/std
        normalized = img.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        normalized = (normalized - mean) / std
        tensor = torch.from_numpy(np.transpose(normalized, (2, 0, 1))).float()

        target_idx = LABEL_TO_IDX.get(int(rec["label"]), 1)
        return tensor, target_idx

def main():
    root = Path("datasets/currency")
    splits_dir = root / "splits"

    train_recs = json.loads((splits_dir / "train.json").read_text(encoding="utf-8"))
    val_recs = json.loads((splits_dir / "validation.json").read_text(encoding="utf-8"))
    test_recs = json.loads((splits_dir / "test.json").read_text(encoding="utf-8"))

    print(f"Dataset splits: {len(train_recs)} train, {len(val_recs)} val, {len(test_recs)} test")

    train_ds = BanknoteDataset(train_recs, root, is_train=True)
    val_ds = BanknoteDataset(val_recs, root, is_train=False)
    test_ds = BanknoteDataset(test_recs, root, is_train=False)

    train_loader = DataLoader(train_ds, batch_size=8, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=8, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=8, shuffle=False)

    # MobileNetV3 Small with transfer learning / pretrained weights
    print("Initializing MobileNetV3-Small with pretrained ImageNet weights...")
    try:
        model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
        print("Loaded official torchvision pretrained weights.")
    except Exception as exc:
        print(f"Pretrained weights unavailable offline ({exc}), initializing architecture...")
        model = models.mobilenet_v3_small(weights=None)

    # Replace last layer with 7 classes
    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, len(DENOMINATIONS))

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-4, weight_decay=1e-3)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=12, eta_min=1e-5)

    num_epochs = 12
    print(f"Training model for {num_epochs} epochs on CPU with CosineAnnealingLR...")
    model.train()
    for epoch in range(num_epochs):
        total_loss = 0.0
        correct = 0
        total = 0
        for tensors, targets in train_loader:
            optimizer.zero_grad()
            outputs = model(tensors)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()

            total_loss += loss.item() * tensors.size(0)
            preds = outputs.argmax(dim=1)
            correct += (preds == targets).sum().item()
            total += targets.size(0)

        scheduler.step()
        epoch_acc = correct / max(1, total)
        current_lr = scheduler.get_last_lr()[0]
        print(f"Epoch {epoch+1:2d}/{num_epochs} - Loss: {total_loss/max(1, total):.4f} - Train Acc: {epoch_acc*100:5.1f}% - lr: {current_lr:.6f}")

    # Evaluate on Validation
    model.eval()
    val_correct = 0
    val_total = 0
    with torch.no_grad():
        for tensors, targets in val_loader:
            outputs = model(tensors)
            preds = outputs.argmax(dim=1)
            val_correct += (preds == targets).sum().item()
            val_total += targets.size(0)

    val_acc = val_correct / max(1, val_total)
    print(f"Validation Accuracy: {val_acc*100:.2f}% ({val_correct}/{val_total})")

    # Evaluate on Test
    test_correct = 0
    test_total = 0
    test_predictions = []
    with torch.no_grad():
        for tensors, targets in test_loader:
            outputs = model(tensors)
            preds = outputs.argmax(dim=1)
            for p, t in zip(preds, targets):
                pred_denom = DENOMINATIONS[p.item()]
                true_denom = DENOMINATIONS[t.item()]
                test_predictions.append({"label": true_denom, "prediction": pred_denom})
                if p == t:
                    test_correct += 1
                test_total += 1

    test_acc = test_correct / max(1, test_total)
    print(f"Independent Test Accuracy: {test_acc*100:.2f}% ({test_correct}/{test_total})")

    # Save test predictions for evaluate_models.py
    pred_path = Path("docs/currency_test_predictions.jsonl")
    with pred_path.open("w", encoding="utf-8") as f:
        for r in test_predictions:
            f.write(json.dumps(r) + "\n")

    # Export to ONNX
    print("Exporting model to ONNX...")
    out_dir = Path("services/vision-engine/models/currency/v1")
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_file = out_dir / "currency_classifier.onnx"

    # Save PyTorch model checkpoint before ONNX export
    ckpt_file = out_dir / "currency_classifier.pt"
    torch.save(model.state_dict(), str(ckpt_file))
    print(f"PyTorch checkpoint saved to {ckpt_file}")

    dummy_input = torch.randn(1, 3, 224, 224, dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_file),
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch_size"}, "logits": {0: "batch_size"}},
        opset_version=18
    )

    import hashlib
    digest = hashlib.sha256(onnx_file.read_bytes()).hexdigest()
    meta = {
        "version": "v1",
        "architecture": "mobilenet_v3_small",
        "input_size": 224,
        "classes": DENOMINATIONS,
        "val_accuracy": round(val_acc, 4),
        "test_accuracy": round(test_acc, 4),
        "sha256": digest
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Model successfully saved to {onnx_file} (SHA256: {digest[:16]}...)")

if __name__ == "__main__":
    main()
