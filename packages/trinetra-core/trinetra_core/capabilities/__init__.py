"""
Capability negotiation package for TRINETRA v2.
"""

from trinetra_core.capabilities.device import DeviceCapabilities, DeviceTier
from trinetra_core.capabilities.negotiator import CapabilityNegotiator, NegotiatedProfile

__all__ = [
    "DeviceCapabilities",
    "DeviceTier",
    "CapabilityNegotiator",
    "NegotiatedProfile",
]
