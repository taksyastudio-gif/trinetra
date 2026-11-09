"""
Hardware Abstraction Layer (HAL) package for TRINETRA v2.
"""

from trinetra_core.hal.camera import CameraAdapterInterface
from trinetra_core.hal.audio import AudioInAdapterInterface, AudioOutAdapterInterface
from trinetra_core.hal.location import LocationAdapterInterface
from trinetra_core.hal.comms import CommsAdapterInterface
from trinetra_core.hal.cellular_sms import (
    SerialGsmCommsAdapter,
    AndroidBridgeCommsAdapter,
    OutboxSpoolCommsAdapter,
    create_resilient_comms_adapter,
)
from trinetra_core.hal.storage import StorageAdapterInterface
from trinetra_core.hal.sensors import SensorsAdapterInterface
from trinetra_core.hal.wearable import (
    WearableDeviceInterface,
    ESP32CamWearableAdapter,
    SmartGlassesAdapter,
    HapticLocation,
    HapticPattern,
    WearableCapabilities,
)

__all__ = [
    "CameraAdapterInterface",
    "AudioInAdapterInterface",
    "AudioOutAdapterInterface",
    "LocationAdapterInterface",
    "CommsAdapterInterface",
    "SerialGsmCommsAdapter",
    "AndroidBridgeCommsAdapter",
    "OutboxSpoolCommsAdapter",
    "create_resilient_comms_adapter",
    "StorageAdapterInterface",
    "SensorsAdapterInterface",
    "WearableDeviceInterface",
    "ESP32CamWearableAdapter",
    "SmartGlassesAdapter",
    "HapticLocation",
    "HapticPattern",
    "WearableCapabilities",
]
