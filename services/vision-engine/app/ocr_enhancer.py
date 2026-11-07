"""
Devanagari OCR Enhancer, Nepali Numeral Parser, and Bus Route Matcher for TRINETRA v2.
Specialized for hand-painted enamel bus hoods, weathered signage, and transit corridors.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np


class NepaliNumeralParser:
    """
    Parses and translates Devanagari digits (०-९) and spoken number phrases.
    """
    DEV_TO_ARABIC = {
        '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
        '५': '5', '६': '6', '७': '7', '८': '8', '९': '9',
    }
    ARABIC_TO_DEV = {v: k for k, v in DEV_TO_ARABIC.items()}

    NEP_WORDS_0_TO_20 = {
        0: "शून्य", 1: "एक", 2: "दुई", 3: "तीन", 4: "चार", 5: "पाँच",
        6: "छ", 7: "सात", 8: "आठ", 9: "नौ", 10: "दस",
        11: "एघार", 12: "बाह्र", 13: "तेह्र", 14: "चौध", 15: "पन्ध्र",
        16: "सोह्र", 17: "सत्र", 18: "अठार", 19: "उन्नाइस", 20: "बीस",
    }

    @classmethod
    def to_arabic_str(cls, devanagari_text: str) -> str:
        """Converts Devanagari digits within text to standard Arabic digits."""
        res = []
        for ch in devanagari_text:
            res.append(cls.DEV_TO_ARABIC.get(ch, ch))
        return "".join(res)

    @classmethod
    def extract_numbers(cls, text: str) -> List[int]:
        """Extracts all numbers (Devanagari or Arabic) found in a text string."""
        normalized = cls.to_arabic_str(text)
        matches = re.findall(r'\b\d+\b', normalized)
        return [int(m) for m in matches]

    @classmethod
    def number_to_spoken_nepali(cls, num: int) -> str:
        """Converts integer into natural spoken Devanagari word."""
        if num in cls.NEP_WORDS_0_TO_20:
            return cls.NEP_WORDS_0_TO_20[num]
        elif num == 100:
            return "एक सय"
        elif num == 1000:
            return "एक हजार"
        # Fallback to digit-by-digit
        digits = str(num)
        return " ".join(cls.NEP_WORDS_0_TO_20.get(int(d), d) for d in digits)


@dataclass
class BusRouteMatch:
    matched: bool
    destination: str
    operator: str
    route_number: Optional[str]
    confidence: float
    spoken_phrase_ne: str


class BusRouteMatcher:
    """
    Matches OCR text against Kathmandu Valley public transit routes and bus boards.
    """

    KNOWN_DESTINATIONS = [
        ("रत्नपार्क", ["रत्नपार्क", "रत्न", "ratnapark", "ratna"]),
        ("लगनखेल", ["लगनखेल", "लगन", "lagankhel", "lagan"]),
        ("कलङ्की", ["कलङ्की", "कलंकी", "kalanki"]),
        ("चाबहिल", ["चाबहिल", "चावहिल", "chabahil"]),
        ("गोङ्गबु नयाँ बसपार्क", ["गोङ्गबु", "गोंगबु", "बसपार्क", "buspark", "gongabu"]),
        ("भक्तपुर", ["भक्तपुर", "bhaktapur", "सूर्यविनायक", "thimi", "थिमी"]),
        ("महाराजगञ्ज", ["महाराजगञ्ज", "महाराजगंज", "maharajgunj", "टिचिङ"]),
        ("कोटेश्वर", ["कोटेश्वर", "koteshwor"]),
        ("बनेपा", ["बनेपा", "धुलिखेल", "banepa", "dhulikhel"]),
        ("स्वयम्भू", ["स्वयम्भू", "स्वयम्भु", "swyambhu"]),
    ]

    KNOWN_OPERATORS = [
        ("साझा यातायात", ["साझा", "sajha"]),
        ("महानगर", ["महानगर", "mahanagar"]),
        ("मयूर यातायात", ["मयूर", "mayur"]),
        ("संयुक्त यातायात", ["संयुक्त"]),
        ("टेम्पो", ["टेम्पो", "tempo"]),
        ("माइक्रो", ["माइक्रो", "micro", "hiace"]),
    ]

    @classmethod
    def match_route(cls, text: str) -> BusRouteMatch:
        text_lower = text.lower()
        matched_dest = ""
        matched_op = ""
        
        # Check destinations
        for canonical, aliases in cls.KNOWN_DESTINATIONS:
            for alias in aliases:
                if alias in text_lower:
                    matched_dest = canonical
                    break
            if matched_dest:
                break

        # Check operators
        for canonical, aliases in cls.KNOWN_OPERATORS:
            for alias in aliases:
                if alias in text_lower:
                    matched_op = canonical
                    break
            if matched_op:
                break

        # Extract bus numbers (e.g., बा ४ ख १२३४ or route number)
        nums = NepaliNumeralParser.extract_numbers(text)
        route_no_str = str(nums[0]) if nums else None

        if matched_dest or matched_op:
            op_part = f"{matched_op} " if matched_op else "गाडी "
            dest_part = f"{matched_dest} जाने" if matched_dest else ""
            route_part = f" नम्बर {route_no_str}" if route_no_str else ""
            spoken = f"अगाडि {dest_part} {op_part}{route_part}भेटियो।".strip()

            return BusRouteMatch(
                matched=True,
                destination=matched_dest,
                operator=matched_op,
                route_number=route_no_str,
                confidence=0.85,
                spoken_phrase_ne=spoken,
            )

        return BusRouteMatch(
            matched=False,
            destination="",
            operator="",
            route_number=None,
            confidence=0.0,
            spoken_phrase_ne="",
        )


class EnamelSignboardPreprocessor:
    """
    Optimizes hand-painted enamel and weathered street signboards for Tesseract Devanagari OCR.
    """

    @staticmethod
    def preprocess_enamel(image_bgr: np.ndarray) -> np.ndarray:
        if image_bgr is None or image_bgr.size == 0:
            return image_bgr

        # Convert to grayscale
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if len(image_bgr.shape) == 3 else image_bgr

        # 1. Bilateral filter removes weathered metal grain while maintaining sharp paint edges
        filtered = cv2.bilateralFilter(gray, 7, 50, 50)

        # 2. CLAHE (Contrast Limited Adaptive Histogram Equalization) overcomes shadow & outdoor glare
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(filtered)

        # 3. Morphological close connects broken Devanagari shirorekha (top bar) strokes
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morph = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, kernel)

        return morph
