"""
Routine and Medication Reminder Scheduler for TRINETRA v2 Caretaker.
Tracks daily schedules, meal timing, and emits respectful Nepali prompts.
"""

from __future__ import annotations
from dataclasses import dataclass
import time
from typing import Any, Dict, List, Optional
from trinetra_core.caretaker.memory import ContextMemory, MedicationItem
from trinetra_core.events.bus import EventBus
from trinetra_core.events.schema import Event, EventCategory, EventPriority, EventType


@dataclass
class ReminderPrompt:
    medication_id: int
    medicine_name: str
    dosage: str
    timing_type: str
    spoken_prompt_ne: str
    scheduled_time: str


class RoutineScheduler:
    """
    Manages periodic routine checks and medication reminder generation.
    """

    def __init__(self, memory: ContextMemory, event_bus: Optional[EventBus] = None):
        self.memory = memory
        self.event_bus = event_bus
        self._snoozed_until: Dict[int, float] = {}

    def format_nepali_prompt(self, med: MedicationItem) -> str:
        timing_map = {
            "before_meal": "खाना खानुअघि",
            "after_meal": "खाना खाएपछि",
            "fixed_time": "नियमित समयमा",
        }
        timing_text = timing_map.get(med.timing_type, "खानापछि")
        return f"हजुर, औषधिको समय भयो: {med.medicine_name}, {med.dosage}, {timing_text}।"

    def check_due_medications(
        self,
        current_time_str: Optional[str] = None,
        tolerance_minutes: int = 20,
    ) -> List[ReminderPrompt]:
        """
        Scans active medications to find any due right now that haven't been taken today.
        current_time_str format: "HH:MM" in 24hr format.
        """
        now = time.localtime()
        if not current_time_str:
            current_time_str = f"{now.tm_hour:02d}:{now.tm_min:02d}"

        curr_hour, curr_min = map(int, current_time_str.split(":"))
        curr_total_mins = curr_hour * 60 + curr_min
        today_date_str = time.strftime("%Y-%m-%d", now)

        due_prompts: List[ReminderPrompt] = []
        meds = self.memory.list_medications(active_only=True)

        for med in meds:
            if med.id is None:
                continue

            # Check if snoozed
            if med.id in self._snoozed_until and time.time() < self._snoozed_until[med.id]:
                continue

            # Check if already taken today
            if med.last_taken_utc and med.last_taken_utc.startswith(today_date_str):
                continue

            try:
                med_hour, med_min = map(int, med.time_of_day.split(":"))
                med_total_mins = med_hour * 60 + med_min
                diff = abs(curr_total_mins - med_total_mins)

                if diff <= tolerance_minutes:
                    prompt_ne = self.format_nepali_prompt(med)
                    due_prompts.append(ReminderPrompt(
                        medication_id=med.id,
                        medicine_name=med.medicine_name,
                        dosage=med.dosage,
                        timing_type=med.timing_type,
                        spoken_prompt_ne=prompt_ne,
                        scheduled_time=med.time_of_day,
                    ))

                    # Emit event if bus connected
                    if self.event_bus:
                        self.event_bus.publish(Event(
                            event_type=EventType.MEDICATION_DUE,
                            category=EventCategory.CARETAKER,
                            priority=EventPriority.NORMAL,
                            payload={
                                "medication_id": med.id,
                                "medicine_name": med.medicine_name,
                                "prompt": prompt_ne,
                                "scheduled_time": med.time_of_day,
                            }
                        ))
            except Exception:
                continue

        return due_prompts

    def snooze(self, med_id: int, minutes: int = 10) -> None:
        """Snoozes a medication prompt for N minutes."""
        self._snoozed_until[med_id] = time.time() + (minutes * 60)

    def acknowledge_taken(self, med_id: int) -> bool:
        """Marks medication as taken for today and removes any snooze."""
        self._snoozed_until.pop(med_id, None)
        return self.memory.mark_medication_taken(med_id)
