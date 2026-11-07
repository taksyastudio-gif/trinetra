"""
Local SQLite Context Memory for TRINETRA v2 Caretaker.
Stores routines, medications, emergency contacts, frequent locations,
and tamper-evident action audit logs with zero cloud leakage.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from trinetra_core.types import AutonomyLevel


@dataclass
class MedicationItem:
    id: Optional[int]
    medicine_name: str
    dosage: str
    timing_type: str                   # "before_meal", "after_meal", "fixed_time"
    time_of_day: str                   # "HH:MM" 24hr format, e.g. "08:00"
    days_of_week: str = "daily"
    is_active: bool = True
    last_taken_utc: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "medicine_name": self.medicine_name,
            "dosage": self.dosage,
            "timing_type": self.timing_type,
            "time_of_day": self.time_of_day,
            "days_of_week": self.days_of_week,
            "is_active": self.is_active,
            "last_taken_utc": self.last_taken_utc,
            "notes": self.notes,
        }


@dataclass
class CaregiverContact:
    id: Optional[int]
    name: str
    relationship: str                  # e.g., "छोरा" (son), "छोरी" (daughter), "छिमेकी" (neighbor)
    phone_number: str                  # E.164 or Nepal 10-digit mobile, e.g., "+9779841000000"
    is_primary_emergency: bool = False
    consent_granted: bool = True
    created_at_utc: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "relationship": self.relationship,
            "phone_number": self.phone_number,
            "is_primary_emergency": self.is_primary_emergency,
            "consent_granted": self.consent_granted,
            "created_at_utc": self.created_at_utc,
        }


class ContextMemory:
    """
    Thread-safe local SQLite context repository for TRINETRA v2.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._last_audit_hash = "0" * 64
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            
            # 1. Preferences & User State
            cur.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # 2. Frequent Places / Bookmarks
            cur.execute("""
                CREATE TABLE IF NOT EXISTS places (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    visit_count INTEGER DEFAULT 1,
                    last_visited_utc TEXT,
                    notes TEXT
                )
            """)

            # 3. Contacts / Caregivers
            cur.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    relationship TEXT,
                    phone_number TEXT NOT NULL,
                    is_primary_emergency INTEGER DEFAULT 0,
                    consent_granted INTEGER DEFAULT 1,
                    created_at_utc REAL
                )
            """)

            # 4. Medication Schedules
            cur.execute("""
                CREATE TABLE IF NOT EXISTS medications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medicine_name TEXT NOT NULL,
                    dosage TEXT NOT NULL,
                    timing_type TEXT DEFAULT 'after_meal',
                    time_of_day TEXT NOT NULL,
                    days_of_week TEXT DEFAULT 'daily',
                    is_active INTEGER DEFAULT 1,
                    last_taken_utc TEXT,
                    notes TEXT
                )
            """)

            # 5. Tamper-Evident Action Audit Log (SHA-256 chained)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc REAL NOT NULL,
                    autonomy_level INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    reason TEXT,
                    inputs_json TEXT,
                    outcome TEXT,
                    prev_hash TEXT NOT NULL,
                    sha256 TEXT NOT NULL
                )
            """)

            # Get latest audit hash if exists
            cur.execute("SELECT sha256 FROM audit_log ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                self._last_audit_hash = row["sha256"]

            self._conn.commit()

    # --- Preferences & Autonomy Settings ---

    def set_preference(self, key: str, value: Any) -> None:
        val_str = json.dumps(value) if not isinstance(value, str) else value
        with self._lock:
            self._conn.execute(
                "INSERT INTO preferences (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
                (key, val_str, val_str)
            )
            self._conn.commit()

    def get_preference(self, key: str, default: Any = None) -> Any:
        with self._lock:
            cur = self._conn.execute("SELECT value FROM preferences WHERE key = ?", (key,))
            row = cur.fetchone()
            if not row:
                return default
            val = row["value"]
            try:
                return json.loads(val)
            except Exception:
                return val

    def get_autonomy_level(self) -> AutonomyLevel:
        lvl = self.get_preference("autonomy_level", int(AutonomyLevel.L2_ACT_CONFIRMED))
        try:
            return AutonomyLevel(int(lvl))
        except ValueError:
            return AutonomyLevel.L2_ACT_CONFIRMED

    def set_autonomy_level(self, level: AutonomyLevel) -> None:
        self.set_preference("autonomy_level", int(level))

    # --- Medication Management ---

    def add_medication(self, med: MedicationItem) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO medications 
                   (medicine_name, dosage, timing_type, time_of_day, days_of_week, is_active, last_taken_utc, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (med.medicine_name, med.dosage, med.timing_type, med.time_of_day,
                 med.days_of_week, 1 if med.is_active else 0, med.last_taken_utc, med.notes)
            )
            self._conn.commit()
            return cur.lastrowid

    def list_medications(self, active_only: bool = True) -> List[MedicationItem]:
        with self._lock:
            query = "SELECT * FROM medications"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY time_of_day ASC"
            rows = self._conn.execute(query).fetchall()
            return [
                MedicationItem(
                    id=row["id"],
                    medicine_name=row["medicine_name"],
                    dosage=row["dosage"],
                    timing_type=row["timing_type"],
                    time_of_day=row["time_of_day"],
                    days_of_week=row["days_of_week"],
                    is_active=bool(row["is_active"]),
                    last_taken_utc=row["last_taken_utc"],
                    notes=row["notes"] or "",
                )
                for row in rows
            ]

    def mark_medication_taken(self, med_id: int) -> bool:
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            cur = self._conn.execute(
                "UPDATE medications SET last_taken_utc = ? WHERE id = ?",
                (now_iso, med_id)
            )
            self._conn.commit()
            return cur.rowcount > 0

    # --- Caregiver Contacts ---

    def add_contact(self, contact: CaregiverContact) -> int:
        with self._lock:
            if contact.is_primary_emergency:
                # Clear existing primary emergency flags
                self._conn.execute("UPDATE contacts SET is_primary_emergency = 0")
            cur = self._conn.execute(
                """INSERT INTO contacts 
                   (name, relationship, phone_number, is_primary_emergency, consent_granted, created_at_utc)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (contact.name, contact.relationship, contact.phone_number,
                 1 if contact.is_primary_emergency else 0, 1 if contact.consent_granted else 0, contact.created_at_utc)
            )
            self._conn.commit()
            return cur.lastrowid

    def list_contacts(self) -> List[CaregiverContact]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM contacts ORDER BY is_primary_emergency DESC, id ASC").fetchall()
            return [
                CaregiverContact(
                    id=row["id"],
                    name=row["name"],
                    relationship=row["relationship"],
                    phone_number=row["phone_number"],
                    is_primary_emergency=bool(row["is_primary_emergency"]),
                    consent_granted=bool(row["consent_granted"]),
                    created_at_utc=row["created_at_utc"],
                )
                for row in rows
            ]

    def get_primary_caregiver(self) -> Optional[CaregiverContact]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM contacts WHERE is_primary_emergency = 1 AND consent_granted = 1 LIMIT 1"
            ).fetchone()
            if not row:
                # Fallback to first consented contact
                row = self._conn.execute(
                    "SELECT * FROM contacts WHERE consent_granted = 1 LIMIT 1"
                ).fetchone()
            if not row:
                return None
            return CaregiverContact(
                id=row["id"],
                name=row["name"],
                relationship=row["relationship"],
                phone_number=row["phone_number"],
                is_primary_emergency=bool(row["is_primary_emergency"]),
                consent_granted=bool(row["consent_granted"]),
                created_at_utc=row["created_at_utc"],
            )

    # --- Frequent Places / Waypoints ---

    def save_place(self, label: str, lat: Optional[float], lon: Optional[float], notes: str = "") -> int:
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            # Check if place with exact label exists
            cur = self._conn.execute("SELECT id, visit_count FROM places WHERE label = ?", (label,))
            existing = cur.fetchone()
            if existing:
                place_id = existing["id"]
                new_count = existing["visit_count"] + 1
                self._conn.execute(
                    "UPDATE places SET visit_count = ?, last_visited_utc = ?, latitude = COALESCE(?, latitude), longitude = COALESCE(?, longitude) WHERE id = ?",
                    (new_count, now_iso, lat, lon, place_id)
                )
                self._conn.commit()
                return place_id
            else:
                res = self._conn.execute(
                    "INSERT INTO places (label, latitude, longitude, visit_count, last_visited_utc, notes) VALUES (?, ?, ?, 1, ?, ?)",
                    (label, lat, lon, now_iso, notes)
                )
                self._conn.commit()
                return res.lastrowid

    def list_places(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM places ORDER BY visit_count DESC, id ASC").fetchall()
            return [dict(r) for r in rows]

    # --- Tamper-Evident Action Audit Ledger ---

    def log_action(
        self,
        autonomy_level: AutonomyLevel,
        event_type: str,
        reason: str,
        inputs: Dict[str, Any],
        outcome: str,
    ) -> str:
        """
        Records an autonomous or emergency decision into an append-only SHA-256 chained log.
        Returns the SHA-256 fingerprint of the record.
        """
        now_ts = time.time()
        inputs_str = json.dumps(inputs, sort_keys=True)
        with self._lock:
            prev_hash = self._last_audit_hash
            raw_payload = f"{now_ts}|{int(autonomy_level)}|{event_type}|{reason}|{inputs_str}|{outcome}|{prev_hash}"
            record_hash = hashlib.sha256(raw_payload.encode('utf-8')).hexdigest()

            self._conn.execute(
                """INSERT INTO audit_log 
                   (timestamp_utc, autonomy_level, event_type, reason, inputs_json, outcome, prev_hash, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (now_ts, int(autonomy_level), event_type, reason, inputs_str, outcome, prev_hash, record_hash)
            )
            self._conn.commit()
            self._last_audit_hash = record_hash
            return record_hash

    def get_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
