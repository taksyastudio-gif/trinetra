"""
Capability Negotiator and Profile Resolver for TRINETRA v2.
Gracefully adapts perception pipelines to device and power realities.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from trinetra_core.capabilities.device import DeviceCapabilities, DeviceTier
from trinetra_core.types import DeviceType


@dataclass
class NegotiatedProfile:
    """
    Resolved operational profile dictating pipeline frequency and feature flags.
    """
    active_tier: DeviceTier
    target_vision_fps: int
    enable_optical_flow: bool
    enable_ground_hazard: bool
    enable_continuous_ocr: bool
    enable_neural_tts: bool
    audio_synthesis_mode: str          # "neural", "template", "chime_only"
    max_onnx_threads: int
    frame_skip_ratio: int              # Process 1 frame every N frames
    degraded_features: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_tier": self.active_tier.value,
            "target_vision_fps": self.target_vision_fps,
            "enable_optical_flow": self.enable_optical_flow,
            "enable_ground_hazard": self.enable_ground_hazard,
            "enable_continuous_ocr": self.enable_continuous_ocr,
            "enable_neural_tts": self.enable_neural_tts,
            "audio_synthesis_mode": self.audio_synthesis_mode,
            "max_onnx_threads": self.max_onnx_threads,
            "frame_skip_ratio": self.frame_skip_ratio,
            "degraded_features": self.degraded_features,
        }


class CapabilityNegotiator:
    """
    Resolves optimal execution profile based on device constraints.
    """

    @staticmethod
    def negotiate(capabilities: DeviceCapabilities, force_tier: Optional[DeviceTier] = None) -> NegotiatedProfile:
        degraded: List[str] = []

        if force_tier is not None:
            target_tier = force_tier
            degraded.append("manual_forced_override")
        else:
            target_tier = capabilities.declared_tier

            # Dynamic downgrade triggers
            # 1. Thermal throttling active -> immediately force LITE
            if capabilities.thermal_throttling_active:
                target_tier = DeviceTier.LITE
                degraded.append("thermal_throttling_active")

            # 2. Critical battery (<15%) -> downgrade to LITE
            if capabilities.is_battery_powered and capabilities.battery_level_pct is not None:
                if capabilities.battery_level_pct <= 15.0:
                    target_tier = DeviceTier.LITE
                    degraded.append("critical_battery_power_save")
                elif capabilities.battery_level_pct <= 30.0 and target_tier == DeviceTier.FULL:
                    target_tier = DeviceTier.STANDARD
                    degraded.append("low_battery_power_save")

            # 3. RAM constraint (< 2048 MB)
            if capabilities.ram_mb < 2048 and target_tier != DeviceTier.LITE:
                target_tier = DeviceTier.LITE
                degraded.append("low_ram_constraint")

            # 4. Wearable ESP32-CAM device type defaults to LITE / STANDARD
            if capabilities.device_type == DeviceType.ESP32_CAM_WEARABLE and target_tier == DeviceTier.FULL:
                target_tier = DeviceTier.STANDARD
                degraded.append("wearable_bandwidth_constraint")

        # Build Profile based on resolved tier
        if target_tier == DeviceTier.LITE:
            return NegotiatedProfile(
                active_tier=DeviceTier.LITE,
                target_vision_fps=min(5, capabilities.camera_native_fps),
                enable_optical_flow=False,
                enable_ground_hazard=True,  # Never disable safety-critical hazard detection
                enable_continuous_ocr=False,
                enable_neural_tts=capabilities.supports_neural_tts and capabilities.ram_mb >= 1500,
                audio_synthesis_mode="template" if capabilities.supports_neural_tts else "chime_only",
                max_onnx_threads=1,
                frame_skip_ratio=max(1, capabilities.camera_native_fps // 5),
                degraded_features=degraded,
            )
        elif target_tier == DeviceTier.STANDARD:
            return NegotiatedProfile(
                active_tier=DeviceTier.STANDARD,
                target_vision_fps=min(15, capabilities.camera_native_fps),
                enable_optical_flow=False,
                enable_ground_hazard=True,
                enable_continuous_ocr=False,
                enable_neural_tts=capabilities.supports_neural_tts,
                audio_synthesis_mode="neural" if capabilities.supports_neural_tts else "template",
                max_onnx_threads=min(2, max(1, capabilities.cpu_cores // 2)),
                frame_skip_ratio=max(1, capabilities.camera_native_fps // 15),
                degraded_features=degraded,
            )
        else:  # DeviceTier.FULL
            return NegotiatedProfile(
                active_tier=DeviceTier.FULL,
                target_vision_fps=min(30, capabilities.camera_native_fps),
                enable_optical_flow=True,
                enable_ground_hazard=True,
                enable_continuous_ocr=True,
                enable_neural_tts=capabilities.supports_neural_tts,
                audio_synthesis_mode="neural",
                max_onnx_threads=min(4, max(1, capabilities.cpu_cores)),
                frame_skip_ratio=1,
                degraded_features=degraded,
            )
