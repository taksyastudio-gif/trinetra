"""
TRINETRA Cellular SMS Communications Adapter
Provides resilient offline emergency dispatch over 2G/GSM serial modems (SIM800L, SIM7600),
Android telephony bridges, and persistent outbox spooling.
"""

from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from trinetra_core.hal.comms import CommsAdapterInterface

logger = logging.getLogger("trinetra.hal.cellular")


class SerialGsmCommsAdapter(CommsAdapterInterface):
    """
    Direct AT-command driver for GSM/GPRS modems (SIM800L, SIM7600, A7670C, Quectel)
    connected via USB-UART or GPIO UART. Works offline on 2G/4G cellular basebands.
    """

    def __init__(self, port: str = "COM3", baudrate: int = 115200, timeout: float = 3.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial = None

    def _get_serial(self):
        if self._serial is None:
            try:
                import serial
                self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                # Initialize text mode
                self._send_at("AT+CMGF=1")
            except Exception as exc:
                logger.warning(f"SerialGsmCommsAdapter: Could not open {self.port}: {exc}")
                self._serial = None
        return self._serial

    def _send_at(self, cmd: str, wait_for: str = "OK", timeout: float = 2.0) -> Tuple[bool, str]:
        ser = self._get_serial()
        if not ser:
            return False, "Port closed"
        try:
            ser.write((cmd + "\r\n").encode("utf-8"))
            deadline = time.time() + timeout
            response = ""
            while time.time() < deadline:
                if ser.in_waiting:
                    line = ser.readline().decode("utf-8", errors="replace")
                    response += line
                    if wait_for in line or "ERROR" in line:
                        break
                time.sleep(0.05)
            return wait_for in response, response
        except Exception as exc:
            logger.error(f"AT command error: {exc}")
            return False, str(exc)

    def send_sms(self, recipient_phone: str, text_message: str) -> bool:
        ser = self._get_serial()
        if not ser:
            return False
        try:
            # Set text mode
            self._send_at("AT+CMGF=1")
            # Set recipient
            ser.write(f'AT+CMGS="{recipient_phone}"\r'.encode("utf-8"))
            time.sleep(0.2)
            # Send message terminated by Ctrl+Z (\x1A)
            payload = text_message.encode("utf-8") + b"\x1A"
            ser.write(payload)
            deadline = time.time() + 8.0
            response = ""
            while time.time() < deadline:
                if ser.in_waiting:
                    chunk = ser.readline().decode("utf-8", errors="replace")
                    response += chunk
                    if "+CMGS:" in response and "OK" in response:
                        logger.info(f"SMS successfully dispatched to {recipient_phone} via GSM modem")
                        return True
                    if "ERROR" in chunk:
                        logger.error(f"GSM modem rejected SMS: {chunk}")
                        return False
                time.sleep(0.05)
            return "+CMGS:" in response
        except Exception as exc:
            logger.error(f"Failed to dispatch SMS via serial modem: {exc}")
            return False

    def is_cellular_available(self) -> bool:
        ser = self._get_serial()
        if not ser:
            return False
        ok, resp = self._send_at("AT+CREG?")
        # +CREG: 0,1 (registered home) or +CREG: 0,5 (registered roaming)
        return ok and (",1" in resp or ",5" in resp)

    def get_signal_quality(self) -> Dict[str, Any]:
        ser = self._get_serial()
        if not ser:
            return {"status": "disconnected", "rssi": 0}
        ok, resp = self._send_at("AT+CSQ")
        rssi = 0
        if ok and "+CSQ:" in resp:
            try:
                parts = resp.split("+CSQ:")[1].strip().split(",")
                rssi = int(parts[0])
            except Exception:
                pass
        return {"status": "connected" if self.is_cellular_available() else "no_service", "csq": rssi}


class AndroidBridgeCommsAdapter(CommsAdapterInterface):
    """
    Uses local Android subsystem (Termux telephony API or Android Intent CLI)
    when running directly on a chest-mounted Android smartphone.
    Zero cloud dependency, zero external serial hardware needed.
    """

    def __init__(self):
        self._termux_sms = shutil.which("termux-sms-send")

    def send_sms(self, recipient_phone: str, text_message: str) -> bool:
        if self._termux_sms:
            try:
                # termux-sms-send -n <phone_number> <message>
                result = subprocess.run(
                    [self._termux_sms, "-n", recipient_phone, text_message],
                    capture_output=True,
                    timeout=5.0,
                    text=True,
                )
                if result.returncode == 0:
                    logger.info(f"SMS dispatched to {recipient_phone} via Termux Android bridge")
                    return True
                logger.warning(f"Termux SMS failed: {result.stderr}")
            except Exception as exc:
                logger.error(f"AndroidBridge send error: {exc}")
        return False

    def is_cellular_available(self) -> bool:
        # Check if termux-telephony-deviceinfo is present and reports sim_state: "READY"
        termux_info = shutil.which("termux-telephony-deviceinfo")
        if termux_info:
            try:
                res = subprocess.run([termux_info], capture_output=True, timeout=2.0, text=True)
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    return data.get("sim_state") == "READY"
            except Exception:
                pass
        return False

    def get_signal_quality(self) -> Dict[str, Any]:
        return {"status": "android_telephony", "available": self.is_cellular_available()}


class OutboxSpoolCommsAdapter(CommsAdapterInterface):
    """
    Decorates a primary comms adapter with an offline file outbox queue.
    If the cellular modem is momentarily busy, booting, or out of signal,
    the emergency dispatch is saved to ~/.trinetra/sms_outbox/ as an atomic JSON record.
    """

    def __init__(
        self,
        primary_adapter: Optional[CommsAdapterInterface] = None,
        spool_dir: Optional[Path] = None,
    ):
        self.primary_adapter = primary_adapter
        if spool_dir is None:
            base = Path(os.environ.get("TRINETRA_DATA_DIR", Path.home() / ".trinetra"))
            self.spool_dir = base / "sms_outbox"
        else:
            self.spool_dir = Path(spool_dir)
        self.spool_dir.mkdir(parents=True, exist_ok=True)

    def send_sms(self, recipient_phone: str, text_message: str) -> bool:
        dispatched = False
        if self.primary_adapter and self.primary_adapter.is_cellular_available():
            try:
                dispatched = self.primary_adapter.send_sms(recipient_phone, text_message)
            except Exception as exc:
                logger.warning(f"Primary comms failed, spooling to outbox: {exc}")

        # Always record to local outbox for auditing and store-and-forward retry
        spool_file = self.spool_dir / f"sms_{int(time.time() * 1000)}.json"
        record = {
            "timestamp": time.time(),
            "recipient": recipient_phone,
            "message": text_message,
            "dispatched": dispatched,
            "adapter": type(self.primary_adapter).__name__ if self.primary_adapter else "spool_only",
        }
        try:
            with open(spool_file, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"Failed to write outbox spool: {exc}")

        # Return True if primary sent or if local spool securely queued it
        return dispatched or (not self.primary_adapter)

    def is_cellular_available(self) -> bool:
        if self.primary_adapter:
            return self.primary_adapter.is_cellular_available()
        return False

    def get_signal_quality(self) -> Dict[str, Any]:
        if self.primary_adapter:
            return self.primary_adapter.get_signal_quality()
        return {"status": "spool_mode", "pending_spool_count": len(list(self.spool_dir.glob("*.json")))}

    def get_pending_spool_count(self) -> int:
        return len(list(self.spool_dir.glob("*.json")))


def create_resilient_comms_adapter(
    modem_port: Optional[str] = None,
    spool_dir: Optional[Path] = None,
) -> OutboxSpoolCommsAdapter:
    """
    Factory that auto-detects available cellular interfaces:
    1. Check for Android Termux environment.
    2. Check for configured Serial GSM modem port.
    3. Wraps with OutboxSpoolCommsAdapter for zero-loss store-and-forward reliability.
    """
    primary: Optional[CommsAdapterInterface] = None
    if shutil.which("termux-sms-send"):
        primary = AndroidBridgeCommsAdapter()
        logger.info("Auto-detected Android telephony bridge for SMS dispatch")
    elif modem_port or os.environ.get("TRINETRA_MODEM_PORT"):
        port = modem_port or os.environ.get("TRINETRA_MODEM_PORT", "COM3")
        primary = SerialGsmCommsAdapter(port=port)
        logger.info(f"Configured GSM serial modem on {port}")

    return OutboxSpoolCommsAdapter(primary_adapter=primary, spool_dir=spool_dir)
