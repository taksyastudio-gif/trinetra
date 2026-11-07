"""
Device Profiles and Capability Declarations for TRINETRA v2.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from trinetra_core.types import DeviceType


class DeviceTier(str, Enum):
    """
    Operating performance tiers:
    FULL: High-end laptop / workstation (Uncapped / 30-60 FPS, all neural nets active)
    STANDARD: Budget laptop / mid-range phone (15 FPS, optimized single-thread inference)
    LITE: Low-end phone / wearable / battery conservation (5 FPS, hazard-only, chime audio)
    """
    FULL = "full"
    STANDARD = "standard"
    LITE = "lite"


@dataclass
class DeviceCapabilities:
    """
    Hardware and sensor capabilities declared by a physical host or wearable.
    """
    device_type: DeviceType = DeviceType.DESKTOP_WORKSTATION
    declared_tier: DeviceTier = DeviceTier.FULL
    
    # Visual capabilities
    has_camera: bool = True
    camera_native_fps: int = 30
    camera_width: int = 640
    camera_height: int = 480
    
    # Audio capabilities
    has_microphone: bool = True
    has_speaker: bool = True
    supports_neural_tts: bool = True
    
    # Sensory & Telephony
    has_gps: bool = False
    has_cellular_sms: bool = False
    has_accelerometer: bool = False
    
    # Compute & Power constraints
    cpu_cores: int = 4
    ram_mb: int = 4096
    is_battery_powered: bool = False
    battery_level_pct: Optional[float] = None
    thermal_throttling_active: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_type": self.device_type.value,
            "declared_tier": self.declared_tier.value,
            "has_camera": self.has_camera,
            "camera_native_fps": self.camera_native_fps,
            "camera_resolution": f"{self.camera_width}x{self.camera_height}",
            "has_microphone": self.has_microphone,
            "has_speaker": self.has_speaker,
            "supports_neural_tts": self.supports_neural_tts,
            "has_gps": self.has_gps,
            "has_cellular_sms": self.has_cellular_sms,
            "has_accelerometer": self.has_accelerometer,
            "cpu_cores": self.cpu_cores,
            "ram_mb": self.ram_mb,
            "is_battery_powered": self.is_battery_powered,
            "battery_level_pct": self.battery_level_pct,
            "thermal_throttling_active": self.thermal_throttling_active,
        }
