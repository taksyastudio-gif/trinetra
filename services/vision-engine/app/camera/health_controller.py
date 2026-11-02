"""
Trinetra Sensor-Health Controller & Perception State Orchestrator
Priority 4.4 Unified Sensor-Health Subsystem.

Responsible for:
- 3x3 Spatial grid image quality assessment.
- Boundary-induced Laplacian inflation suppression.
- Luminance-coupled low-texture vs occlusion disambiguation.
- Temporal debounce and hysteresis.
- Formal 5-state perception lifecycle (VALID_OBSERVATION, TEMPORARILY_DEGRADED,
  SENSOR_UNAVAILABLE, STALE_TERMINATED, RECOVERY_TRANSITION).
- Tracking uncertainty, elapsed time outage tracking, and adaptive coasting ceilings.
- Audio chime dispatching with strict 5.0-second cooldown rate-limiting.
- Disabled-by-default feature flag safety gate.
"""

from dataclasses import dataclass
from enum import Enum
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np

from app.camera.sensor_health import (
    ActionRecommendation,
    DegradationReason,
    HealthStatus,
    SensorHealthAssessment,
    SensorHealthGatekeeper,
    SensorHealthThresholds,
)

logger = logging.getLogger("trinetra.camera.health_controller")

# Feature flag environment variable (default: disabled)
ENV_ENABLE_SENSOR_HEALTH = "TRINETRA_ENABLE_SENSOR_HEALTH"


class PerceptionState(str, Enum):
    """The five formal perception lifecycle states."""
    VALID_OBSERVATION = "VALID_OBSERVATION"
    TEMPORARILY_DEGRADED = "TEMPORARILY_DEGRADED"
    SENSOR_UNAVAILABLE = "SENSOR_UNAVAILABLE"
    STALE_TERMINATED = "STALE_TERMINATED"
    RECOVERY_TRANSITION = "RECOVERY_TRANSITION"


@dataclass(frozen=True)
class StateActionPacket:
    """Action directives emitted by the SensorHealthController to downstream components."""
    state: PerceptionState
    should_run_dnn: bool
    kalman_action: str  # "MEASUREMENT_UPDATE", "CAUTIOUS_UPDATE", "COAST_ONLY", "PURGE_TRACKS", "INIT_FRESH"
    audio_chime: Optional[str]
    coasting_frames: int
    outage_duration_seconds: float
    tracks_purged: bool
    confidence_scale: float


