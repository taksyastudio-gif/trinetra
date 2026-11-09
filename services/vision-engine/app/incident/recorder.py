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
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import threading
import time
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
        self._active_prealert: Optional[Dict[str, Any]] = None
        self._lock = threading.RLock()
        self._device_secret = self._init_device_secret()

    def _init_device_secret(self) -> bytes:
        """Initializes or loads persistent 256-bit local device HMAC signing key."""
        key_dir = Path.home() / ".trinetra"
        key_file = key_dir / "device_hmac.key"
        if key_file.is_file():
            try:
                raw = key_file.read_bytes()
                if len(raw) >= 32:
                    return raw
            except Exception:
                pass
        try:
            key_dir.mkdir(parents=True, exist_ok=True)
            new_key = secrets.token_bytes(32)
            key_file.write_bytes(new_key)
            return new_key
        except Exception:
            return b"trinetra_device_fallback_signing_key_32bytes"

    def trigger_prealert(
        self,
        packet: FramePacket,
        detection_result: Optional[DetectionResult] = None,
        location_data: Optional[Dict[str, Any]] = None,
        notes: str = "Emergency Signal Triggered",
        countdown_seconds: int = 10,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiates the Caretaker Safety Protocol with a 10-second audible countdown.
        Allows the user to cancel if it was a false alarm.
        """
        with self._lock:
            if self._active_prealert and self._active_prealert.get("timer"):
                try:
                    self._active_prealert["timer"].cancel()
                except Exception:
                    pass

            now_epoch = time.time()
            prealert_id = f"pre_{int(now_epoch)}_{packet.frame_id}"
            active_lang = normalize_language(language) if language and is_supported_language(language) else self.default_language

            def _on_timeout():
                with self._lock:
                    if self._active_prealert and self._active_prealert.get("prealert_id") == prealert_id and not self._active_prealert.get("cancelled"):
                        logger.info(f"Pre-alert countdown expired for {prealert_id}. Confirming incident record.")
                        self.capture(
                            packet=packet,
                            detection_result=detection_result,
                            location_data=location_data,
                            notes=f"{notes} [CONFIRMED_AFTER_COUNTDOWN]",
                            language=active_lang
                        )
                        if self.speech_manager:
                            self.speech_manager.announce(
                                text="आपतकालीन घटना प्रमाणित भयो र सुरक्षित गरियो।" if active_lang == "ne" else "Emergency incident confirmed and saved.",
                                priority=SpeechPriority.CRITICAL_HAZARD,
                                interrupt=True,
                                cooldown=0.0,
                                language=active_lang
                            )
                        self._active_prealert = None

            timer = threading.Timer(float(countdown_seconds), _on_timeout)
            timer.daemon = True

            self._active_prealert = {
                "prealert_id": prealert_id,
                "packet": packet,
                "start_epoch": now_epoch,
                "duration": countdown_seconds,
                "timer": timer,
                "cancelled": False,
                "notes": notes,
                "language": active_lang
            }
            timer.start()

        # Audible prompt
        if self.speech_manager:
            prompt = (
                "चेतावनी: आपतकालीन सूचना १० सेकेन्डमा सुरक्षित हुनेछ। रद्द गर्न स्क्रिन छुनुहोस् वा 'म ठीक छु' भन्नुहोस्।"
                if active_lang == "ne"
                else "Warning: Emergency alert will activate in 10 seconds. Touch screen to cancel."
            )
            self.speech_manager.announce(
                text=prompt,
                priority=SpeechPriority.CRITICAL_HAZARD,
                interrupt=True,
                cooldown=0.0,
                language=active_lang
            )

        return {
            "status": "prealert_started",
            "prealert_id": prealert_id,
            "countdown_seconds": countdown_seconds,
            "disclaimer": "Local incident verification protocol; does not contact remote emergency services."
        }

    def cancel_prealert(self) -> Dict[str, Any]:
        """Cancels an active 10-second countdown."""
        with self._lock:
            if not self._active_prealert or self._active_prealert.get("cancelled"):
                return {"status": "none_active", "message": "No active countdown to cancel."}

            self._active_prealert["cancelled"] = True
            timer = self._active_prealert.get("timer")
            if timer:
                try:
                    timer.cancel()
                except Exception:
                    pass

            lang = self._active_prealert.get("language", self.default_language)
            self._active_prealert = None

        if self.speech_manager:
            self.speech_manager.announce(
                text="आपतकालीन सूचना रद्द गरियो।" if lang == "ne" else "Emergency alert cancelled.",
                priority=SpeechPriority.INFORMATIONAL,
                interrupt=True,
                cooldown=0.0,
                language=lang
            )

        return {"status": "cancelled", "message": "Emergency pre-alert cancelled successfully."}

    def get_prealert_status(self) -> Dict[str, Any]:
        """Returns the current state of any active countdown."""
        with self._lock:
            if not self._active_prealert or self._active_prealert.get("cancelled"):
                return {"active": False, "remaining_seconds": 0}

            elapsed = time.time() - self._active_prealert["start_epoch"]
            remaining = max(0.0, self._active_prealert["duration"] - elapsed)
            return {
                "active": remaining > 0,
                "prealert_id": self._active_prealert["prealert_id"],
                "remaining_seconds": round(remaining, 1),
                "notes": self._active_prealert["notes"]
            }

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

        # 4. Combined device HMAC-SHA-256 signature (image_sha256 + metadata_sha256)
        combined_payload = f"{image_sha256}:{metadata_sha256}".encode("utf-8")
        integrity_digest = hmac.new(self._device_secret, combined_payload, hashlib.sha256).hexdigest()

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
                        "notes": data.get("notes", ""),
                    })
                except Exception as exc:
                    logger.warning(f"Failed to parse incident metadata {json_file}: {exc}")
            return results

    def get_incident(self, incident_id: str) -> Optional[Tuple[IncidentRecord, bytes]]:
        """Retrieves record and raw image bytes by incident ID."""
        if not incident_id or not re.match(r"^inc_[a-zA-Z0-9_\-]+$", incident_id):
            logger.warning(f"Rejected invalid incident ID format: {incident_id}")
            return None
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
        if not incident_id or not re.match(r"^inc_[a-zA-Z0-9_\-]+$", incident_id):
            return {"incident_id": incident_id, "verified": False, "error": "Invalid incident ID format"}
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

                # Recalculate combined integrity digest using device HMAC key (with legacy fallback)
                expected_meta_sha = data.get("metadata_sha256")
                combined_payload = f"{actual_img_sha}:{expected_meta_sha}".encode("utf-8")
                actual_hmac = hmac.new(self._device_secret, combined_payload, hashlib.sha256).hexdigest()
                actual_legacy = hashlib.sha256(combined_payload).hexdigest()
                digest_matches = (expected_digest == actual_hmac) or (expected_digest == actual_legacy)

                is_valid = image_matches and digest_matches

                return {
                    "incident_id": safe_id,
                    "verified": is_valid,
                    "image_integrity": image_matches,
                    "digest_integrity": digest_matches,
                    "signing_method": "hmac_sha256" if expected_digest == actual_hmac else "legacy_sha256",
                    "image_sha256": actual_img_sha,
                    "expected_sha256": expected_img_sha,
                    "integrity_digest": actual_hmac if expected_digest == actual_hmac else actual_legacy,
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
