"""
Comprehensive Unit & Integration Test Suite for TRINETRA v2 Core (trinetra_core)
Verifies Event Protocol v2.0, HAL Interfaces, Capability Negotiation,
Lite Mode Controller, and Model Abstractions.
"""

import time
import pytest
from typing import Any, Dict, List, Optional, Tuple

from trinetra_core.types import (
    BoundingBox,
    Point2D,
    Vector2D,
    DeviceType,
    AutonomyLevel,
    FrameMetadata,
)
from trinetra_core.events import (
    Event,
    EventCategory,
    EventPriority,
    EventType,
    EventBus,
)
from trinetra_core.hal import (
    CameraAdapterInterface,
    AudioInAdapterInterface,
    AudioOutAdapterInterface,
    LocationAdapterInterface,
    CommsAdapterInterface,
    StorageAdapterInterface,
    SensorsAdapterInterface,
)
from trinetra_core.capabilities import (
    DeviceCapabilities,
    DeviceTier,
    CapabilityNegotiator,
    NegotiatedProfile,
)
from trinetra_core.lite_mode import LiteModeController
from trinetra_core.models import BaseModelInterface, ModelMetadata


# ============================================================================
# 1. TYPES & PRIMITIVES TESTS
# ============================================================================

def test_bounding_box_calculations():
    bbox = BoundingBox(xmin=10.0, ymin=20.0, xmax=110.0, ymax=120.0)
    assert bbox.width == 100.0
    assert bbox.height == 100.0
    assert bbox.center_x == 60.0
    assert bbox.center_y == 70.0
    assert bbox.area == 10000.0


def test_bounding_box_iou():
    box1 = BoundingBox(0.0, 0.0, 10.0, 10.0)  # Area 100
    box2 = BoundingBox(5.0, 0.0, 15.0, 10.0)  # Area 100, Intersection 5x10 = 50, Union 150
    assert abs(box1.iou(box2) - (50.0 / 150.0)) < 1e-5

    # Non-overlapping
    box3 = BoundingBox(20.0, 20.0, 30.0, 30.0)
    assert box1.iou(box3) == 0.0


def test_frame_metadata_defaults():
    meta = FrameMetadata(frame_id=42)
    assert meta.frame_id == 42
    assert meta.width == 640
    assert meta.source_device == DeviceType.DESKTOP_WORKSTATION
    assert meta.exposure_status == "normal"


# ============================================================================
# 2. EVENT PROTOCOL v2.0 & EVENT BUS TESTS
# ============================================================================

def test_event_serialization_and_hash():
    evt = Event(
        event_type=EventType.SURFACE_HAZARD,
        category=EventCategory.PERCEPTION,
        priority=EventPriority.CRITICAL_HAZARD,
        source_device="desktop_test",
        payload={"hazard": "pothole", "distance_meters": 1.5},
    )
    data = evt.to_dict()
    assert data["event_type"] == "perception.surface_hazard"
    assert data["priority"] == 40
    assert data["payload"]["hazard"] == "pothole"

    reconstructed = Event.from_dict(data)
    assert reconstructed.event_type == EventType.SURFACE_HAZARD
    assert reconstructed.priority == EventPriority.CRITICAL_HAZARD
    assert reconstructed.payload["distance_meters"] == 1.5

    # Deterministic SHA-256
    hash1 = evt.compute_sha256()
    hash2 = reconstructed.compute_sha256()
    assert hash1 == hash2
    assert len(hash1) == 64


def test_event_bus_subscriptions_and_hash_chain():
    bus = EventBus(history_capacity=100)
    
    received_type: List[Event] = []
    received_category: List[Event] = []
    received_global: List[Event] = []

    bus.subscribe(lambda e: received_type.append(e), event_type=EventType.SURFACE_HAZARD)
    bus.subscribe(lambda e: received_category.append(e), category=EventCategory.PERCEPTION)
    bus.subscribe(lambda e: received_global.append(e))

    e1 = Event(
        event_type=EventType.SURFACE_HAZARD,
        category=EventCategory.PERCEPTION,
        priority=EventPriority.CRITICAL_HAZARD,
        payload={"hazard": "open_drain"},
    )
    e2 = Event(
        event_type=EventType.OCR_READ,
        category=EventCategory.ASSISTIVE,
        priority=EventPriority.NORMAL,
        payload={"text": "रत्नपार्क"},
    )

    h1 = bus.publish(e1)
    h2 = bus.publish(e2)

    # Verification of subscriptions
    assert len(received_type) == 1
    assert received_type[0].payload["hazard"] == "open_drain"
    assert len(received_category) == 1
    assert len(received_global) == 2

    # Verification of cryptographic hash chaining
    history = bus.get_history()
    assert len(history) == 2
    assert history[0].metadata["prev_hash"] == "0" * 64
    assert history[0].metadata["sha256"] == h1
    assert history[1].metadata["prev_hash"] == h1
    assert history[1].metadata["sha256"] == h2


