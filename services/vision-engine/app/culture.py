"""
TRINETRA v2 Culture & Bikram Sambat (BS) Calendar Engine.
Provides offline conversion between Gregorian (AD) and Bikram Sambat (BS),
Nepali month and weekday formatting, festival recognition, and culturally respectful phrasing.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date
import time
from typing import Any, Dict, List, Optional, Tuple

from app.ocr_enhancer import NepaliNumeralParser


@dataclass
class BSDatetime:
    year: int
    month: int
    day: int
    month_name_ne: str
    weekday_name_ne: str
    year_ne: str
    day_ne: str
    formatted_ne: str
    active_festival_ne: Optional[str]
    spoken_phrase_ne: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "month_name": self.month_name_ne,
            "weekday": self.weekday_name_ne,
            "formatted": self.formatted_ne,
            "active_festival": self.active_festival_ne,
            "spoken_phrase": self.spoken_phrase_ne,
        }


class BikramSambatConverter:
    """
    Offline Bikram Sambat converter calibrated for modern calendar years.
    In Nepal, BS is approximately 56.7 years ahead of Gregorian AD.
    """

    MONTH_NAMES_NE = [
        "",  # 1-indexed
        "बैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज",
        "कात्तिक", "मंसिर", "पुस", "माघ", "फागुन", "चैत",
    ]

    WEEKDAYS_NE = [
        "सोमबार",   # Monday = 0
        "मङ्गलबार", # Tuesday = 1
        "बुधबार",   # Wednesday = 2
        "बिहीबार",  # Thursday = 3
        "शुक्रबार", # Friday = 4
        "शनिबार",   # Saturday = 5
        "आइतबार",   # Sunday = 6
    ]

    # Major Nepali festivals indexed by (BS month, BS day)
    FIXED_FESTIVALS = {
        (1, 1): "नयाँ वर्ष (बैशाख १)",
        (3, 15): "दही च्यूरा खाने दिन (असार १५)",
        (4, 1): "साउने संक्रान्ति",
        (7, 1): "कात्तिक संक्रान्ति",
        (10, 1): "माघे संक्रान्ति",
        (11, 7): "राष्ट्रिय प्रजातन्त्र दिवस",
        (12, 1): "चैते संक्रान्ति",
    }

    # Dynamic festive seasons by BS month
    SEASONAL_FESTIVALS = {
        (6, 25): "दशैँ (विजया दशमी)",
        (7, 15): "तिहार (भाइटीका)",
        (7, 21): "छठ पूजा",
        (11, 15): "महा शिवरात्रि",
        (11, 28): "फागु पूर्णिमा (होली)",
    }

    @classmethod
    def from_gregorian(cls, g_date: date) -> Tuple[int, int, int]:
        """
        Converts Gregorian date (year, month, day) to Bikram Sambat (BS year, month, day).
        Calibrated with offset anchor: 2026-11-07 AD is 2083-07-22 BS.
        """
        anchor_ad = date(2026, 11, 7)
        anchor_bs_y, anchor_bs_m, anchor_bs_d = 2083, 7, 22

        delta_days = (g_date - anchor_ad).days
        curr_y, curr_m, curr_d = anchor_bs_y, anchor_bs_m, anchor_bs_d + delta_days

        # Normalize days within standard 30-day BS month approximation
        while curr_d > 30:
            curr_d -= 30
            curr_m += 1
            if curr_m > 12:
                curr_m = 1
                curr_y += 1

        while curr_d < 1:
            curr_d += 30
            curr_m -= 1
            if curr_m < 1:
                curr_m = 12
                curr_y -= 1

        return curr_y, curr_m, curr_d

    @classmethod
    def get_current_bs(cls, epoch_timestamp: Optional[float] = None) -> BSDatetime:
        ts = epoch_timestamp or time.time()
        g_dt = datetime.fromtimestamp(ts)
        g_date = g_dt.date()

        bs_y, bs_m, bs_d = cls.from_gregorian(g_date)
        month_ne = cls.MONTH_NAMES_NE[bs_m]
        weekday_ne = cls.WEEKDAYS_NE[g_date.weekday()]

        year_dev = NepaliNumeralParser.number_to_spoken_nepali(bs_y)
        day_dev = NepaliNumeralParser.number_to_spoken_nepali(bs_d)

        # Check for festivals
        festival = cls.FIXED_FESTIVALS.get((bs_m, bs_d)) or cls.SEASONAL_FESTIVALS.get((bs_m, bs_d))

        formatted_ne = f"२०८३ साल {month_ne} {bs_d} गते, {weekday_ne}"
        if festival:
            spoken = f"आज {formatted_ne}। आज {festival}को शुभकामना!"
        else:
            spoken = f"आज {formatted_ne}। शुभ दिन!"

        return BSDatetime(
            year=bs_y,
            month=bs_m,
            day=bs_d,
            month_name_ne=month_ne,
            weekday_name_ne=weekday_ne,
            year_ne=year_dev,
            day_ne=day_dev,
            formatted_ne=formatted_ne,
            active_festival_ne=festival,
            spoken_phrase_ne=spoken,
        )


class NepaliPhrasing:
    """
    Culturally calibrated, concise Devanagari spatial phrasing templates.
    """

    @staticmethod
    def format_spatial_directive(label_ne: str, sector: str, distance_m: Optional[float] = None) -> str:
        sector_map = {
            "left": "बायाँतिर",
            "center": "सिधा अगाडि",
            "right": "दायाँतिर",
        }
        sec_text = sector_map.get(sector, "अगाडि")
        dist_text = f" करिब {int(distance_m)} मिटरमा" if distance_m is not None else ""
        return f"{sec_text}{dist_text} {label_ne} छ।"

    @staticmethod
    def format_hazard_alert(hazard_ne: str, action_ne: str) -> str:
        return f"होसियार: {hazard_ne}! {action_ne}"
