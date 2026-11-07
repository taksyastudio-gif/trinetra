"""
Unit tests for Wearable & Smart Glasses HAL:
- ESP32CamWearableAdapter
- SmartGlassesAdapter
- Haptic location and pattern dispatching
"""
import pytest
from trinetra_core.hal.wearable import (
    ESP32CamWearableAdapter,
    SmartGlassesAdapter,
    HapticLocation,
    HapticPattern,
    WearableCapabilities,
)


def test_esp32_cam_wearable_adapter():
    adapter = ESP32CamWearableAdapter(stream_url="http://192.168.4.1/stream")
    caps = adapter.get_capabilities()
    assert caps.has_camera is True
    assert caps.device_model == "AI-Thinker ESP32-CAM"
    assert adapter.is_active() is False

    adapter.start()
    assert adapter.is_active() is True
    assert adapter.get_resolution() == (640, 480)
    assert adapter.get_fps() == 15.0

    frame = adapter.capture_frame()
    assert frame is not None
    assert frame.startswith(b"\xff\xd8")  # JPEG SOI marker

    # Telemetry
    adapter.set_mock_battery(12.0, charging=False)
    assert adapter.get_battery_percentage() == 12.0
    assert adapter.is_charging() is False

    adapter.set_mock_temperature(75.0)
    assert adapter.is_thermal_throttling() is True

    # Haptic trigger
    ok = adapter.trigger_haptic(HapticLocation.CENTER, HapticPattern.SINGLE_SHORT)
    assert ok is True
    assert len(adapter._haptic_log) == 1

    adapter.stop()
    assert adapter.is_active() is False


def test_smart_glasses_adapter():
    glasses = SmartGlassesAdapter(device_id="glasses-cs12")
    caps = glasses.get_capabilities()
    assert caps.has_camera is True
    assert caps.has_haptics is True
    assert HapticLocation.LEFT_TEMPLE in caps.haptic_locations
    assert HapticLocation.RIGHT_TEMPLE in caps.haptic_locations

    glasses.start()
    assert glasses.is_active() is True
    assert glasses.get_resolution() == (1280, 720)
    assert glasses.get_fps() == 30.0

    # Directional haptic feedback
    assert glasses.trigger_haptic(HapticLocation.LEFT_TEMPLE, HapticPattern.URGENT_PULSE, intensity=0.9) is True
    assert len(glasses.haptic_commands) == 1
    assert glasses.haptic_commands[0]["location"] == "left_temple"
    assert glasses.haptic_commands[0]["pattern"] == "urgent_pulse"

    glasses.set_temperature(60.0)
    assert glasses.is_thermal_throttling() is True

    glasses.stop()
    assert glasses.is_active() is False
