"""
Trinetra Nepali Sign Language (NSL) Dataset Extractor & Augmenter
================================================================
Extracts authentic Nepali Sign Language character images (classes 0-35)
from Birat Poudel's repository and notebook outputs.
Generates a structured, augmented dataset in datasets/nepali_sign_language/.
"""

import base64
import io
import json
import os
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
NOTEBOOK_PATH = ROOT_DIR / "datasets" / "nsl_updated_raw" / "nepali_sign_language.ipynb"
OUTPUT_DIR = ROOT_DIR / "datasets" / "nepali_sign_language"

NSL_36_CLASSES = [
    {"id": 0, "char": "क", "rom": "ka", "name": "Ka"},
    {"id": 1, "char": "ख", "rom": "kha", "name": "Kha"},
    {"id": 2, "char": "ग", "rom": "ga", "name": "Ga"},
    {"id": 3, "char": "घ", "rom": "gha", "name": "Gha"},
    {"id": 4, "char": "ङ", "rom": "nga", "name": "Nga"},
    {"id": 5, "char": "च", "rom": "cha", "name": "Cha"},
    {"id": 6, "char": "छ", "rom": "chha", "name": "Chha"},
    {"id": 7, "char": "ज", "rom": "ja", "name": "Ja"},
    {"id": 8, "char": "झ", "rom": "jha", "name": "Jha"},
    {"id": 9, "char": "ञ", "rom": "yna", "name": "Yna"},
    {"id": 10, "char": "ट", "rom": "ta1", "name": "Ta (Retroflex)"},
    {"id": 11, "char": "ठ", "rom": "tha1", "name": "Tha (Retroflex)"},
    {"id": 12, "char": "ड", "rom": "da1", "name": "Da (Retroflex)"},
    {"id": 13, "char": "ढ", "rom": "dha1", "name": "Dha (Retroflex)"},
    {"id": 14, "char": "ण", "rom": "na1", "name": "Na (Retroflex)"},
    {"id": 15, "char": "त", "rom": "ta2", "name": "Ta (Dental)"},
    {"id": 16, "char": "थ", "rom": "tha2", "name": "Tha (Dental)"},
    {"id": 17, "char": "द", "rom": "da2", "name": "Da (Dental)"},
    {"id": 18, "char": "ध", "rom": "dha2", "name": "Dha (Dental)"},
    {"id": 19, "char": "न", "rom": "na2", "name": "Na (Dental)"},
    {"id": 20, "char": "प", "rom": "pa", "name": "Pa"},
    {"id": 21, "char": "फ", "rom": "pha", "name": "Pha"},
    {"id": 22, "char": "ब", "rom": "ba", "name": "Ba"},
    {"id": 23, "char": "भ", "rom": "bha", "name": "Bha"},
    {"id": 24, "char": "म", "rom": "ma", "name": "Ma"},
    {"id": 25, "char": "य", "rom": "ya", "name": "Ya"},
    {"id": 26, "char": "र", "rom": "ra", "name": "Ra"},
    {"id": 27, "char": "ल", "rom": "la", "name": "La"},
    {"id": 28, "char": "व", "rom": "wa", "name": "Wa"},
    {"id": 29, "char": "श", "rom": "sha1", "name": "Sha (Palatal)"},
    {"id": 30, "char": "ष", "rom": "sha2", "name": "Sha (Retroflex)"},
    {"id": 31, "char": "स", "rom": "sa", "name": "Sa"},
    {"id": 32, "char": "ह", "rom": "ha", "name": "Ha"},
    {"id": 33, "char": "क्ष", "rom": "kshya", "name": "Kshya"},
    {"id": 34, "char": "त्र", "rom": "tra", "name": "Tra"},
    {"id": 35, "char": "ज्ञ", "rom": "gyan", "name": "Gyana"},
]


def extract_base_samples():
    print(f"Loading notebook from {NOTEBOOK_PATH}...")
    with open(NOTEBOOK_PATH, "r", encoding="utf-8") as f:
        nb = json.load(f)

    cell15 = nb["cells"][15]
    png_outputs = [o for o in cell15.get("outputs", []) if "image/png" in o.get("data", {})]
    print(f"Found {len(png_outputs)} class figures in Cell 15")

    total_extracted = 0
    for class_idx, out in enumerate(png_outputs):
        if class_idx >= len(NSL_36_CLASSES):
            break

        class_meta = NSL_36_CLASSES[class_idx]
        class_dir = OUTPUT_DIR / f"{class_idx:02d}_{class_meta['rom']}"
        class_dir.mkdir(parents=True, exist_ok=True)

        png_b64 = out["data"]["image/png"]
        fig_img = Image.open(io.BytesIO(base64.b64decode(png_b64))).convert("RGB")
        w, h = fig_img.size

        # Slices 5 subplots per figure
        sub_w = w / 5.0
        for sample_i in range(5):
            left = int(sample_i * sub_w)
            right = int((sample_i + 1) * sub_w)
            sub = fig_img.crop((left, 0, right, h))

            arr = np.array(sub)
            non_white = np.where(arr < 250)
            if len(non_white[0]) > 0:
                min_y, max_y = np.min(non_white[0]), np.max(non_white[0])
                min_x, max_x = np.min(non_white[1]), np.max(non_white[1])
                # Add small margin
                margin = 4
                min_y = max(0, min_y - margin)
                min_x = max(0, min_x - margin)
                max_y = min(h, max_y + margin)
                max_x = min(int(sub_w), max_x + margin)
                content = sub.crop((min_x, min_y, max_x, max_y))
            else:
                content = sub

            # Resize to standardized 160x160
            content = content.resize((160, 160), Image.Resampling.LANCZOS)
            base_filename = class_dir / f"orig_{sample_i:02d}.jpg"
            content.save(base_filename, quality=95)
            total_extracted += 1

            # Generate offline augmentations for training robustness
            cv_img = cv2.imread(str(base_filename))
            if cv_img is not None:
                # 1. Rotations (-12 deg, +12 deg)
                for ang_idx, angle in enumerate([-12, 12, -6, 6]):
                    M = cv2.getRotationMatrix2D((80, 80), angle, 1.0)
                    rotated = cv2.warpAffine(cv_img, M, (160, 160), borderMode=cv2.BORDER_REPLICATE)
                    cv2.imwrite(str(class_dir / f"aug_rot_{sample_i}_{ang_idx}.jpg"), rotated)
                    total_extracted += 1

                # 2. Lighting / contrast
                for b_idx, factor in enumerate([0.85, 1.15]):
                    bright = np.clip(cv_img.astype(np.float32) * factor, 0, 255).astype(np.uint8)
                    cv2.imwrite(str(class_dir / f"aug_bright_{sample_i}_{b_idx}.jpg"), bright)
                    total_extracted += 1

                # 3. Slight zoom / crop
                h_c, w_c = cv_img.shape[:2]
                crop_box = cv_img[8:h_c-8, 8:w_c-8]
                scaled = cv2.resize(crop_box, (160, 160), interpolation=cv2.INTER_LINEAR)
                cv2.imwrite(str(class_dir / f"aug_scale_{sample_i}.jpg"), scaled)
                total_extracted += 1

    # Save classes metadata
    meta_path = OUTPUT_DIR / "classes.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(NSL_36_CLASSES, f, indent=2, ensure_ascii=False)

    print(f"Extraction & Augmentation complete!")
    print(f"Total images generated: {total_extracted} across 36 Nepali Sign Language classes.")
    print(f"Classes dictionary saved to {meta_path}")


if __name__ == "__main__":
    extract_base_samples()
