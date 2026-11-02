"""
Tests for Trinetra Phase 3: Offline Location Capability Layer.
Validates privacy-safe defaults, manual offline coordinates, Windows Location fallback,
and strict anti-hallucination guarantees (never guessing or fabricating GPS coordinates).
"""

import pytest

from app.location.provider import (
    DisabledLocationProvider,
    LocationManager,
    LocationStatus,
    ManualOfflineLocationProvider,
    PRIVACY_GUARANTEE_STATEMENT,
    WindowsLocationProvider,
)


def test_disabled_location_provider_default():
    """Validates that location is disabled by default with strict privacy guarantees."""
    provider = DisabledLocationProvider()
    rep = provider.get_location()

    assert rep.status == LocationStatus.DISABLED
    assert rep.latitude is None
    assert rep.longitude is None
    assert rep.accuracy_meters is None
    assert rep.is_live is False
    assert rep.privacy_notice == PRIVACY_GUARANTEE_STATEMENT


def test_manual_offline_location_provider():
    """Validates manual offline landmark coordinate provision (e.g., Kathmandu base)."""
    provider = ManualOfflineLocationProvider(
        latitude=27.7172,
        longitude=85.3240,
        accuracy_meters=25.0,
        notes="Kathmandu Reference"
    )
    rep = provider.get_location()

    assert rep.status == LocationStatus.CACHED
    assert rep.latitude == 27.7172
    assert rep.longitude == 85.3240
    assert rep.accuracy_meters == 25.0
    assert rep.source == "manual_offline"
    assert rep.is_live is False
    assert rep.is_stale is False

    # When disabled, returns disabled status
    provider.disable()
    assert provider.get_location().status == LocationStatus.DISABLED


def test_windows_location_provider_safe_fallback():
    """Validates that WindowsLocationProvider safely handles hardware/permission limits without raising."""
    provider = WindowsLocationProvider()
    # Initially disabled
    assert provider.get_location().status == LocationStatus.DISABLED

    provider.enable()
    rep = provider.get_location()
    # On environments without GPS hardware or permissions, reports UNAVAILABLE honestly
    assert rep.status in (LocationStatus.LIVE, LocationStatus.UNAVAILABLE, LocationStatus.CACHED)
    if rep.status == LocationStatus.UNAVAILABLE:
        assert rep.latitude is None
        assert rep.longitude is None
        assert rep.is_live is False


def test_anti_hallucination_strict_guarantee():
    """Validates that under no circumstances does an unconfigured provider return fabricated coordinates."""
    mgr = LocationManager()
    rep = mgr.get_report()
    assert rep.status == LocationStatus.DISABLED
    assert rep.latitude is None
    assert rep.longitude is None

    # Test with empty manual provider
    mgr.set_provider(ManualOfflineLocationProvider(latitude=None, longitude=None))
    empty_rep = mgr.get_report()
    assert empty_rep.status == LocationStatus.UNAVAILABLE
    assert empty_rep.latitude is None
    assert empty_rep.longitude is None
