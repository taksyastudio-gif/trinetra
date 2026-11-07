"""
Event protocol package for TRINETRA v2.
"""

from trinetra_core.events.schema import (
    Event,
    EventCategory,
    EventPriority,
    EventType,
)
from trinetra_core.events.bus import EventBus

__all__ = [
    "Event",
    "EventCategory",
    "EventPriority",
    "EventType",
    "EventBus",
]