def test_event_bus_unsubscribe():
    bus = EventBus()
    events = []
    handler = lambda e: events.append(e)

    bus.subscribe(handler, event_type=EventType.REMINDER_TRIGGER)
    bus.publish(Event(event_type=EventType.REMINDER_TRIGGER, category=EventCategory.CARETAKER))
    assert len(events) == 1

    bus.unsubscribe(handler)
    bus.publish(Event(event_type=EventType.REMINDER_TRIGGER, category=EventCategory.CARETAKER))
    assert len(events) == 1


# ============================================================================
# 3. HARDWARE ABSTRACTION LAYER (HAL) TESTS
# ============================================================================

class MockCamera(CameraAdapterInterface):
    def __init__(self):
        self._is_open = False
        self._frames = 0

    def open(self, source_index_or_url: Any = 0) -> bool:
        self._is_open = True
        return True

    def close(self) -> None:
        self._is_open = False

    def read_frame(self) -> Tuple[bool, Optional[Any], Optional[FrameMetadata]]:
        if not self._is_open:
            return False, None, None
        self._frames += 1
        return True, "mock_frame_data", FrameMetadata(frame_id=self._frames)

    def is_healthy(self) -> bool:
        return self._is_open

    def get_telemetry(self) -> Dict[str, Any]:
        return {"active": self._is_open, "frames_captured": self._frames}


class MockAudioOut(AudioOutAdapterInterface):
    def __init__(self):
        self.spoken: List[str] = []
        self._speaking = False
        self._rate = 1.0

    def speak(self, text: str, priority: EventPriority = EventPriority.NORMAL, language: str = "ne", interrupt: bool = False) -> bool:
        if interrupt:
            self.spoken.clear()
        self.spoken.append(text)
        return True

    def stop(self) -> None:
        self._speaking = False

    def is_speaking(self) -> bool:
        return self._speaking

    def set_speech_rate(self, rate: float) -> None:
        self._rate = rate

    def get_status(self) -> Dict[str, Any]:
        return {"spoken_count": len(self.spoken), "rate": self._rate}


class MockComms(CommsAdapterInterface):
    def __init__(self):
        self.outbox: List[Tuple[str, str]] = []

    def send_sms(self, recipient_phone: str, text_message: str) -> bool:
        self.outbox.append((recipient_phone, text_message))
        return True

    def is_cellular_available(self) -> bool:
        return True

    def get_signal_quality(self) -> Dict[str, Any]:
        return {"csq": 24, "operator": "NTC"}


def test_hal_interfaces():
    # Verify camera
    cam = MockCamera()
    assert cam.open(0) is True
    ok, frame, meta = cam.read_frame()
    assert ok is True
    assert meta.frame_id == 1
    assert cam.is_healthy() is True
    cam.close()
    assert cam.is_healthy() is False

    # Verify audio
    audio = MockAudioOut()
    audio.speak("नमस्ते", priority=EventPriority.NORMAL)
    assert "नमस्ते" in audio.spoken
    audio.speak("आपतकालीन!", priority=EventPriority.CRITICAL_HAZARD, interrupt=True)
    assert audio.spoken == ["आपतकालीन!"]

    # Verify comms
    comms = MockComms()
    assert comms.send_sms("+9779841000000", "TRINETRA Alert: Fall detected at 27.7172, 85.3240") is True
    assert len(comms.outbox) == 1
    assert comms.outbox[0][0] == "+9779841000000"


# ============================================================================
# 4. CAPABILITY NEGOTIATION TESTS
# ============================================================================

def test_negotiate_full_tier():
    caps = DeviceCapabilities(
        declared_tier=DeviceTier.FULL,
        camera_native_fps=30,
        cpu_cores=8,
        ram_mb=16384,
        supports_neural_tts=True,
    )
    profile = CapabilityNegotiator.negotiate(caps)
    assert profile.active_tier == DeviceTier.FULL
    assert profile.target_vision_fps == 30
    assert profile.enable_optical_flow is True
    assert profile.enable_ground_hazard is True
    assert profile.enable_continuous_ocr is True
    assert profile.max_onnx_threads == 4
    assert profile.frame_skip_ratio == 1


def test_negotiate_standard_tier():
    caps = DeviceCapabilities(
        declared_tier=DeviceTier.STANDARD,
        camera_native_fps=30,
        cpu_cores=4,
        ram_mb=4096,
        supports_neural_tts=True,
    )
    profile = CapabilityNegotiator.negotiate(caps)
    assert profile.active_tier == DeviceTier.STANDARD
    assert profile.target_vision_fps == 15
    assert profile.enable_optical_flow is False
    assert profile.enable_ground_hazard is True
    assert profile.max_onnx_threads == 2
    assert profile.frame_skip_ratio == 2


