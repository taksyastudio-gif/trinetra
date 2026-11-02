"""
Trinetra Offline Location Capability Layer.

Hardware-independent location provider abstraction designed for privacy and local-first operation:
1. Disabled by default to prevent unauthorized location telemetry.
2. Hardware-independent abstraction with Windows Location integration where available.
3. Offline support: Caches last-known position and supports manual offline coordinates.
4. Truthful accuracy reporting: Distinguishes live, cached, unavailable, and disabled states.
5. Strict anti-hallucination constraint: NEVER fabricates or guesses GPS coordinates.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
import os
import subprocess
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("trinetra.location")

PRIVACY_GUARANTEE_STATEMENT = (
    "Local-only processing. Location telemetry is strictly confined to on-device memory "
    "and optional local incident logs. No coordinates are shared or transmitted to external servers."
)


class LocationStatus(str, Enum):
    LIVE = "live"
    CACHED = "cached"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


@dataclass
class LocationReport:
    status: LocationStatus
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_meters: Optional[float] = None
    timestamp_utc: Optional[str] = None
    timestamp_epoch: Optional[float] = None
    source: str = "disabled"
    is_live: bool = False
    is_stale: bool = False
    privacy_notice: str = PRIVACY_GUARANTEE_STATEMENT

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class LocationProvider(ABC):
    """Abstract contract for local location providers."""

    @abstractmethod
    def get_location(self) -> LocationReport:
        """Returns the current location report. Must NOT block indefinitely."""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Returns True if the provider is currently enabled."""
        pass

    @abstractmethod
    def enable(self) -> None:
        """Enables location queries (explicit user opt-in required)."""
        pass

    @abstractmethod
    def disable(self) -> None:
        """Disables location queries and purges cached location if requested."""
        pass


class DisabledLocationProvider(LocationProvider):
    """Default privacy-safe provider: strictly returns disabled status."""

    def __init__(self):
        self._enabled = False

    def is_enabled(self) -> bool:
        return False

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def get_location(self) -> LocationReport:
        return LocationReport(
            status=LocationStatus.DISABLED,
            source="disabled",
            is_live=False,
            is_stale=False,
            latitude=None,
            longitude=None,
            accuracy_meters=None,
        )