class SensorHealthController:
    """
    Unified, single-point-of-truth controller for all perception health operations.
    Maintains spatial quality, temporal debounce, 5-state machine, and tracking safety limits.
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        thresholds: Optional[SensorHealthThresholds] = None,
        degrade_debounce_frames: int = 3,
        recovery_debounce_frames: int = 3,
        chime_cooldown_seconds: float = 5.0,
        max_coasting_duration_seconds: float = 0.20,  # 200 ms (approx 6 frames at 30 FPS)
        max_coasting_frames: int = 5
    ):
        if enabled is not None:
            self._enabled = enabled
        else:
            self._enabled = os.environ.get(ENV_ENABLE_SENSOR_HEALTH, "").lower() in ("1", "true", "yes")

        self.thresholds = thresholds or SensorHealthThresholds()
        self.degrade_debounce = degrade_debounce_frames
        self.recovery_debounce = recovery_debounce_frames
        self.chime_cooldown = chime_cooldown_seconds
        self.max_coasting_duration = max_coasting_duration_seconds
        self.max_coasting_frames = max_coasting_frames

        # State machine tracking
        self.state = PerceptionState.VALID_OBSERVATION
        self.consecutive_severely_degraded = 0
        self.consecutive_normal = 0
        self.coast_frames = 0
        self.outage_start_timestamp: Optional[float] = None
        self.last_chime_timestamp: float = -999.0
        self.last_clean_inference_timestamp: float = 0.0

        # Most recent diagnostic assessment
        self.latest_assessment: Optional[SensorHealthAssessment] = None

    def is_enabled(self) -> bool:
        """Returns True if the sensor health feature flag is active."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Dynamically enables or disables the controller for testing or feature gating."""
        self._enabled = enabled
        if not enabled:
            self.reset()

    def reset(self) -> None:
        """Resets all internal counters, state, and timers."""
        self.state = PerceptionState.VALID_OBSERVATION
        self.consecutive_severely_degraded = 0
        self.consecutive_normal = 0
        self.coast_frames = 0
        self.outage_start_timestamp = None
        self.latest_assessment = None

    def evaluate_frame(
        self,
        frame: Union[np.ndarray, bytes],
        frame_id: Optional[int] = None,
        timestamp: Optional[float] = None
    ) -> Tuple[SensorHealthAssessment, StateActionPacket]:
        """
        Executes pre-flight spatial quality check and computes StateActionPacket directives.
        If disabled, returns nominal pass-through without modifying perception execution.
        """
        now = timestamp if timestamp is not None else time.time()

        if not self._enabled:
            # Pass-through when disabled: 0% disruption, 100% backward compatible
            nominal_ass = SensorHealthAssessment(
                status=HealthStatus.NORMAL,
                blur_score=999.0,
                mean_luminance=128.0,
                contrast=50.0,
                is_blurry=False,
                is_dark=False,
                is_bright=False,
                is_occluded=False,
                reasons=(),
                action=ActionRecommendation.PROCESS,
                latency_ms=0.0,
                frame_id=frame_id,
                timestamp=now
            )
            pass_action = StateActionPacket(
                state=PerceptionState.VALID_OBSERVATION,
                should_run_dnn=True,
                kalman_action="MEASUREMENT_UPDATE",
                audio_chime=None,
                coasting_frames=0,
                outage_duration_seconds=0.0,
                tracks_purged=False,
                confidence_scale=1.0
            )
            self.latest_assessment = nominal_ass
            return nominal_ass, pass_action

        # Step 1: Spatial 3x3 Assessment & Boundary Inflation Rejection
        assessment = self._assess_spatial_quality(frame, frame_id, now)
        self.latest_assessment = assessment

        # Step 2: Temporal Hysteresis & 5-State Life Cycle Transition
        action_packet = self._transition_state(assessment, now)

        return assessment, action_packet

    def _assess_spatial_quality(
        self,
        frame: Union[np.ndarray, bytes],
        frame_id: Optional[int],
        timestamp: float
    ) -> SensorHealthAssessment:
        """Performs downsampled SIMD 3x3 spatial grid quality assessment."""
        t0 = time.perf_counter()

        # 1. Decode or normalize to single-channel 8-bit grayscale
        gray: Optional[np.ndarray] = None
        if isinstance(frame, bytes):
            if not frame:
                return self._create_empty_fallback(frame_id, timestamp, t0)
            buf = np.frombuffer(frame, dtype=np.uint8)
            gray = cv2.imdecode(buf, cv2.IMREAD_REDUCED_GRAYSCALE_2)
            if gray is None:
                return self._create_empty_fallback(frame_id, timestamp, t0)
        elif isinstance(frame, np.ndarray):
            if frame.size == 0:
                return self._create_empty_fallback(frame_id, timestamp, t0)
            if frame.ndim == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            elif frame.ndim == 2:
                gray = frame
            else:
                return self._create_empty_fallback(frame_id, timestamp, t0)
        else:
            return self._create_empty_fallback(frame_id, timestamp, t0)

        # 2. Resize to 320x240 for sub-millisecond execution
        h, w = gray.shape[:2]
        if w != 320 or h != 240:
            gray = cv2.resize(gray, (320, 240), interpolation=cv2.INTER_LINEAR)
            h, w = 240, 320

        # 3. Global Luminance & Contrast (single-pass SIMD)
        mean_mat, std_mat = cv2.meanStdDev(gray)
        global_lum = float(mean_mat[0][0])
        global_contrast = float(std_mat[0][0])

        # 4. Global 16-bit signed Laplacian
        laplacian = cv2.Laplacian(gray, cv2.CV_16S, ksize=3)
        global_blur = float(laplacian.var())

        # 5. Spatial 3x3 Grid Analysis (Nine 106x80 tiles)
        tile_h, tile_w = h // 3, w // 3
        occluded_tiles = 0
        dark_tiles = 0
        bright_tiles = 0
        max_tile_contrast = 0.0
        tile_blurs: List[float] = []

        for r in range(3):
            for c in range(3):
                t_gray = gray[r * tile_h:(r + 1) * tile_h, c * tile_w:(c + 1) * tile_w]
                tm_mat, ts_mat = cv2.meanStdDev(t_gray)
                t_mean = float(tm_mat[0][0])
                t_contrast = float(ts_mat[0][0])
                if t_contrast > max_tile_contrast:
                    max_tile_contrast = t_contrast

                t_lap = laplacian[r * tile_h:(r + 1) * tile_h, c * tile_w:(c + 1) * tile_w]
                t_blur = float(t_lap.var())
                tile_blurs.append(t_blur)

                is_occ = (t_contrast < 3.5 and t_mean < 30.0)
                if is_occ:
                    occluded_tiles += 1
                if t_mean < 15.0:
                    dark_tiles += 1
                if t_mean > 240.0:
                    bright_tiles += 1

        # 6. Boundary Inflation Rejection:
        # If >= 2 tiles are occluded and global blur > 2x median tile blur,
        # replace inflated global blur with median tile blur.
        median_tile_blur = float(np.median(tile_blurs)) if tile_blurs else global_blur
        boundary_inflation = (occluded_tiles >= 2 and global_blur > 2.0 * median_tile_blur)
        effective_blur = median_tile_blur if boundary_inflation else global_blur

        # 7. Diagnostic Checks
        reasons: List[DegradationReason] = []
        is_dark = False
        is_bright = False
        is_blurry = False
        is_occluded = False

        if global_lum < self.thresholds.luminance_too_dark or dark_tiles >= 6:
            is_dark = True
            reasons.append(DegradationReason.TOO_DARK)
        elif global_lum < self.thresholds.luminance_low_light:
            is_dark = True
            reasons.append(DegradationReason.LOW_LIGHT)
        elif global_lum > self.thresholds.luminance_too_bright or bright_tiles >= 6:
            is_bright = True
            reasons.append(DegradationReason.TOO_BRIGHT)

        # White-wall coupling: Well-lit surfaces (mean >= 50.0) with low contrast are LOW_TEXTURE, not OCCLUDED
        # Partial occlusion requires at least 2 dead tiles while other tiles observe a normal scene (max_contrast > 15)
        has_partial_occ = (occluded_tiles >= 2 and max_tile_contrast > 15.0)
        if global_contrast < self.thresholds.contrast_occlusion_threshold:
            if global_lum < 50.0:
                is_occluded = True
                reasons.append(DegradationReason.OCCLUDED_LENS)
            else:
                reasons.append(DegradationReason.LOW_TEXTURE)
        elif has_partial_occ:
            is_occluded = True
            reasons.append(DegradationReason.OCCLUDED_LENS)
        elif not is_dark and not is_bright:
            if global_contrast < self.thresholds.contrast_low_texture:
                reasons.append(DegradationReason.LOW_TEXTURE)
            else:
                if effective_blur < self.thresholds.blur_severe_threshold:
                    is_blurry = True
                    reasons.append(DegradationReason.DEFOCUS_BLUR)
                elif effective_blur < self.thresholds.blur_degraded_threshold:
                    is_blurry = True
                    reasons.append(DegradationReason.MOTION_BLUR)

        # 8. Action Synthesis
        if (
            DegradationReason.TOO_DARK in reasons
            or DegradationReason.TOO_BRIGHT in reasons
            or DegradationReason.OCCLUDED_LENS in reasons
            or DegradationReason.DEFOCUS_BLUR in reasons
        ):
            status = HealthStatus.SEVERELY_DEGRADED
            action = ActionRecommendation.SUPPRESS_AND_CHIME
        elif (
            DegradationReason.LOW_LIGHT in reasons
            or DegradationReason.MOTION_BLUR in reasons
            or DegradationReason.LOW_TEXTURE in reasons
        ):
            status = HealthStatus.DEGRADED
            action = ActionRecommendation.PROCESS_WITH_CAUTION
        else:
            status = HealthStatus.NORMAL
            action = ActionRecommendation.PROCESS

        t1 = time.perf_counter()
        exec_ms = (t1 - t0) * 1000.0

        return SensorHealthAssessment(
            status=status,
            blur_score=round(effective_blur, 2),
            mean_luminance=round(global_lum, 2),
            contrast=round(global_contrast, 2),
            is_blurry=is_blurry,
            is_dark=is_dark,
            is_bright=is_bright,
            is_occluded=is_occluded,
            reasons=tuple(reasons),
            action=action,
            latency_ms=round(exec_ms, 3),
            frame_id=frame_id,
            timestamp=timestamp
        )

    def _transition_state(
        self,
        assessment: SensorHealthAssessment,
        timestamp: float
    ) -> StateActionPacket:
        """Formal 5-state transition engine with debounce, elapsed time ceiling, and cooldown."""
        status = assessment.status
        audio_chime: Optional[str] = None
        tracks_purged = False

        if status == HealthStatus.SEVERELY_DEGRADED:
            self.consecutive_severely_degraded += 1
            self.consecutive_normal = 0
            if self.outage_start_timestamp is None:
                self.outage_start_timestamp = timestamp
        elif status == HealthStatus.NORMAL:
            self.consecutive_normal += 1
            self.consecutive_severely_degraded = 0
            self.outage_start_timestamp = None
        else:  # DEGRADED
            self.consecutive_normal = 0
            self.consecutive_severely_degraded = 0

        # Compute outage duration in seconds (elapsed time, not fixed frame counts alone)
        outage_duration = (
            (timestamp - self.outage_start_timestamp)
            if self.outage_start_timestamp is not None
            else 0.0
        )

        prev_state = self.state

        # State transition ladder
        if self.state == PerceptionState.VALID_OBSERVATION:
            if status == HealthStatus.DEGRADED:
                self.state = PerceptionState.TEMPORARILY_DEGRADED
            elif self.consecutive_severely_degraded >= self.degrade_debounce:
                self.state = PerceptionState.SENSOR_UNAVAILABLE
                self.coast_frames = 1
                audio_chime = self._get_rate_limited_chime("CHIME_UNAVAILABLE", timestamp)

        elif self.state == PerceptionState.TEMPORARILY_DEGRADED:
            if status == HealthStatus.NORMAL:
                self.state = PerceptionState.VALID_OBSERVATION
            elif self.consecutive_severely_degraded >= self.degrade_debounce:
                self.state = PerceptionState.SENSOR_UNAVAILABLE
                self.coast_frames = 1
                audio_chime = self._get_rate_limited_chime("CHIME_UNAVAILABLE", timestamp)

        elif self.state == PerceptionState.SENSOR_UNAVAILABLE:
            if self.consecutive_normal >= self.recovery_debounce:
                self.state = PerceptionState.RECOVERY_TRANSITION
                audio_chime = self._get_rate_limited_chime("CHIME_RECOVERY", timestamp, exempt_cooldown=True)
            else:
                self.coast_frames += 1
                # Enforce safety ceilings: either max frames OR max elapsed time
                if (
                    self.coast_frames > self.max_coasting_frames
                    or outage_duration > self.max_coasting_duration
                ):
                    self.state = PerceptionState.STALE_TERMINATED
                    tracks_purged = True
                    audio_chime = self._get_rate_limited_chime("CHIME_OUTAGE_EXPIRED", timestamp)

        elif self.state == PerceptionState.STALE_TERMINATED:
            # Cannot jump directly to VALID_OBSERVATION; must pass through RECOVERY_TRANSITION
            if self.consecutive_normal >= self.recovery_debounce:
                self.state = PerceptionState.RECOVERY_TRANSITION
                audio_chime = self._get_rate_limited_chime("CHIME_RECOVERY", timestamp, exempt_cooldown=True)

        elif self.state == PerceptionState.RECOVERY_TRANSITION:
            # Immediate handoff to VALID_OBSERVATION after fresh tracking verification
            self.state = PerceptionState.VALID_OBSERVATION
            self.coast_frames = 0
            self.consecutive_severely_degraded = 0
            self.outage_start_timestamp = None

        # Build output directives packet
        if self.state == PerceptionState.VALID_OBSERVATION:
            should_run_dnn = True
            kalman_action = "MEASUREMENT_UPDATE"
            confidence_scale = 1.0
            self.coast_frames = 0
        elif self.state == PerceptionState.TEMPORARILY_DEGRADED:
            should_run_dnn = True
            kalman_action = "CAUTIOUS_UPDATE"
            confidence_scale = 1.25  # elevate confidence requirement
        elif self.state == PerceptionState.SENSOR_UNAVAILABLE:
            should_run_dnn = False
            kalman_action = "COAST_ONLY"
            confidence_scale = 1.0
        elif self.state == PerceptionState.STALE_TERMINATED:
            should_run_dnn = False
            kalman_action = "PURGE_TRACKS"
            confidence_scale = 1.0
        elif self.state == PerceptionState.RECOVERY_TRANSITION:
            should_run_dnn = True
            kalman_action = "INIT_FRESH"
            confidence_scale = 1.0

        return StateActionPacket(
            state=self.state,
            should_run_dnn=should_run_dnn,
            kalman_action=kalman_action,
            audio_chime=audio_chime,
            coasting_frames=self.coast_frames,
            outage_duration_seconds=round(outage_duration, 3),
            tracks_purged=tracks_purged,
            confidence_scale=confidence_scale
        )

    def _get_rate_limited_chime(
        self,
        chime_name: str,
        timestamp: float,
        exempt_cooldown: bool = False
    ) -> Optional[str]:
        """Dispatches chime only if cooldown period has elapsed (or if exempt)."""
        if exempt_cooldown or (timestamp - self.last_chime_timestamp) >= self.chime_cooldown:
            self.last_chime_timestamp = timestamp
            return chime_name
        return None

    def _create_empty_fallback(
        self,
        frame_id: Optional[int],
        timestamp: float,
        t0: float
    ) -> SensorHealthAssessment:
        t1 = time.perf_counter()
        return SensorHealthAssessment(
            status=HealthStatus.SEVERELY_DEGRADED,
            blur_score=0.0,
            mean_luminance=0.0,
            contrast=0.0,
            is_blurry=True,
            is_dark=True,
            is_bright=False,
            is_occluded=True,
            reasons=(DegradationReason.TOO_DARK, DegradationReason.OCCLUDED_LENS),
            action=ActionRecommendation.SUPPRESS_AND_CHIME,
            latency_ms=round((t1 - t0) * 1000.0, 3),
            frame_id=frame_id,
            timestamp=timestamp
        )
