"""
TRINETRA v2 Event Protocol Schema (v2.0)
Standardized event primitives across all devices and core workers.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum, IntEnum
import hashlib
import json
import time
from typing import Any, Dict, Optional
import uuid


class EventPriority(IntEnum):
    """
    Priority ordering for event bus dispatch and audio preemption.
    Higher integer = higher priority.
    """
    LOW = 10
    NORMAL = 20
    HIGH = 30
    CRITICAL_HAZARD = 40


class EventCategory(str, Enum):
    PERCEPTION = "perception"
    NAVIGATION = "navigation"
    ASSISTIVE = "assistive"
    HEALTH_WELLBEING = "health_wellbeing"
    CARETAKER = "caretaker"
    SYSTEM_LIFECYCLE = "system_lifecycle"


class EventType(str, Enum):
    # Perception events
    DETECTION_FRAME = "perception.detection_frame"
    SURFACE_HAZARD = "perception.surface_hazard"           # Pothole, open drain, trench
    OVERHEAD_HAZARD = "perception.overhead_hazard"         # Low wires, protruding branches
    OBSTACLE_APPROACHING = "perception.obstacle_approaching"# Fast obstacle on collision course
    SIGN_GESTURE = "perception.sign_gesture"               # NSL or universal gesture
    
    # Assistive events
    OCR_READ = "assistive.ocr_read"
    CURRENCY_IDENTIFIED = "assistive.currency_identified"
    QR_PAYMENT_DETECTED = "assistive.qr_payment_detected"
    SCENE_GROUNDING = "assistive.scene_grounding"
    
    # Dialogue & Voice
    VOICE_COMMAND = "speech.voice_command"
    SPEECH_ANNOUNCEMENT = "speech.announcement"
    
    # Caretaker & Routines
    REMINDER_TRIGGER = "caretaker.reminder_trigger"
    MEDICATION_DUE = "caretaker.medication_due"
    FALL_SUSPECTED = "caretaker.fall_suspected"
    INACTIVITY_WARNING = "caretaker.inactivity_warning"
    LOCATION_BOOKMARK = "caretaker.location_bookmark"
    
    # Autonomy L4 Emergency Protocol
    EMERGENCY_PREALERT = "emergency.prealert"             # 10s countdown start
    EMERGENCY_CANCELLED = "emergency.cancelled"           # User pressed "I'm OK"
    EMERGENCY_DISPATCH = "emergency.dispatch"             # SMS / Alert dispatched
    
    # System Lifecycle & Health
    DEVICE_HEALTH = "system.device_health"
    TIER_CHANGED = "system.tier_changed"
    LITE_MODE_TRIGGERED = "system.lite_mode_triggered"


@dataclass
class Event:
    """
    Standardized TRINETRA event container.
    """
    event_type: EventType
    category: EventCategory
    priority: EventPriority = EventPriority.NORMAL
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_utc: float = field(default_factory=time.time)
    source_device: str = "core"
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else str(self.event_type),
            "category": self.category.value if isinstance(self.category, EventCategory) else str(self.category),
            "priority": int(self.priority),
            "timestamp_utc": self.timestamp_utc,
            "source_device": self.source_device,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Event:
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=EventType(data["event_type"]) if data["event_type"] in EventType._value2member_map_ else data["event_type"],
            category=EventCategory(data["category"]) if data["category"] in EventCategory._value2member_map_ else data["category"],
            priority=EventPriority(data.get("priority", EventPriority.NORMAL)),
            timestamp_utc=data.get("timestamp_utc", time.time()),
            source_device=data.get("source_device", "core"),
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
        )

    def compute_sha256(self) -> str:
        """Computes deterministic cryptographic fingerprint for tamper-evident logging."""
        canonical_json = json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