class ManualOfflineLocationProvider(LocationProvider):
    """
    Offline location provider allowing manual landmark or home base coordinates.
    Never fabricates coordinates; uses only explicitly configured values.
    """

    def __init__(
        self,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        accuracy_meters: Optional[float] = 50.0,
        notes: str = "Manual offline reference"
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.accuracy_meters = accuracy_meters
        self.notes = notes
        self._enabled = True

    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def get_location(self) -> LocationReport:
        if not self._enabled:
            return LocationReport(status=LocationStatus.DISABLED, source="manual_offline")

        if self.latitude is None or self.longitude is None:
            return LocationReport(
                status=LocationStatus.UNAVAILABLE,
                source="manual_offline",
                is_live=False,
                is_stale=False
            )

        now = datetime.now(timezone.utc)
        return LocationReport(
            status=LocationStatus.CACHED,
            latitude=round(self.latitude, 6),
            longitude=round(self.longitude, 6),
            accuracy_meters=self.accuracy_meters,
            timestamp_utc=now.isoformat(),
            timestamp_epoch=now.timestamp(),
            source="manual_offline",
            is_live=False,
            is_stale=False
        )


class WindowsLocationProvider(LocationProvider):
    """
    Local Windows Geolocation provider.
    Interrogates local Windows device location services safely without cloud dependencies.
    If location services are denied or hardware is unavailable, reports UNAVAILABLE honestly.
    """

    def __init__(self, cache_timeout_seconds: float = 600.0):
        self._enabled = False
        self._cache_timeout = cache_timeout_seconds
        self._last_report: Optional[LocationReport] = None
        self._lock = threading.RLock()

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def enable(self) -> None:
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        with self._lock:
            self._enabled = False
            self._last_report = None

    def get_location(self) -> LocationReport:
        with self._lock:
            if not self._enabled:
                return LocationReport(status=LocationStatus.DISABLED, source="windows_location")

            # Check cache freshness
            now = time.time()
            if self._last_report and self._last_report.timestamp_epoch:
                age = now - self._last_report.timestamp_epoch
                if age < 30.0:  # Fresh within 30 seconds
                    return self._last_report
                elif age < self._cache_timeout:
                    # Return cached report with stale indicator
                    return LocationReport(
                        status=LocationStatus.CACHED,
                        latitude=self._last_report.latitude,
                        longitude=self._last_report.longitude,
                        accuracy_meters=self._last_report.accuracy_meters,
                        timestamp_utc=self._last_report.timestamp_utc,
                        timestamp_epoch=self._last_report.timestamp_epoch,
                        source="windows_location_cached",
                        is_live=False,
                        is_stale=True,
                    )

            # Attempt live query via PowerShell Windows.Devices.Geolocation
            try:
                report = self._query_windows_geolocation()
                if report.status == LocationStatus.LIVE:
                    self._last_report = report
                return report
            except Exception as exc:
                logger.debug(f"Windows geolocation query failed: {exc}")
                if self._last_report:
                    return LocationReport(
                        status=LocationStatus.CACHED,
                        latitude=self._last_report.latitude,
                        longitude=self._last_report.longitude,
                        accuracy_meters=self._last_report.accuracy_meters,
                        timestamp_utc=self._last_report.timestamp_utc,
                        timestamp_epoch=self._last_report.timestamp_epoch,
                        source="windows_location_cached",
                        is_live=False,
                        is_stale=True,
                    )
                return LocationReport(
                    status=LocationStatus.UNAVAILABLE,
                    source="windows_location",
                    is_live=False,
                    is_stale=False,
                )

    def _query_windows_geolocation(self) -> LocationReport:
        """Queries local Windows GeoCoordinateWatcher with strict timeout."""
        ps_cmd = (
            "Add-Type -AssemblyName System.Device; "
            "$w = New-Object System.Device.Location.GeoCoordinateWatcher; "
            "$w.Start(); "
            "$s = 0; while (($w.Status -ne [System.Device.Location.GeoPositionStatus]::Ready) -and ($s -lt 15)) { Start-Sleep -Milliseconds 100; $s++ }; "
            "if ($w.Status -eq [System.Device.Location.GeoPositionStatus]::Ready) { "
            "  $c = $w.Position.Location; "
            "  Write-Output \"$($c.Latitude),$($c.Longitude),$($c.HorizontalAccuracy)\" "
            "} else { Write-Output 'UNAVAILABLE' }; "
            "$w.Stop()"
        )

        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=3.0
            )
            out = proc.stdout.strip()
            if out and out != "UNAVAILABLE" and "," in out:
                parts = out.split(",")
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                acc = float(parts[2].strip()) if len(parts) > 2 and parts[2].strip() != "NaN" else 50.0

                now = datetime.now(timezone.utc)
                return LocationReport(
                    status=LocationStatus.LIVE,
                    latitude=round(lat, 6),
                    longitude=round(lon, 6),
                    accuracy_meters=round(acc, 1),
                    timestamp_utc=now.isoformat(),
                    timestamp_epoch=now.timestamp(),
                    source="windows_geolocation",
                    is_live=True,
                    is_stale=False,
                )
        except Exception:
            pass

        return LocationReport(
            status=LocationStatus.UNAVAILABLE,
            source="windows_location",
            is_live=False,
            is_stale=False,
        )


class LocationManager:
    """Singleton holder for authoritative location provider."""

    def __init__(self, provider: Optional[LocationProvider] = None):
        self.provider: LocationProvider = provider or DisabledLocationProvider()
        self._lock = threading.RLock()

    def get_report(self) -> LocationReport:
        with self._lock:
            return self.provider.get_location()

    def set_provider(self, provider: LocationProvider) -> None:
        with self._lock:
            self.provider = provider

    def enable(self) -> None:
        with self._lock:
            self.provider.enable()

    def disable(self) -> None:
        with self._lock:
            self.provider.disable()
