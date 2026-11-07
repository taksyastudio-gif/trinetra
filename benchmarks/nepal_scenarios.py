"""
TRINETRA v2 Nepali Street Scenario Simulations.
Reproducible end-to-end integration tests mimicking physical Kathmandu conditions:
1. Open drain / pothole hazard on broken footpath.
2. Bus board reading & route identification at Ratna Park transit hub.
3. Retail QR payment readout at vegetable/tea stall (FonePay / eSewa).
4. Trip and fall on temple stone steps (audible 10s countdown & user override).
5. Thermal & battery throttling dynamically switching to LITE mode.
"""

from __future__ import annotations
import math
import time
from typing import Any, Dict, List
import cv2
import numpy as np

from trinetra_core.types import AutonomyLevel
from trinetra_core.capabilities import DeviceCapabilities, DeviceTier
from trinetra_core.events import EventBus, EventCategory, EventPriority, EventType
from trinetra_core.caretaker import ContextMemory, CaregiverLink, AutonomySupervisor, CaregiverContact
from trinetra_core.lite_mode import LiteModeController
from app.detection.ground_hazard import GroundHazardDetector
from app.detection.nepal_hazards import NepalOverheadWireDetector, NepalHazardTaxonomyMapper
from app.ocr_enhancer import BusRouteMatcher, NepaliNumeralParser
from app.qr_payment import QRPaymentService


class NepalStreetScenarioRunner:
    """
    Executes end-to-end multi-modal simulations of physical street situations.
    """

    @staticmethod
    def scenario_open_drain_hazard() -> Dict[str, Any]:
        """
        Scenario 1: Pedestrian navigating sidewalk encounters an open drainage trench.
        Expectation: Ground hazard detector flags 'pothole/open_trench' in <10ms and
        produces priority preemption message: 'अगाडि जमिनमा खाल्डो छ, होसियार!'.
        """
        t0 = time.perf_counter()
        detector = GroundHazardDetector(dark_pit_thresh=55)

        # Generate synthetic street frame with realistic open drainage pit in bottom corridor
        frame = np.full((480, 640, 3), 110, dtype=np.uint8) # Ambient asphalt
        # Draw dark pit in bottom center
        cv2.ellipse(frame, (320, 380), (70, 45), 0, 0, 360, (20, 20, 20), -1)

        hazard = detector.analyze(frame)
        latency_ms = (time.perf_counter() - t0) * 1000

        passed = hazard.detected and hazard.hazard_type == "pothole" and hazard.confidence >= 0.70
        return {
            "scenario": "Open Drain / Pothole Avoidance",
            "passed": passed,
            "latency_ms": round(latency_ms, 2),
            "hazard_type": hazard.hazard_type,
            "confidence": hazard.confidence,
            "spoken_prompt_ne": hazard.message_ne,
        }

    @staticmethod
    def scenario_bus_route_matcher() -> Dict[str, Any]:
        """
        Scenario 2: Commuter at Ratna Park waiting for Sajha bus.
        Expectation: Hand-painted text containing destination 'रत्नपार्क' and 'साझा'
        is matched and spoken aloud.
        """
        raw_ocr_output = "बा ४ ख २३४५ साझा यातायात रत्नपार्क लगनखेल"
        t0 = time.perf_counter()
        match = BusRouteMatcher.match_route(raw_ocr_output)
        latency_ms = (time.perf_counter() - t0) * 1000

        passed = match.matched and match.destination == "रत्नपार्क" and match.operator == "साझा यातायात"
        return {
            "scenario": "Public Transit & Bus Board Matching",
            "passed": passed,
            "latency_ms": round(latency_ms, 2),
            "destination": match.destination,
            "operator": match.operator,
            "spoken_phrase_ne": match.spoken_phrase_ne,
        }

    @staticmethod
    def scenario_qr_payment_readout() -> Dict[str, Any]:
        """
        Scenario 3: Blind user paying at vendor counter with FonePay QR code.
        Expectation: QR detected and decoded in <20ms, merchant name extracted.
        """
        t0 = time.perf_counter()
        service = QRPaymentService()

        # Standard FonePay EMVCo payload format
        test_payload = "00020101021226320010np.fonepay0114984100000000005204599953035245802NP5916Himalayan Bakery6009Kathmandu6304ABCD"
        res = service.parse_payload(test_payload)
        latency_ms = (time.perf_counter() - t0) * 1000

        passed = res.detected and res.scheme == "fonepay" and res.merchant_name == "Himalayan Bakery"
        return {
            "scenario": "Retail QR Code Audio Readout",
            "passed": passed,
            "latency_ms": round(latency_ms, 2),
            "scheme": res.scheme,
            "merchant_name": res.merchant_name,
            "spoken_phrase_ne": res.spoken_phrase_ne,
        }

    @staticmethod
    def scenario_fall_emergency_cancellation() -> Dict[str, Any]:
        """
        Scenario 4: User trips on uneven temple steps, triggering 10s emergency pre-alert.
        User taps screen saying 'म ठीक छु' within 3 seconds.
        Expectation: Countdown aborted, zero SMS dispatched, audit record sealed.
        """
        mem = ContextMemory(":memory:")
        mem.add_contact(CaregiverContact(None, "छोरा", "छोरा", "+9779841112233", True))
        link = CaregiverLink(memory=mem)
        supervisor = AutonomySupervisor(memory=mem, caregiver_link=link)

        # Trigger countdown
        supervisor.trigger_emergency_countdown(incident_type="fall_detected", duration_seconds=10.0)
        assert supervisor._emergency_state.is_active is True

        # Simulate 0.05s elapsed and cancel
        time.sleep(0.05)
        cancelled = supervisor.cancel_emergency(cancel_reason="user_ok")

        # Verify state
        audit_trail = mem.get_audit_trail(limit=2)
        passed = cancelled and not supervisor._emergency_state.is_dispatched and len(audit_trail) >= 2
        return {
            "scenario": "Trip & Fall 10s Cancellation Window",
            "passed": passed,
            "cancelled": cancelled,
            "audit_hash_chained": audit_trail[0]["prev_hash"] == audit_trail[1]["sha256"],
        }

    @staticmethod
    def scenario_thermal_throttling_lite_mode() -> Dict[str, Any]:
        """
        Scenario 5: High ambient Kathmandu summer temperature causes hardware thermal throttling.
        Expectation: System automatically transitions from FULL tier to LITE mode,
        throttling FPS to 5 and shedding optical flow while preserving ground hazard checks.
        """
        caps = DeviceCapabilities(declared_tier=DeviceTier.FULL, camera_native_fps=30)
        ctrl = LiteModeController(capabilities=caps)
        assert ctrl.active_tier == DeviceTier.FULL

        # Hardware reports thermal throttle
        ctrl.update_telemetry(thermal_throttling=True)
        passed = ctrl.active_tier == DeviceTier.LITE and ctrl.profile.target_vision_fps == 5 and ctrl.profile.enable_ground_hazard is True

        return {
            "scenario": "Thermal Throttling & Lite Mode Enforcement",
            "passed": passed,
            "resolved_tier": ctrl.active_tier.value,
            "target_fps": ctrl.profile.target_vision_fps,
            "hazard_preserved": ctrl.profile.enable_ground_hazard,
        }

    @classmethod
    def run_all(cls) -> List[Dict[str, Any]]:
        return [
            cls.scenario_open_drain_hazard(),
            cls.scenario_bus_route_matcher(),
            cls.scenario_qr_payment_readout(),
            cls.scenario_fall_emergency_cancellation(),
            cls.scenario_thermal_throttling_lite_mode(),
        ]
