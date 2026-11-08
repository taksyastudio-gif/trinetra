"""
Trinetra Web Image Harvester
Fetches real, high-quality training images from Wikimedia Commons API
for training the 100% in-house Trinetra neural vision classifier.
"""

import hashlib
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from PIL import Image

ROOT_DIR = Path(r"D:\trinetra")
DATASET_DIR = ROOT_DIR / "datasets" / "native_train"

SEARCH_TERMS = {
    "person": [
        "person portrait indoor",
        "human face portrait",
        "standing person portrait",
        "nepali people portrait",
    ],
    "sign_namaste": [
        "namaste gesture",
        "anjali mudra",
        "open palm hand",
        "waving hand",
    ],
    "sign_thumbs_up": [
        "thumbs up gesture",
        "thumb up hand",
        "approval thumb gesture",
    ],
    "sign_fist": [
        "clenched fist",
        "raised fist gesture",
        "closed fist hand",
    ],
    "hazard_pothole": [
        "pothole road damage",
        "asphalt pothole street",
        "road pit hole",
    ],
    "safe_ground": [
        "wood floor indoor",
        "carpet flooring living room",
        "tile floor clean",
        "blanket carpet bedroom floor",
    ],
    "stairs": [
        "staircase steps indoor",
        "wooden stairs home",
        "concrete stairway steps",
    ],
    "vehicle": [
        "car road traffic front",
        "motorcycle vehicle street",
        "bus vehicle city road",
    ],
    "chair": [
        "chair furniture living room",
        "wooden chair office",
        "armchair indoor furniture",
    ],
    "door": [
        "indoor wooden door entrance",
        "closed room door interior",
        "doorway frame indoor",
    ],
}

HEADERS = {
    "User-Agent": "TrinetraAssistiveBot/2.0 (https://trinetra.org; assistive-ai@trinetra.org) Python-urllib"
}


def search_wikimedia_images(query: str, limit: int = 15) -> list[str]:
    """Queries Wikimedia Commons API for direct image URLs."""
    urls = []
    try:
        encoded_q = urllib.parse.quote(query)
        api_url = (
            f"https://commons.wikimedia.org/w/api.php?action=query"
            f"&generator=search&gsrsearch={encoded_q}&gsrnamespace=6"
            f"&gsrlimit={limit}&prop=imageinfo&iiprop=url&iiurlwidth=400&format=json"
        )
        req = urllib.request.Request(api_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))

        pages = data.get("query", {}).get("pages", {})
        for _, page_data in pages.items():
            img_infos = page_data.get("imageinfo", [])
            for info in img_infos:
                # Prefer thumburl (400px wide, fast download) or direct url
                url = info.get("thumburl") or info.get("url")
                if url:
                    clean_path = url.split("?")[0].lower()
                    if clean_path.endswith((".jpg", ".jpeg", ".png", ".webp")):
                        urls.append(url)
    except Exception as e:
        print(f"  [Error] Wikimedia search failed for '{query}': {e}")

    return urls


def download_and_preprocess(url: str, save_path: Path) -> bool:
    """Downloads image, decodes, resizes to 128x128 standard format, and saves as JPEG."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_data = resp.read()

        img = Image.open(io.BytesIO(raw_data))
        img = img.convert("RGB")
        img = img.resize((128, 128), Image.Resampling.BILINEAR)
        img.save(save_path, "JPEG", quality=90)
        return True
    except Exception:
        return False


def harvest_dataset(target_per_class: int = 20):
    print("=" * 65)
    print("  TRINETRA ONLINE DATASET HARVESTER: Real Web Images")
    print("=" * 65)

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}

    for category, queries in SEARCH_TERMS.items():
        cat_dir = DATASET_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[Category: {category}]")

        downloaded = 0
        seen_urls = set()

        for q in queries:
            if downloaded >= target_per_class:
                break
            print(f"  Searching web for: '{q}'...")
            urls = search_wikimedia_images(q, limit=12)

            for u in urls:
                if u in seen_urls:
                    continue
                seen_urls.add(u)

                url_hash = hashlib.md5(u.encode()).hexdigest()[:8]
                filename = f"{category}_{downloaded + 1:03d}_{url_hash}.jpg"
                out_file = cat_dir / filename

                if download_and_preprocess(u, out_file):
                    downloaded += 1
                    print(f"    [OK] Downloaded [{downloaded}/{target_per_class}]: {filename}")

                if downloaded >= target_per_class:
                    break

        summary[category] = downloaded
        print(f"  Finished {category}: {downloaded} real images.")

    print("\n" + "=" * 65)
    print("  HARVEST COMPLETE:")
    for cat, n in summary.items():
        print(f"    - {cat:20s}: {n} images")
    print("=" * 65)


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    harvest_dataset(target_per_class=count)
