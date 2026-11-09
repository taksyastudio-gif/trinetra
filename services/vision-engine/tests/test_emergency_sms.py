"""
Tests for TRINETRA Offline Caretaker SMS Emergency Dispatch
Verifies zero-cloud cellular dispatch, AT-command formatting,
Android bridge integration, and offline outbox spooling.
"""

import json
from pathlib import Path
import tempfile
import time
from unittest.mock import MagicMock

from trinetra_core.caretaker.caregiver import CaregiverLink
from trinetra_core.caretaker.memory import CaregiverContact, ContextMemory
from trinetra_core.caretaker.autonomy import AutonomySupervisor
from trinetra_core.hal.cellular_sms import (
    AndroidBridgeCommsAdapter,
    OutboxSpoolCommsAdapter,
    SerialGsmCommsAdapter,
    create_resilient_comms_adapter,
)


def test_serial_gsm_sms_formatting():
    """Verifies AT command sequences on a mock serial port."""
    mock_serial = MagicMock()
    mock_serial.in_waiting = 1
    mock_serial.readline.side_effect = [b"OK\r\n", b"+CMGS: 42\r\n", b"OK\r\n", b""]

    adapter = SerialGsmCommsAdapter(port="COM99")
    adapter._serial = mock_serial

    success = adapter.send_sms("+9779800000000", "[त्रिनेत्र] आपतकालीन सहयोग आवश्यक छ!")
    assert success is True
    # Verify AT+CMGS and Ctrl+Z (\x1A) was transmitted
    written_data = b"".join(call.args[0] for call in mock_serial.write.call_args_list)
    assert b'AT+CMGS="+9779800000000"' in written_data
    assert b"\x1A" in written_data


def test_outbox_spool_persists_offline():
    """Verifies that an emergency SMS is reliably queued in outbox when offline."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        spool_dir = Path(tmp_dir) / "spool"
        adapter = OutboxSpoolCommsAdapter(primary_adapter=None, spool_dir=spool_dir)

        phone = "+9779841234567"
        text = "[त्रिनेत्र आपतकालीन] हजुर: लड्नुभएको शंका। स्थान: https://maps.google.com/?q=27.71720,85.32400"

        ok = adapter.send_sms(phone, text)
        assert ok is True
        assert adapter.get_pending_spool_count() == 1

        spool_files = list(spool_dir.glob("*.json"))
        assert len(spool_files) == 1

        with open(spool_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["recipient"] == phone
        assert data["message"] == text
        assert "timestamp" in data


def test_caregiver_link_full_emergency_dispatch():
    """Verifies end-to-end CaregiverLink -> CommsAdapter dispatch during countdown expiry."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "test_caretaker.db")
        memory = ContextMemory(db_path=db_path)
        try:
            # Register a primary caregiver contact
            memory.add_contact(
                CaregiverContact(
                    id=None,
                    name="Aama",
                    relationship="Mother",
                    phone_number="+9779811223344",
                    is_primary_emergency=True,
                    consent_granted=True,
                )
            )

            spool_dir = Path(tmp_dir) / "sms_outbox"
            adapter = create_resilient_comms_adapter(spool_dir=spool_dir)
            link = CaregiverLink(memory=memory, comms_adapter=adapter, sms_cooldown_seconds=1.0)

            # Dispatch emergency
            result = link.dispatch_emergency(
                alert_title="आकस्मिक सूचना (लड्नुभएको शंका)",
                coordinates=(27.7172, 85.3240),
                battery_pct=85.0,
                user_name="हजुर",
                force=True,
            )

            assert result.success is True
            assert result.recipient_phone == "+9779811223344"
            assert "maps.google.com" in result.message_text
            assert "ब्याट्री 85%" in result.message_text
            assert adapter.get_pending_spool_count() == 1
        finally:
            memory.close()


def test_autonomy_countdown_triggers_sms_dispatch():
    """Verifies that 10s countdown expiry invokes CaregiverLink.dispatch_emergency."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "test_caretaker2.db")
        memory = ContextMemory(db_path=db_path)
        try:
            memory.add_contact(
                CaregiverContact(
                    id=None,
                    name="Dai",
                    relationship="Brother",
                    phone_number="+9779855667788",
                    is_primary_emergency=True,
                    consent_granted=True,
                )
            )

            spool_dir = Path(tmp_dir) / "sms_outbox"
            adapter = create_resilient_comms_adapter(spool_dir=spool_dir)
            link = CaregiverLink(memory=memory, comms_adapter=adapter)
            supervisor = AutonomySupervisor(memory=memory, caregiver_link=link)

            # Trigger emergency with 0.1s countdown for fast testing
            state = supervisor.trigger_emergency_countdown(
                incident_type="fall_detected",
                reason="High impact acceleration detected",
                coordinates=(27.7000, 85.3000),
                duration_seconds=0.1,
            )
            assert state.is_active is True

            # Wait for timer expiration
            time.sleep(0.15)

            dispatched_now, final_state = supervisor.tick_emergency_countdown()
            assert dispatched_now is True
            assert final_state.is_dispatched is True
            assert final_state.dispatch_result is not None
            assert final_state.dispatch_result.success is True
            assert adapter.get_pending_spool_count() == 1
        finally:
            memory.close()
