"""
Trinetra Object Detection Engine & Perception Pipeline
Abstract detection contract, spatial sector partitioning, and decoupled inference worker.
"""

from abc import ABC, abstractmethod
import dataclasses
from dataclasses import dataclass
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from app.audio.speaker import SpeechManager, SpeechPriority
from app.camera.adapter import FramePacket
from app.detection.decision import SceneDecisionEngine
from app.detection.ego_motion import EgoMotionEstimate, SparseOpticalFlowEgoMotionEstimator
from app.detection.fusion import DetectionFusion
from app.detection.ground_hazard import GroundHazardDetector
from app.detection.nepal_hazards import NepalOverheadWireDetector
from app.detection.sign_interpreter import SignGestureInterpreter
from app.detection.scene import SceneAnalyzer
from app.detection.tracking import TemporalTracker
from app.detection.types import BoundingBox, Detection, DetectionResult, classify_sector
from app.localization import (
    DEFAULT_LANGUAGE,
    format_announcement,
    get_announcement_key,
    is_supported_language,
    normalize_language,
)

logger = logging.getLogger("trinetra.detection")


class DetectionEngine(ABC):
    """Abstract Base Class for local on-device computer vision models."""

    @abstractmethod
    def detect(self, jpeg_bytes: bytes, frame_id: int) -> DetectionResult:
        """Executes inference on a frame payload. Must NOT block camera capture."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Returns True if the engine is initialized and ready for inference."""
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Returns metadata about the active detection model."""
        pass


class UnavailableDetectionEngine(DetectionEngine):
    """
    Explicit fallback detection engine when model weights are missing or uninitialized.
    Refuses inference with an actionable error and prevents silent mock detection emission.
    """

    def __init__(
        self,
        error_message: str = "Detection model weights not found or runtime unavailable.",
        error_type: str = "ModelUnavailable",
        model_name: str = "Unavailable"
    ):
        self.error_message = error_message
        self.error_type = error_type
        self.model_name = model_name

    def detect(self, jpeg_bytes: bytes, frame_id: int) -> DetectionResult:
        raise RuntimeError(f"Detection engine unavailable: {self.error_message}")

    def is_ready(self) -> bool:
        return False

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "runtime": "unavailable",
            "supported_classes": [],
            "is_ready": False,
            "error": self.error_message,
            "error_type": self.error_type
        }


class FakeDetectionEngine(DetectionEngine):
    """
    Deterministic mock detection engine for automated regression testing.
    Produces predictable detections without downloading models or requiring GPUs.
    """

    def __init__(
        self,
        mock_detections: Optional[List[Detection]] = None,
        simulated_latency_ms: float = 15.0,
        should_fail: bool = False
    ):
        self.mock_detections = mock_detections if mock_detections is not None else [
            Detection(
                class_name="person",
                confidence=0.88,
                box=BoundingBox(x_min=0.40, y_min=0.20, x_max=0.60, y_max=0.80),
                sector="center"
            )
        ]
        self.simulated_latency_ms = simulated_latency_ms
        self.should_fail = should_fail
        self._lock = threading.Lock()

    def detect(self, jpeg_bytes: bytes, frame_id: int) -> DetectionResult:
        with self._lock:
            if self.should_fail:
                raise RuntimeError("Simulated inference engine failure.")

            now = time.time()
            return DetectionResult(
                frame_id=frame_id,
                timestamp=now,
                detections=list(self.mock_detections),
                inference_time_ms=self.simulated_latency_ms,
                model_name="FakeDetectionEngine-v1"
            )

    def is_ready(self) -> bool:
        return not self.should_fail

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "model_name": "FakeDetectionEngine-v1",
            "runtime": "mock",
            "supported_classes": ["person", "chair", "door", "table"],
            "is_ready": self.is_ready()
        }


class PerceptionPipeline:
    """
    Asynchronous perception loop that independently samples fresh camera frames,
    executes detection inference in the background, and dispatches prioritized speech alerts.
    Keeps camera capture and HTTP frame delivery completely responsive and decoupled from inference latency.
    """

    def __init__(
        self,
        engine: Optional[DetectionEngine] = None,
        speech_manager: Optional[SpeechManager] = None,
        target_fps: float = 10.0,
        language: str = DEFAULT_LANGUAGE,
        fusion: Optional[DetectionFusion] = None,
        health_controller: Optional[Any] = None
    ):
        self.engine = engine or UnavailableDetectionEngine(
            error_message="No detection engine configured.",
            error_type="EngineNotConfigured"
        )
        self.speech_manager = speech_manager
        self.fusion = fusion
        if health_controller is not None:
            self.health_controller = health_controller
        else:
            try:
                from app.camera.health_controller import SensorHealthController
                self.health_controller = SensorHealthController()
            except Exception:
                self.health_controller = None
        self.target_interval = 1.0 / target_fps if target_fps > 0 else 0.1
        self._language = normalize_language(language) if is_supported_language(language) else language.strip().lower()

        self._active = False
        self._lock = threading.Lock()
        self._latest_result: Optional[DetectionResult] = None
        self._worker_thread: Optional[threading.Thread] = None

        # Bounded O(1) capacity-1 pending frame slot
        self._pending_lock = threading.Lock()
        self._pending_packet: Optional[FramePacket] = None
        self._new_frame_event = threading.Event()
        self._last_processed_frame_id: int = -1
        self._last_processed_session_id: str = ""
        self._frames_processed_count: int = 0

        # Event-aware tracking and scene decision layers
        self.tracker = TemporalTracker()
        self.ego_motion_estimator = SparseOpticalFlowEgoMotionEstimator()
        self.scene_analyzer = SceneAnalyzer()
        self.ground_hazard_detector = GroundHazardDetector()
        self.wire_detector = NepalOverheadWireDetector()
        self.sign_interpreter = SignGestureInterpreter()
        self._last_sign_time: float = 0.0
        self.currency_service = None
        self._last_auto_currency_time: float = 0.0
        self.decision_engine = SceneDecisionEngine(
            speech_manager=self.speech_manager,
            language=self._language
        )

    @property
    def language(self) -> str:
        with self._lock:
            return self._language

    @language.setter
    def language(self, value: str) -> None:
        norm = normalize_language(value) if is_supported_language(value) else value.strip().lower()
        with self._lock:
            self._language = norm
            if hasattr(self, "decision_engine") and self.decision_engine:
                self.decision_engine.language = norm

    def start(self) -> None:
        """Starts the background perception worker thread deterministically."""
        with self._lock:
            if self._active:
                return
            self._active = True
            self._new_frame_event.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="PerceptionWorkerThread",
                daemon=True
            )
            self._worker_thread.start()
            logger.info("Perception pipeline background worker started.")

    def stop(self, timeout: float = 2.0) -> None:
        """
        Stops the background perception worker thread deterministically.
        Waits up to timeout seconds for ongoing inference to finish.
        """
        thread_to_join = None
        with self._lock:
            if not self._active:
                return
            self._active = False
            self._new_frame_event.set()
            thread_to_join = self._worker_thread
            self._worker_thread = None

        if thread_to_join and thread_to_join.is_alive():
            thread_to_join.join(timeout=timeout)

        self.reset_session()
        logger.info("Perception pipeline stopped.")

    def reset_session(self, new_session_id: Optional[str] = None, clear_latest: bool = False) -> None:
        """
        Resets frame sequence tracking and purges any pending in-flight frame
        from prior camera sessions to avoid processing stale cross-session frames.
        """
        with self._pending_lock:
            self._pending_packet = None
            self._new_frame_event.clear()
        with self._lock:
            self._last_processed_frame_id = -1
            self._last_processed_session_id = new_session_id or ""
            if clear_latest:
                self._latest_result = None
            if hasattr(self, "tracker") and self.tracker:
                self.tracker.reset()
            if hasattr(self, "ego_motion_estimator") and self.ego_motion_estimator:
                self.ego_motion_estimator.reset()
            if hasattr(self, "decision_engine") and self.decision_engine:
                self.decision_engine.reset()
            if hasattr(self, "health_controller") and self.health_controller:
                self.health_controller.reset()

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def submit_frame(self, packet: FramePacket) -> None:
        """
        Non-blocking ingestion of a fresh camera frame into the bounded capacity-1 buffer.
        Overwrites any unconsumed older frame and notifies the perception worker.
        Runs in O(1) time without blocking camera capture or HTTP frame delivery.
        """
        if not self.is_active():
            return

        with self._pending_lock:
            self._pending_packet = packet
            self._new_frame_event.set()

    def process_frame(self, packet: FramePacket) -> Optional[DetectionResult]:
        """
        Synchronous processing helper for deterministic offline testing.
        Production paths should prefer non-blocking submit_frame().
        """
        try:
            # 0. Pre-flight sensor health evaluation (controlled via disabled-by-default feature flag)
            state_action = None
            if hasattr(self, "health_controller") and self.health_controller and self.health_controller.is_enabled():
                try:
                    _, state_action = self.health_controller.evaluate_frame(
                        packet.jpeg_bytes,
                        frame_id=packet.frame_id,
                        timestamp=packet.captured_at
                    )
                except Exception as h_err:
                    logger.warning(f"SensorHealthController error: {h_err}")
                    state_action = None

            # Trace audio chime into speech manager for spoken health warnings
            if state_action is not None and getattr(state_action, "audio_chime", None):
                self._handle_sensor_health_alert(state_action)

            # 1. Suppress DNN inference during verified outages to prevent hallucinations & save compute
            if state_action is not None and not state_action.should_run_dnn:
                if getattr(state_action, "tracks_purged", False) or getattr(state_action.state, "value", "") == "STALE_TERMINATED":
                    if hasattr(self, "tracker") and self.tracker:
                        if hasattr(self.tracker, "tracks"):
                            self.tracker.tracks.clear()
                        else:
                            self.tracker.reset()
                elif getattr(state_action, "kalman_action", "") == "COAST_ONLY":
                    if hasattr(self, "tracker") and self.tracker and self.tracker.tracks:
                        for trk in self.tracker.tracks:
                            if getattr(trk.state, "value", "") != "deleted":
                                trk.predict(packet.captured_at)
                                trk.mark_missed(max_age=15)

                suppressed_result = DetectionResult(
                    frame_id=packet.frame_id,
                    timestamp=packet.captured_at if packet.captured_at > 0 else time.time(),
                    detections=[],
                    inference_time_ms=0.0,
                    model_name=getattr(self.engine, "model_name", "InferenceSuppressed")
                )
                with self._lock:
                    self._latest_result = suppressed_result
                    self._last_processed_frame_id = packet.frame_id
                    self._last_processed_session_id = packet.session_id
                    self._frames_processed_count += 1
                return suppressed_result

            result = self.engine.detect(packet.jpeg_bytes, packet.frame_id)
            if hasattr(self, "fusion") and self.fusion is not None and packet.jpeg_bytes:
                fused_dets = self.fusion.fuse(result.detections, frame_bytes=packet.jpeg_bytes)
                result = dataclasses.replace(result, detections=fused_dets)

            frame_bgr = None
            if packet.jpeg_bytes:
                try:
                    import cv2
                    import numpy as np
                    nparr = np.frombuffer(packet.jpeg_bytes, np.uint8)
                    frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception:
                    frame_bgr = None

            # Ground hazard & surface discontinuity check (potholes, open drains, curb drops)
            hazard_data = None
            if packet.jpeg_bytes and hasattr(self, "ground_hazard_detector") and self.ground_hazard_detector:
                try:
                    import cv2
                    import numpy as np
                    nparr = np.frombuffer(packet.jpeg_bytes, np.uint8)
                    frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame_bgr is not None:
                        hazard = self.ground_hazard_detector.analyze(frame_bgr)
                        if hazard.detected:
                            hazard_data = {
                                "detected": True,
                                "hazard_type": hazard.hazard_type,
                                "severity": hazard.severity,
                                "confidence": round(float(hazard.confidence), 2),
                                "message": hazard.message_ne if self.language.startswith("ne") else hazard.message_en,
                                "bounding_box": list(hazard.bounding_box) if hazard.bounding_box else None
                            }
                            if self.speech_manager:
                                self.speech_manager.announce(
                                    text=hazard.message_ne if self.language.startswith("ne") else hazard.message_en,
                                    priority=SpeechPriority.CRITICAL_HAZARD,
                                    message_key=f"ground_hazard:{hazard.hazard_type}",
                                    interrupt=True,
                                    cooldown=3.0,
                                    language="ne" if self.language.startswith("ne") else "en"
                                )
                except Exception as gh_err:
                    logger.debug(f"Ground hazard detection error: {gh_err}")

            if hazard_data:
                result = dataclasses.replace(result, ground_hazard=hazard_data)

            # Overhead dangling wire detection (upper 35% clearance zone)
            wire_data = None
            if packet.jpeg_bytes and hasattr(self, "wire_detector") and self.wire_detector:
                try:
                    if frame_bgr is not None:
                        wire_alert = self.wire_detector.analyze(frame_bgr)
                        if wire_alert.detected:
                            wire_data = {
                                "detected": True,
                                "hazard_class": wire_alert.hazard_class,
                                "severity": wire_alert.severity,
                                "confidence": round(float(wire_alert.confidence), 2),
                                "message": wire_alert.message_ne if self.language.startswith("ne") else wire_alert.message_en,
                                "bounding_box": list(wire_alert.bounding_box) if wire_alert.bounding_box else None
                            }
                            if self.speech_manager:
                                self.speech_manager.announce(
                                    text=wire_alert.message_ne if self.language.startswith("ne") else wire_alert.message_en,
                                    priority=SpeechPriority.CRITICAL_HAZARD,
                                    message_key=f"wire_hazard:{wire_alert.hazard_class}",
                                    interrupt=True,
                                    cooldown=3.0,
                                    language="ne" if self.language.startswith("ne") else "en"
                                )
                except Exception as w_err:
                    logger.debug(f"Overhead wire detection error: {w_err}")

            if wire_data:
                result = dataclasses.replace(result, overhead_wire=wire_data)

            # Semi-autonomous in-hand currency note recognition
            auto_currency_data = None
            now_sec = time.time()
            if (
                packet.jpeg_bytes
                and getattr(self, "currency_service", None) is not None
                and (now_sec - getattr(self, "_last_auto_currency_time", 0.0)) >= 1.0
            ):
                try:
                    curr_res = self.currency_service.identify(packet.jpeg_bytes)
                    if curr_res.get("status") == "identified":
                        self._last_auto_currency_time = now_sec
                        auto_currency_data = curr_res
                        spoken = curr_res.get("spoken_text") or curr_res.get("message")
                        if self.speech_manager:
                            self.speech_manager.announce(
                                text=spoken,
                                priority=SpeechPriority.SPATIAL_NAVIGATION,
                                message_key=f"auto_currency:{curr_res.get('denomination')}",
                                interrupt=True,
                                cooldown=4.0,
                                language="ne" if self.language.startswith("ne") else "en"
                            )
                except Exception as c_err:
                    logger.debug(f"Auto-currency check error: {c_err}")

            if auto_currency_data:
                result = dataclasses.replace(result, auto_currency=auto_currency_data)

            # Two-way sign language & hand gesture translation
            sign_data = None
            if packet.jpeg_bytes and getattr(self, "sign_interpreter", None) is not None and (now_sec - getattr(self, "_last_sign_time", 0.0)) >= 1.2:
                try:
                    import cv2
                    import numpy as np
                    nparr = np.frombuffer(packet.jpeg_bytes, np.uint8)
                    frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame_bgr is not None:
                        sign = self.sign_interpreter.analyze(frame_bgr)
                        if sign.detected:
                            self._last_sign_time = now_sec
                            sign_data = {
                                "detected": True,
                                "gesture_type": sign.gesture_type,
                                "confidence": round(float(sign.confidence), 2),
                                "message": sign.message_ne if self.language.startswith("ne") else sign.message_en,
                                "symbol": sign.symbol,
                                "bounding_box": list(sign.bounding_box) if sign.bounding_box else None
                            }
                            if self.speech_manager:
                                self.speech_manager.announce(
                                    text=sign.message_ne if self.language.startswith("ne") else sign.message_en,
                                    priority=SpeechPriority.SPATIAL_NAVIGATION,
                                    message_key=f"sign:{sign.gesture_type}",
                                    interrupt=True,
                                    cooldown=4.5,
                                    language="ne" if self.language.startswith("ne") else "en"
                                )
                except Exception as s_err:
                    logger.debug(f"Sign interpreter error: {s_err}")

            if sign_data:
                result = dataclasses.replace(result, sign_gesture=sign_data)

            e2e_ms = max(0.0, (time.time() - packet.captured_at) * 1000.0) if packet.captured_at > 0 else result.inference_time_ms
            result = dataclasses.replace(result, e2e_latency_ms=round(e2e_ms, 1))

            with self._lock:
                self._latest_result = result
                self._last_processed_frame_id = packet.frame_id
                self._last_processed_session_id = packet.session_id
                self._frames_processed_count += 1

            # Estimate camera ego-motion if frame bytes are present
            ego_motion = None
            if (
                hasattr(self, "ego_motion_estimator")
                and self.ego_motion_estimator is not None
                and packet.jpeg_bytes is not None
                and len(packet.jpeg_bytes) > 0
            ):
                boxes = [d.box for d in result.detections] if result.detections else None
                ego_motion = self.ego_motion_estimator.estimate(
                    packet.jpeg_bytes,
                    packet.captured_at,
                    detected_boxes=boxes
                )

            self._announce_detections(result, ego_motion=ego_motion)
            return result
        except Exception as exc:
            logger.warning(f"Detection processing failed: {exc}")
            return None

    def get_latest_result(self) -> Optional[DetectionResult]:
        with self._lock:
            return self._latest_result

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active": self._active,
                "frames_processed": self._frames_processed_count,
                "last_processed_frame_id": self._last_processed_frame_id,
                "last_processed_session_id": self._last_processed_session_id,
                "has_latest_result": self._latest_result is not None,
                "language": self._language
            }

    def _announce_detections(self, result: DetectionResult, ego_motion: Optional[Any] = None) -> None:
        if not self.speech_manager or not result.detections:
            return

        try:
            # 1. Temporal object tracking across consecutive frames with camera ego-motion compensation
            tracks = self.tracker.update(result.detections, result.timestamp, ego_motion=ego_motion)

            # 2. Scene awareness, crowd count, and walkable space analysis
            assessment = self.scene_analyzer.analyze_scene(tracks, result.frame_id, result.timestamp)

            # 3. Speech decision engine prioritizes and dispatches concise guidance
            self.decision_engine.language = self.language
            self.decision_engine.process_scene(assessment, current_time=result.timestamp)
        except Exception as exc:
            logger.warning(f"Failed to announce detection: {exc}")

    def _handle_sensor_health_alert(self, state_action: Any) -> None:
        """
        Traces state_action.audio_chime and dispatches rate-limited bilingual spoken warnings.
        """
        if state_action is None or not getattr(state_action, "audio_chime", None):
            return
        if not hasattr(self, "speech_manager") or not self.speech_manager:
            return

        chime = state_action.audio_chime
        active_lang = self.language

        messages = {
            "CHIME_UNAVAILABLE": {
                "ne": "चेतावनी: क्यामेरा दृश्य अवरुद्ध वा अँध्यारो छ।",
                "en": "Warning: camera view obstructed or dark.",
            },
            "CHIME_OUTAGE_EXPIRED": {
                "ne": "सेन्सर अनुपलब्ध: ट्र्याकिङ रोकियो।",
                "en": "Sensor unavailable: tracking stopped.",
            },
            "CHIME_RECOVERY": {
                "ne": "क्यामेरा दृश्य पुनः सुरु भयो।",
                "en": "Camera view restored.",
            },
        }

        entry = messages.get(chime)
        if not entry:
            return

        lang_code = "ne" if active_lang.startswith("ne") else "en"
        text = entry.get(lang_code, entry["en"])

        from app.audio.speaker import SpeechPriority
        if chime in ("CHIME_UNAVAILABLE", "CHIME_OUTAGE_EXPIRED"):
            priority = SpeechPriority.CRITICAL_HAZARD
            interrupt = True
        else:
            priority = SpeechPriority.SPATIAL_NAVIGATION
            interrupt = False

        self.speech_manager.announce(
            text=text,
            priority=priority,
            message_key=f"sensor_health:{chime}",
            interrupt=interrupt,
            cooldown=5.0,
            language=lang_code
        )

    def _worker_loop(self) -> None:
        """
        Dedicated background loop independently sampling the latest camera frame.
        Skips already-processed frames within the same session, while immediately
        transitioning to fresh frames from new camera session generations.
        """
        while self.is_active():
            self._new_frame_event.wait(timeout=self.target_interval)
            self._new_frame_event.clear()

            if not self.is_active():
                break

            packet: Optional[FramePacket] = None
            with self._pending_lock:
                cand = self._pending_packet
                if cand is not None:
                    is_new_session = (
                        cand.session_id != ""
                        and cand.session_id != self._last_processed_session_id
                    )
                    if is_new_session or cand.frame_id > self._last_processed_frame_id:
                        packet = cand

            if packet is None:
                continue

            try:
                self.process_frame(packet)
            except Exception as exc:
                logger.warning(f"Background perception worker error on frame {packet.frame_id}: {exc}")

