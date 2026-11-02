#!/usr/bin/env python3
"""
Trinetra Model Setup Utility
Downloads, verifies, and installs the verified YOLOX-Nano ONNX model.

Provenance:
  Official Megvii YOLOX upstream release v0.1.1rc0
  URL: https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx
  Pinned SHA-256: c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d

Security and Reliability:
  - Cryptographic SHA-256 integrity verification against pinned digest
  - Atomic write via temporary file (.tmp) preventing corrupted or partial files
  - Idempotent: Skips download if valid model already exists
  - Offline/air-gapped support via --local-file import
  - Zero external third-party dependencies (pure standard library)
"""

import argparse
import hashlib
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("setup_models")

DEFAULT_MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx"
PINNED_SHA256 = "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"
DEFAULT_FILENAME = "yolox_nano.onnx"

# Comprehensive registry of verified models used by Trinetra
MODEL_REGISTRY = {
    "yolox_nano": {
        "url": DEFAULT_MODEL_URL,
        "sha256": PINNED_SHA256,
        "filename": "yolox_nano.onnx",
        "subdir": "models",
        "description": "YOLOX-Nano Object Detector (Megvii, Apache 2.0)",
    },
    "yunet": {
        "url": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "filename": "face_detection_yunet_2023mar.onnx",
        "subdir": "models",
        "description": "YuNet Face Detector (OpenCV Zoo, Apache 2.0 / BSD-3)",
    },
    "piper_nepali": {
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ne/ne_NP/google/x_low/ne_NP-google-x_low.onnx",
        "sha256": "283431c1f89be9b13a40f885da818b23ac13f6ca536e2a0a414c970d3b13f0f2",
        "filename": "ne_NP-google-x_low.onnx",
        "subdir": "models/tts",
        "description": "Piper Neural TTS Nepali Voice (ne_NP-google-x_low, OpenSLR / CC-BY-SA-4.0)",
    },
}