def test_negotiate_lite_tier_and_throttles():
    # 1. Explicit LITE
    caps = DeviceCapabilities(
        declared_tier=DeviceTier.LITE,
        camera_native_fps=30,
        cpu_cores=2,
        ram_mb=2048,
    )
    profile = CapabilityNegotiator.negotiate(caps)
    assert profile.active_tier == DeviceTier.LITE
    assert profile.target_vision_fps == 5
    assert profile.enable_optical_flow is False
    assert profile.enable_continuous_ocr is False
    assert profile.max_onnx_threads == 1
    assert profile.frame_skip_ratio == 6  # 30 // 5 = 6

    # 2. Dynamic downgrade on Thermal Throttling
    caps_hot = DeviceCapabilities(
        declared_tier=DeviceTier.FULL,
        thermal_throttling_active=True,
    )
    profile_hot = CapabilityNegotiator.negotiate(caps_hot)
    assert profile_hot.active_tier == DeviceTier.LITE
    assert "thermal_throttling_active" in profile_hot.degraded_features

    # 3. Dynamic downgrade on Critical Battery
    caps_battery = DeviceCapabilities(
        declared_tier=DeviceTier.FULL,
        is_battery_powered=True,
        battery_level_pct=12.0,
    )
    profile_battery = CapabilityNegotiator.negotiate(caps_battery)
    assert profile_battery.active_tier == DeviceTier.LITE
    assert "critical_battery_power_save" in profile_battery.degraded_features


# ============================================================================
# 5. LITE MODE CONTROLLER TESTS
# ============================================================================

def test_lite_mode_controller_lifecycle():
    bus = EventBus()
    events = []
    bus.subscribe(lambda e: events.append(e), category=EventCategory.SYSTEM_LIFECYCLE)

    caps = DeviceCapabilities(
        declared_tier=DeviceTier.FULL,
        camera_native_fps=30,
        is_battery_powered=True,
        battery_level_pct=90.0,
    )
    ctrl = LiteModeController(capabilities=caps, event_bus=bus)

    assert ctrl.active_tier == DeviceTier.FULL
    assert ctrl.is_lite_mode is False
    assert ctrl.should_process_frame(0) is True
    assert ctrl.should_run_continuous_ocr() is True

    # Drop battery to critical level
    changed = ctrl.update_telemetry(battery_pct=10.0)
    assert changed is True
    assert ctrl.active_tier == DeviceTier.LITE
    assert ctrl.is_lite_mode is True
    assert ctrl.should_run_continuous_ocr() is False
    assert len(events) == 1
    assert events[0].event_type == EventType.LITE_MODE_TRIGGERED

    # Frame skipping at 5 FPS on 30 FPS camera (skip ratio = 6)
    assert ctrl.should_process_frame(0) is True
    assert ctrl.should_process_frame(1) is False
    assert ctrl.should_process_frame(5) is False
    assert ctrl.should_process_frame(6) is True

    # Manual force tier override
    ctrl.force_tier(DeviceTier.STANDARD)
    assert ctrl.active_tier == DeviceTier.STANDARD
    assert ctrl.is_lite_mode is False


# ============================================================================
# 6. MODEL STRATEGY & METADATA TESTS
# ============================================================================

class MockModel(BaseModelInterface):
    def __init__(self):
        self._loaded = False
        self._meta = ModelMetadata(
            name="yolox_nepal_test",
            version="0.2.0",
            architecture="YOLOX-Nano",
            framework="onnx",
            license="Apache-2.0",
            origin_dataset="COCO 2017 + NSHD",
            nepal_bias_notes="Fine-tuned for open drains and tempos.",
            supported_classes=["person", "open_drain", "tempo"],
            input_resolution=(416, 416),
        )

    def load(self, model_path: str, execution_provider: str = "CPU", num_threads: int = 2) -> bool:
        self._loaded = True
        return True

    def predict(self, inputs: Any) -> Any:
        return [{"class": "open_drain", "confidence": 0.88}]

    def unload(self) -> None:
        self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def metadata(self) -> ModelMetadata:
        return self._meta

    def get_average_latency_ms(self) -> float:
        return 18.5


def test_model_abstraction():
    model = MockModel()
    assert model.is_loaded() is False
    assert model.metadata.name == "yolox_nepal_test"
    assert "open_drain" in model.metadata.supported_classes

    meta_dict = model.metadata.to_dict()
    assert meta_dict["framework"] == "onnx"
    assert meta_dict["license"] == "Apache-2.0"

    assert model.load("dummy.onnx") is True
    assert model.is_loaded() is True
    res = model.predict("test_frame")
    assert res[0]["class"] == "open_drain"
    assert model.get_average_latency_ms() == 18.5
    model.unload()
    assert model.is_loaded() is False
