"""
Unit and Integration Tests for TRINETRA v2 Caretaker Engine:
- ContextMemory (SQLite persistence, routines, contacts, audit log)
- CaregiverLink (SMS formatting, transmission, and cooldowns)
- RoutineScheduler (Medication checks, snooze, taken acknowledgment)
- FallDetector & InactivityMonitor (IMU & optical flow fall detection)
- AutonomySupervisor (L0-L4 governance & 10s emergency countdown)
"""

import os
import sys
import time
import pytest

# Ensure services/vision-engine is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from trinetra_core.types import AutonomyLevel
from trinetra_core.events import EventBus, EventCategory, EventPriority, EventType
from trinetra_core.hal import CommsAdapterInterface
from trinetra_core.caretaker import (
    ContextMemory,
    MedicationItem,
    CaregiverContact,
    CaregiverLink,
    RoutineScheduler,
    FallDetector,
    InactivityMonitor,
    AutonomySupervisor,
)


# ============================================================================
# 1. CONTEXT MEMORY TESTS
# ============================================================================

def test_context_memory_preferences_and_autonomy():
    mem = ContextMemory(":memory:")
    assert mem.get_autonomy_level() == AutonomyLevel.L2_ACT_CONFIRMED

    mem.set_autonomy_level(AutonomyLevel.L3_ROUTINE_AUTO)
    assert mem.get_autonomy_level() == AutonomyLevel.L3_ROUTINE_AUTO

    mem.set_preference("speech_rate", 1.25)
    assert mem.get_preference("speech_rate") == 1.25


def test_context_memory_medications():
    mem = ContextMemory(":memory:")
    med = MedicationItem(
        id=None,
        medicine_name="पारासिटामोल",
        dosage="५०० मि.ग्रा., १ चक्की",
        timing_type="after_meal",
        time_of_day="08:00",
    )
    med_id = mem.add_medication(med)
    assert med_id > 0

    meds = mem.list_medications(active_only=True)
    assert len(meds) == 1
    assert meds[0].medicine_name == "पारासिटामोल"
    assert meds[0].last_taken_utc is None

    # Mark taken
    assert mem.mark_medication_taken(med_id) is True
    meds_updated = mem.list_medications(active_only=True)
    assert meds_updated[0].last_taken_utc is not None


def test_context_memory_contacts():
    mem = ContextMemory(":memory:")
    c1 = CaregiverContact(
        id=None,
        name="राम थापा",
        relationship="छोरा",
        phone_number="+9779841000001",
        is_primary_emergency=True,
    )
    c2 = CaregiverContact(
        id=None,
        name="सिता थापा",
        relationship="छोरी",
        phone_number="+9779841000002",
        is_primary_emergency=False,
    )
    mem.add_contact(c1)
    mem.add_contact(c2)

    contacts = mem.list_contacts()
    assert len(contacts) == 2

    primary = mem.get_primary_caregiver()
    assert primary is not None
    assert primary.name == "राम थापा"
    assert primary.phone_number == "+9779841000001"


def test_context_memory_places_and_audit_ledger():
    mem = ContextMemory(":memory:")
    p1 = mem.save_place("बस स्टप", 27.7172, 85.3240, "घर नजिक")
    p2 = mem.save_place("बस स्टप", 27.7172, 85.3240) # Duplicate label updates visit count
    assert p1 == p2

    places = mem.list_places()
    assert len(places) == 1
    assert places[0]["visit_count"] == 2

    # Audit logging with hash chaining
    h1 = mem.log_action(AutonomyLevel.L3_ROUTINE_AUTO, "test.action", "Reason 1", {"k": 1}, "Success")
    h2 = mem.log_action(AutonomyLevel.L4_EMERGENCY, "emergency.test", "Reason 2", {"k": 2}, "Dispatched")

    trail = mem.get_audit_trail(limit=10)
    assert len(trail) == 2
    assert trail[0]["sha256"] == h2
    assert trail[0]["prev_hash"] == h1
    assert trail[1]["sha256"] == h1
    assert trail[1]["prev_hash"] == "0" * 64


# ============================================================================
# 2. CAREGIVER LINK TESTS
# ============================================================================

class MockComms(CommsAdapterInterface):
    def __init__(self):
        self.sent_messages = []

    def send_sms(self, recipient_phone: str, text_message: str) -> bool:
        self.sent_messages.append((recipient_phone, text_message))
        return True

    def is_cellular_available(self) -> bool:
        return True

    def get_signal_quality(self) -> dict:
        return {"csq": 20}


def test_caregiver_link_sms_dispatch():
    mem = ContextMemory(":memory:")
    mem.add_contact(CaregiverContact(
        id=None,
        name="हरि",
        relationship="छोरा",
        phone_number="+9779841112233",
        is_primary_emergency=True,
    ))

    comms = MockComms()
    link = CaregiverLink(memory=mem, comms_adapter=comms, sms_cooldown_seconds=60.0)

    # Dispatch emergency
    res = link.dispatch_emergency(
        alert_title="आकस्मिक सूचना",
        coordinates=(27.71724, 85.32401),
        battery_pct=88.0,
    )
    assert res.success is True
    assert res.recipient_phone == "+9779841112233"
    assert "https://maps.google.com/?q=27.71724,85.32401" in res.message_text
    assert "ब्याट्री 88%" in res.message_text
    assert len(comms.sent_messages) == 1

    # Second dispatch within cooldown is suppressed
    res2 = link.dispatch_emergency(alert_title="दोस्रो सूचना")
    assert res2.success is False
    assert res2.cooldown_suppressed is True
    assert len(comms.sent_messages) == 1


