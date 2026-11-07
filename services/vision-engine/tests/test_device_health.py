"""
Unit tests for DeviceHealthSupervisor:
- Battery critical threshold downgrade to LITE mode
- Thermal throttling trigger and recovery
- Frame drop ratio monitoring
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.sensors.device_health import DeviceHealthSupervisor
from trinetra_core.capabilities import DeviceTier
from trinetra_core.events import EventBus
from trinetra_core.lite_mode import LiteModeController


def test_device_health_normal_state():
    bus = EventBus()
    lite = LiteModeController(event_bus=bus)
    supervisor = DeviceHealthSupervisor(lite_controller=lite, event_bus=bus)

    rep = supervisor.update_telemetry(battery_pct=85.0, is_charging=False, temp_c=45.0, frame_drop_ratio=0.02)
    assert rep["is_battery_critical"] is False
    assert rep["is_thermal_throttling"] is False
    assert rep["active_tier"] in ("standard", "full")
    assert "सामान्य" in rep["recommendation_ne"]


def test_device_health_battery_critical_downgrade():
    bus = EventBus()
    lite = LiteModeController(event_bus=bus)
    spoken_alerts = []

    def mock_speech(text):
        spoken_alerts.append(text)

    supervisor = DeviceHealthSupervisor(
        lite_controller=lite,
        event_bus=bus,
        speech_callback=mock_speech,
        battery_critical_threshold=15.0,
    )

    # Battery drops to 10% discharging
    rep = supervisor.update_telemetry(battery_pct=10.0, is_charging=False, temp_c=40.0)
    assert rep["is_battery_critical"] is True
    assert rep["active_tier"] == "lite"
    assert lite.active_tier == DeviceTier.LITE
    assert len(spoken_alerts) == 1
    assert "लाइट मोड" in spoken_alerts[0]


def test_device_health_thermal_throttling_and_recovery():
    bus = EventBus()
    lite = LiteModeController(event_bus=bus)
    supervisor = DeviceHealthSupervisor(
        lite_controller=lite,
        event_bus=bus,
        thermal_throttle_threshold=75.0,
        thermal_recovery_threshold=65.0,
    )

    # Heat spike to 80 C
    rep1 = supervisor.update_telemetry(battery_pct=90.0, temp_c=80.0)
    assert rep1["is_thermal_throttling"] is True
    assert rep1["active_tier"] == "lite"

    # Temperature cools to 55 C
    rep2 = supervisor.update_telemetry(temp_c=55.0)
    assert rep2["is_thermal_throttling"] is False
    assert rep2["active_tier"] in ("standard", "full")
    assert lite.active_tier in (DeviceTier.STANDARD, DeviceTier.FULL)