def compute_sha256(file_path: Path) -> str:
    """Computes the SHA-256 hexadecimal digest of a local file in 64KB chunks."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def verify_file_hash(file_path: Path, expected_sha: str = PINNED_SHA256) -> bool:
    """Verifies that the file exists and matches the expected SHA-256 digest."""
    if not file_path.is_file():
        return False
    actual_sha = compute_sha256(file_path)
    return actual_sha == expected_sha.strip().lower()


def download_model(
    url: str = DEFAULT_MODEL_URL,
    dest_path: Optional[Path] = None,
    expected_sha: str = PINNED_SHA256,
    force: bool = False,
    timeout: int = 60
) -> bool:
    """
    Downloads model weights from url, verifies SHA-256, and atomically installs to dest_path.
    If valid file exists and force is False, returns True without re-downloading.
    """
    if dest_path is None:
        dest_path = Path(__file__).resolve().parent.parent / "models" / DEFAULT_FILENAME

    dest_path = dest_path.resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if dest_path.is_file() and not force:
        if verify_file_hash(dest_path, expected_sha):
            logger.info(f"Verified model already present at: {dest_path}")
            return True
        else:
            logger.warning(f"Existing file at {dest_path} failed integrity check. Re-downloading...")

    # Write to a temporary file in the same directory to guarantee atomic rename on the same filesystem
    tmp_file = dest_path.with_suffix(dest_path.suffix + f".tmp.{os.getpid()}")
    if tmp_file.exists():
        try:
            tmp_file.unlink()
        except OSError:
            pass

    logger.info(f"Downloading model from: {url}")
    logger.info(f"Target destination: {dest_path}")
    logger.info(f"Expected SHA-256: {expected_sha}")

    hasher = hashlib.sha256()
    bytes_downloaded = 0

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Trinetra-ModelSetup/1.0 (Windows; Python urllib)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            with open(tmp_file, "wb") as out_f:
                while chunk := response.read(65536):
                    hasher.update(chunk)
                    out_f.write(chunk)
                    bytes_downloaded += len(chunk)

        actual_sha = hasher.hexdigest().lower()
        logger.info(f"Downloaded {bytes_downloaded:,} bytes. Verifying SHA-256...")

        if actual_sha != expected_sha.strip().lower():
            logger.error(
                f"Cryptographic hash mismatch!\n"
                f"  Expected: {expected_sha.lower()}\n"
                f"  Actual:   {actual_sha}\n"
                f"Aborting installation. Temporary file deleted."
            )
            if tmp_file.exists():
                tmp_file.unlink()
            return False

        # Atomic replacement
        os.replace(tmp_file, dest_path)
        logger.info(f"Model successfully verified and installed to: {dest_path}")
        return True

    except Exception as exc:
        logger.error(f"Download or verification failed: {exc}")
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError:
                pass
        return False


def import_local_model(
    src_path: Path,
    dest_path: Optional[Path] = None,
    expected_sha: str = PINNED_SHA256,
    force: bool = False
) -> bool:
    """
    Imports and verifies an existing local model file into the destination path.
    Enables air-gapped / offline setup without internet access.
    """
    if dest_path is None:
        dest_path = Path(__file__).resolve().parent.parent / "models" / DEFAULT_FILENAME

    src_path = src_path.resolve()
    dest_path = dest_path.resolve()

    if not src_path.is_file():
        logger.error(f"Source file does not exist: {src_path}")
        return False

    logger.info(f"Verifying source file integrity: {src_path}")
    actual_sha = compute_sha256(src_path)
    if actual_sha != expected_sha.strip().lower():
        logger.error(
            f"Source file hash mismatch!\n"
            f"  Expected: {expected_sha.lower()}\n"
            f"  Actual:   {actual_sha}"
        )
        return False

    if dest_path.is_file() and not force:
        if verify_file_hash(dest_path, expected_sha):
            logger.info(f"Verified model already present at destination: {dest_path}")
            return True

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = dest_path.with_suffix(dest_path.suffix + f".tmp.{os.getpid()}")

    try:
        shutil.copyfile(src_path, tmp_file)
        # Verify the copied temporary file
        if compute_sha256(tmp_file) != expected_sha.strip().lower():
            raise IOError("Integrity check failed on copied temporary file.")
        os.replace(tmp_file, dest_path)
        logger.info(f"Successfully imported and verified model to: {dest_path}")
        return True
    except Exception as exc:
        logger.error(f"Local file import failed: {exc}")
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError:
                pass
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trinetra Vision Engine — Verified Model Setup Utility",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Target model destination path (defaults to services/vision-engine/models/yolox_nano.onnx)"
    )
    parser.add_argument(
        "--local-file",
        type=Path,
        default=None,
        help="Path to an existing local ONNX model file to import and verify (for offline environments)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download or re-copy even if destination file already exists and is valid"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only verify presence and cryptographic integrity of existing destination model"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_MODEL_URL,
        help="Custom URL to download model weights from"
    )
    parser.add_argument(
        "--expected-sha",
        type=str,
        default=PINNED_SHA256,
        help="Expected SHA-256 digest"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Verify and download all registered models (YOLOX-Nano, YuNet, Piper Nepali)"
    )

    args = parser.parse_args()

    # Multi-model batch mode
    if args.all:
        base_dir = Path(__file__).resolve().parent.parent
        all_ok = True
        logger.info("Processing all registered Trinetra models...")
        for name, meta in MODEL_REGISTRY.items():
            dest = base_dir / meta["subdir"] / meta["filename"]
            logger.info(f"--- Model: {name} ({meta['description']}) ---")
            if args.check_only:
                if not dest.is_file():
                    logger.error(f"Missing: {dest}")
                    all_ok = False
                elif compute_sha256(dest) != meta["sha256"]:
                    logger.error(f"SHA-256 mismatch for {name} at {dest}")
                    all_ok = False
                else:
                    logger.info(f"Verified {name} (SHA-256 match).")
            else:
                ok = download_model(
                    url=meta["url"],
                    dest_path=dest,
                    expected_sha=meta["sha256"],
                    force=args.force
                )
                if not ok:
                    all_ok = False
        return 0 if all_ok else 1

    target_path = args.dest
    if target_path is None:
        target_path = Path(__file__).resolve().parent.parent / "models" / DEFAULT_FILENAME
    target_path = target_path.resolve()

    if args.check_only:
        logger.info(f"Checking model integrity at: {target_path}")
        if not target_path.is_file():
            logger.error(f"Model file not found at: {target_path}")
            return 1
        actual_sha = compute_sha256(target_path)
        if actual_sha == args.expected_sha.strip().lower():
            logger.info("Model integrity verified (SHA-256 match).")
            return 0
        else:
            logger.error(
                f"Model integrity failure!\n"
                f"  Expected: {args.expected_sha.lower()}\n"
                f"  Actual:   {actual_sha}"
            )
            return 1

    if args.local_file:
        success = import_local_model(
            src_path=args.local_file,
            dest_path=target_path,
            expected_sha=args.expected_sha,
            force=args.force
        )
    else:
        success = download_model(
            url=args.url,
            dest_path=target_path,
            expected_sha=args.expected_sha,
            force=args.force
        )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