# ============================================================================
# 3. ROUTINE & REMINDER SCHEDULER TESTS
# ============================================================================

def test_routine_scheduler_medication_check():
    mem = ContextMemory(":memory:")
    bus = EventBus()
    events = []
    bus.subscribe(lambda e: events.append(e), category=EventCategory.CARETAKER)

    med_id = mem.add_medication(MedicationItem(
        id=None,
        medicine_name="सिटामोल",
        dosage="५०० मि.ग्रा.",
        timing_type="after_meal",
        time_of_day="09:00",
    ))

    scheduler = RoutineScheduler(memory=mem, event_bus=bus)

    # At 08:50 (within 20m tolerance) -> should be due
    due = scheduler.check_due_medications(current_time_str="08:50", tolerance_minutes=20)
    assert len(due) == 1
    assert due[0].medication_id == med_id
    assert "सिटामोल" in due[0].spoken_prompt_ne
    assert len(events) == 1

    # Snooze for 15 minutes
    scheduler.snooze(med_id, minutes=15)
    due_after_snooze = scheduler.check_due_medications(current_time_str="08:52")
    assert len(due_after_snooze) == 0

    # Acknowledge taken
    assert scheduler.acknowledge_taken(med_id) is True
    due_after_taken = scheduler.check_due_medications(current_time_str="09:00")
    assert len(due_after_taken) == 0


# ============================================================================
# 4. FALL DETECTION & INACTIVITY MONITOR TESTS
# ============================================================================

def test_fall_detector_imu():
    detector = FallDetector(freefall_threshold=4.5, impact_threshold=22.0)

    # 1. Normal gravity (9.8 m/s^2) -> no fall
    assert detector.update_imu(0.0, 0.0, 9.8, timestamp=1.0) is False

    # 2. Free-fall (2.0 m/s^2) -> no fall yet, but primed
    assert detector.update_imu(1.0, 1.0, 1.0, timestamp=1.2) is False

    # 3. Severe impact (24.0 m/s^2) within 1.5s -> FALL DETECTED!
    assert detector.update_imu(10.0, 12.0, 18.0, timestamp=1.5) is True

    # 4. Standalone extreme impact (>28 m/s^2) -> FALL DETECTED!
    assert detector.update_imu(15.0, 20.0, 15.0, timestamp=5.0) is True


def test_fall_detector_visual_flow():
    detector = FallDetector(visual_downward_threshold=40.0)
    # Sudden large downward velocity spike (dy = 55 px)
    assert detector.update_visual_motion(dy=55.0, is_ground_visible=True) is True
    # Minor downward flow (dy = 10 px) -> False
    assert detector.update_visual_motion(dy=10.0, is_ground_visible=True) is False


def test_inactivity_monitor():
    monitor = InactivityMonitor(inactivity_threshold_seconds=100.0, active_hours=(0, 24))
    
    # Check immediately -> False
    is_due, elapsed, _ = monitor.check_inactivity()
    assert is_due is False

    # Fast forward last activity
    monitor._last_activity_timestamp = time.time() - 150.0
    is_due, elapsed, prompt = monitor.check_inactivity()
    assert is_due is True
    assert "कुनै गतिविधि देखिएन" in prompt

    # Record user tap/action -> resets timer
    monitor.record_activity()
    is_due_reset, _, _ = monitor.check_inactivity()
    assert is_due_reset is False


# ============================================================================
# 5. AUTONOMY SUPERVISOR & 10-SECOND EMERGENCY COUNTDOWN TESTS
# ============================================================================

def test_autonomy_emergency_countdown_and_cancellation():
    mem = ContextMemory(":memory:")
    comms = MockComms()
    link = CaregiverLink(memory=mem, comms_adapter=comms)
    bus = EventBus()
    spoken = []

    supervisor = AutonomySupervisor(
        memory=mem,
        caregiver_link=link,
        event_bus=bus,
        speech_callback=lambda text, interrupt: spoken.append(text)
    )

    # Trigger emergency countdown
    state = supervisor.trigger_emergency_countdown(
        incident_type="fall_detected",
        reason="Fall detected on steps",
        duration_seconds=10.0
    )
    assert state.is_active is True
    assert state.remaining_seconds > 8.0
    assert len(spoken) == 1
    assert "१० सेकेन्ड" in spoken[0]

    # User cancels countdown ("म ठीक छु")
    cancelled = supervisor.cancel_emergency(cancel_reason="user_ok")
    assert cancelled is True
    assert state.is_cancelled is True
    assert state.is_active is False
    assert len(comms.sent_messages) == 0  # No SMS sent!


def test_autonomy_emergency_countdown_auto_dispatch():
    mem = ContextMemory(":memory:")
    mem.add_contact(CaregiverContact(
        id=None,
        name="छोरा",
        relationship="छोरा",
        phone_number="+9779849999999",
        is_primary_emergency=True,
    ))
    comms = MockComms()
    link = CaregiverLink(memory=mem, comms_adapter=comms)
    bus = EventBus()
    dispatched_events = []
    bus.subscribe(lambda e: dispatched_events.append(e), event_type=EventType.EMERGENCY_DISPATCH)

    supervisor = AutonomySupervisor(
        memory=mem,
        caregiver_link=link,
        event_bus=bus,
    )

    # Start countdown with 0.1s duration
    supervisor.trigger_emergency_countdown(duration_seconds=0.1)
    time.sleep(0.15) # Wait for timer to expire

    dispatched, state = supervisor.tick_emergency_countdown()
    assert dispatched is True
    assert state.is_dispatched is True
    assert len(comms.sent_messages) == 1
    assert comms.sent_messages[0][0] == "+9779849999999"
    assert len(dispatched_events) == 1
