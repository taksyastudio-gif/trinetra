"""
Trinetra Accessible Incident Documentation & Tamper-Evident Snapshot Recorder.

Provides accessible, on-demand visual and telemetry capture with:
1. Cryptographic SHA-256 integrity digest across captured image and metadata.
2. Local-only bounded file storage with automated retention pruning.
3. Audible feedback through SpeechManager upon capture.
4. Strict safety boundaries: Standard generic object classification only;
   NO biometric person identification, NO face recognition, NO criminal inference.
5. Legal boundary note: Cryptographic hashes provide tamper-evidence of stored
   files but do NOT confer automatic legal admissibility in judicial systems.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional, Tuple

from app.audio.speaker import SpeechManager, SpeechPriority
from app.camera.adapter import FramePacket
from app.detection.types import DetectionResult
from app.localization import DEFAULT_LANGUAGE, is_supported_language, normalize_language

logger = logging.getLogger("trinetra.incident")

DEFAULT_INCIDENTS_DIR = Path(__file__).resolve().parent.parent.parent / "incidents"
LEGAL_DISCLAIMER_TEXT = (
    "Cryptographic SHA-256 hash verifies data integrity and tamper-evidence of stored files. "
    "It does not establish legal admissibility, chain of custody, or criminal liability. "
    "Standard generic object classes only; no facial recognition, person identification, "
    "or criminal characterization is performed."
)


@dataclass
class IncidentRecord:
    incident_id: str
    timestamp_utc: str
    timestamp_epoch: float
    frame_id: int
    session_id: str
    camera_source: str
    image_filename: str
    metadata_filename: str
    image_sha256: str
    metadata_sha256: str
    integrity_digest: str
    detections: List[Dict[str, Any]] = field(default_factory=list)
    location: Optional[Dict[str, Any]] = None
    notes: str = ""
    legal_disclaimer: str = LEGAL_DISCLAIMER_TEXT

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class IncidentRecorder:
    """
    Thread-safe manager for recording, storing, listing, and verifying incident snapshots.
    Enforces local-only storage, bounded disk retention, and tamper verification.
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        max_records: int = 50,
        speech_manager: Optional[SpeechManager] = None
    ):
        env_dir = os.environ.get("TRINETRA_INCIDENTS_DIR")
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir)
        elif env_dir:
            self.storage_dir = Path(env_dir)
        else:
            self.storage_dir = DEFAULT_INCIDENTS_DIR

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_records = max(5, max_records)
        self.speech_manager = speech_manager
        self.default_language: str = DEFAULT_LANGUAGE
        self._lock = threading.RLock()

    def set_default_language(self, lang: str) -> None:
        with self._lock:
            self.default_language = normalize_language(lang) if is_supported_language(lang) else lang.strip().lower()

    def capture(
        self,
        packet: FramePacket,
        detection_result: Optional[DetectionResult] = None,
        location_data: Optional[Dict[str, Any]] = None,
        notes: str = "",
        language: Optional[str] = None
    ) -> IncidentRecord:
        """
        Captures an incident snapshot from the current frame packet and telemetry.
        Computes SHA-256 hashes, writes JPEG + JSON to disk, and triggers audible feedback.
        """
        now = datetime.now(timezone.utc)
        timestamp_utc = now.isoformat()
        timestamp_epoch = now.timestamp()
        incident_id = f"inc_{now.strftime('%Y%m%d_%H%M%S')}_{packet.frame_id:06d}"

        # 1. Compute image SHA-256
        image_sha256 = hashlib.sha256(packet.jpeg_bytes).hexdigest()

        # 2. Extract generic object detection metadata
        detections_payload = []
        if detection_result and detection_result.detections:
            for det in detection_result.detections:
                detections_payload.append({
                    "class_name": det.class_name,
                    "confidence": round(float(det.confidence), 3),
                    "sector": det.sector,
                    "box": {
                        "x_min": round(float(det.box.x_min), 3),
                        "y_min": round(float(det.box.y_min), 3),
                        "x_max": round(float(det.box.x_max), 3),
                        "y_max": round(float(det.box.y_max), 3),
                    }
                })

        image_filename = f"{incident_id}.jpg"
        metadata_filename = f"{incident_id}.json"

        # 3. Canonical metadata payload before hashing
        meta_preliminary = {
            "incident_id": incident_id,
            "timestamp_utc": timestamp_utc,
            "timestamp_epoch": timestamp_epoch,
            "frame_id": packet.frame_id,
            "session_id": packet.session_id,
            "camera_source": packet.source_id,
            "image_filename": image_filename,
            "metadata_filename": metadata_filename,
            "image_sha256": image_sha256,
            "detections": detections_payload,
            "location": location_data,
            "notes": notes,
            "legal_disclaimer": LEGAL_DISCLAIMER_TEXT,
        }
        meta_json_bytes = json.dumps(meta_preliminary, sort_keys=True, indent=2).encode("utf-8")
        metadata_sha256 = hashlib.sha256(meta_json_bytes).hexdigest()

        # 4. Combined integrity digest (image_sha256 + metadata_sha256)
        combined_payload = f"{image_sha256}:{metadata_sha256}".encode("utf-8")
        integrity_digest = hashlib.sha256(combined_payload).hexdigest()

        record = IncidentRecord(
            incident_id=incident_id,
            timestamp_utc=timestamp_utc,
            timestamp_epoch=timestamp_epoch,
            frame_id=packet.frame_id,
            session_id=packet.session_id,
            camera_source=packet.source_id,
            image_filename=image_filename,
            metadata_filename=metadata_filename,
            image_sha256=image_sha256,
            metadata_sha256=metadata_sha256,
            integrity_digest=integrity_digest,
            detections=detections_payload,
            location=location_data,
            notes=notes,
            legal_disclaimer=LEGAL_DISCLAIMER_TEXT,
        )

        with self._lock:
            # Write image JPEG
            img_path = self.storage_dir / image_filename
            img_path.write_bytes(packet.jpeg_bytes)

            # Write full metadata JSON
            json_path = self.storage_dir / metadata_filename
            json_path.write_text(
                json.dumps(record.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

            # Enforce retention policy
            self._prune_excess_records()

        logger.info(f"Recorded incident {incident_id} (digest: {integrity_digest[:12]}...)")

        # 5. Audible feedback
        active_lang = normalize_language(language) if language and is_supported_language(language) else (language or self.default_language)
        self._dispatch_audible_feedback(active_lang)

        return record

    def list_incidents(self) -> List[Dict[str, Any]]:
        """Lists metadata summaries for all recorded incidents, sorted newest first."""
        with self._lock:
            results = []
            for json_file in sorted(self.storage_dir.glob("inc_*.json"), reverse=True):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    results.append({
                        "incident_id": data.get("incident_id"),
                        "timestamp_utc": data.get("timestamp_utc"),
                        "frame_id": data.get("frame_id"),
                        "image_filename": data.get("image_filename"),
                        "integrity_digest": data.get("integrity_digest"),
                        "detections_count": len(data.get("detections", [])),
                        "has_location": data.get("location") is not None,
                    })
                except Exception as exc:
                    logger.warning(f"Failed to parse incident metadata {json_file}: {exc}")
            return results

    def get_incident(self, incident_id: str) -> Optional[Tuple[IncidentRecord, bytes]]:
        """Retrieves record and raw image bytes by incident ID."""
        safe_id = Path(incident_id).name
        with self._lock:
            json_path = self.storage_dir / f"{safe_id}.json"
            img_path = self.storage_dir / f"{safe_id}.jpg"

            if not json_path.is_file() or not img_path.is_file():
                return None

            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                record = IncidentRecord(**data)
                img_bytes = img_path.read_bytes()
                return record, img_bytes
            except Exception as exc:
                logger.error(f"Error loading incident {safe_id}: {exc}")
                return None

    def verify_integrity(self, incident_id: str) -> Dict[str, Any]:
        """
        Cryptographically verifies whether on-disk JPEG and metadata files match
        their original SHA-256 digests.
        """
        safe_id = Path(incident_id).name
        with self._lock:
            json_path = self.storage_dir / f"{safe_id}.json"
            img_path = self.storage_dir / f"{safe_id}.jpg"

            if not json_path.is_file():
                return {"incident_id": safe_id, "verified": False, "error": "Metadata file not found"}
            if not img_path.is_file():
                return {"incident_id": safe_id, "verified": False, "error": "Image file not found"}

            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                expected_img_sha = data.get("image_sha256")
                expected_digest = data.get("integrity_digest")

                # Recalculate image hash
                actual_img_sha = hashlib.sha256(img_path.read_bytes()).hexdigest()
                image_matches = (actual_img_sha == expected_img_sha)

                # Recalculate combined integrity digest
                expected_meta_sha = data.get("metadata_sha256")
                actual_combined = hashlib.sha256(f"{actual_img_sha}:{expected_meta_sha}".encode("utf-8")).hexdigest()
                digest_matches = (actual_combined == expected_digest)

                is_valid = image_matches and digest_matches

                return {
                    "incident_id": safe_id,
                    "verified": is_valid,
                    "image_integrity": image_matches,
                    "digest_integrity": digest_matches,
                    "image_sha256": actual_img_sha,
                    "expected_sha256": expected_img_sha,
                    "integrity_digest": actual_combined,
                    "legal_disclaimer": LEGAL_DISCLAIMER_TEXT
                }
            except Exception as exc:
                return {"incident_id": safe_id, "verified": False, "error": str(exc)}

    def _prune_excess_records(self) -> None:
        """Removes oldest incident files when total count exceeds max_records."""
        json_files = sorted(self.storage_dir.glob("inc_*.json"), key=lambda p: p.stat().st_mtime)
        if len(json_files) > self.max_records:
            excess = len(json_files) - self.max_records
            for oldest_json in json_files[:excess]:
                try:
                    img_file = oldest_json.with_suffix(".jpg")
                    if img_file.is_file():
                        img_file.unlink()
                    oldest_json.unlink()
                    logger.info(f"Pruned expired incident record: {oldest_json.stem}")
                except Exception as exc:
                    logger.warning(f"Failed to prune incident {oldest_json.stem}: {exc}")

    def _dispatch_audible_feedback(self, language: str) -> None:
        """Dispatches an accessible confirmation chime or localized announcement."""
        if not self.speech_manager:
            return

        lang = normalize_language(language) if is_supported_language(language) else language.strip().lower()
        if lang == "ne":
            text = "घटना अभिलेख गरियो।"
        else:
            text = "Incident snapshot recorded."

        self.speech_manager.announce(
            text=text,
            priority=SpeechPriority.INFORMATIONAL,
            message_key="incident:captured",
            interrupt=True,
            cooldown=1.0,
            language=lang
        )
