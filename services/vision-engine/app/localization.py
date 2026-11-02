"""
Trinetra Localization Layer
Maps structured detection events to concise, natural spoken phrases in supported languages.
Keeps object detection and computer vision language-independent.
"""

from enum import Enum
import logging
from typing import Dict, Optional

logger = logging.getLogger("trinetra.localization")


class SupportedLanguage(str, Enum):
    ENGLISH = "en"
    NEPALI = "ne"


DEFAULT_LANGUAGE = SupportedLanguage.NEPALI.value
SUPPORTED_LANGUAGES = [SupportedLanguage.NEPALI.value, SupportedLanguage.ENGLISH.value]


def is_supported_language(lang: Optional[str]) -> bool:
    """Checks whether the given language string corresponds to a supported language."""
    if not lang:
        return False
    norm = lang.strip().lower()
    return norm in ("ne", "nepali", "ne-np", "en", "english", "en-us", "en-gb")


def normalize_language(lang: Optional[str]) -> str:
    """
    Normalizes language aliases into canonical language codes: 'ne' or 'en'.
    Raises ValueError for unsupported language identifiers.
    """
    if not lang:
        return DEFAULT_LANGUAGE
    norm = lang.strip().lower()
    if norm in ("ne", "nepali", "ne-np", "ne_np"):
        return SupportedLanguage.NEPALI.value
    if norm in ("en", "english", "en-us", "en_us", "en-gb", "en_gb"):
        return SupportedLanguage.ENGLISH.value
    raise ValueError(
        f"Unsupported language '{lang}'. Supported language codes: {SUPPORTED_LANGUAGES}"
    )


# Directional sector localization
SECTORS_EN: Dict[str, str] = {
    "left": "left",
    "center": "ahead",
    "ahead": "ahead",
    "right": "right",
}

SECTORS_NE: Dict[str, str] = {
    "left": "बायाँतिर",
    "center": "अगाडि",
    "ahead": "अगाडि",
    "right": "दायाँतिर",
}

# Standard COCO object label mappings for Nepali (Devanagari)
# Concise terms suitable for rapid assistive navigation
COCO_NEPALI_LABELS: Dict[str, str] = {
    "person": "मान्छे",
    "dog": "कुकुर",
    "cat": "बिरालो",
    "car": "गाडी",
    "bicycle": "साइकल",
    "motorcycle": "मोटरसाइकल",
    "bus": "बस",
    "truck": "ट्रक",
    "traffic light": "ट्राफिक बत्ती",
    "stop sign": "रोक संकेत",
    "bench": "बेन्च",
    "chair": "कुर्सी",
    "couch": "सोफा",
    "bed": "ओछ्यान",
    "dining table": "टेबुल",
    "table": "टेबुल",
    "door": "ढोका",
    "stairs": "भर्‍याङ",
    "backpack": "झोला",
    "umbrella": "छाता",
    "handbag": "झोला",
    "bottle": "बोतल",
    "cup": "कप",
    "cell phone": "फोन",
    "laptop": "ल्यापटप",
    "book": "किताब",
    "clock": "घडी",
}


def normalize_sector(sector: str) -> str:
    """Normalizes sector strings to standard keys: left, center, right."""
    s = sector.strip().lower()
    if s in ("center", "ahead", "middle", "front"):
        return "center"
    if s in ("left", "port"):
        return "left"
    if s in ("right", "starboard"):
        return "right"
    return "center"


def format_announcement(
    class_name: str,
    sector: str,
    language: str = DEFAULT_LANGUAGE
) -> str:
    """
    Formats a concise, natural spoken announcement for a detected object and spatial sector.
    
    Examples:
      - person + ahead (ne) -> "अगाडि मान्छे छ।"
      - dog + left (ne)    -> "बायाँतिर कुकुर छ।"
      - car + right (ne)   -> "दायाँतिर गाडी छ।"
      - person + ahead (en) -> "Person, ahead."
      - dog + left (en)     -> "Dog, left."
      - car + right (en)    -> "Car, right."
    """
    norm_sector = normalize_sector(sector)
    clean_class = class_name.strip().lower()
    lang = language.strip().lower()

    if lang == SupportedLanguage.NEPALI.value:
        nepali_sector = SECTORS_NE.get(norm_sector, "अगाडि")
        nepali_label = COCO_NEPALI_LABELS.get(clean_class)
        if nepali_label:
            return f"{nepali_sector} {nepali_label} छ।"
        else:
            # Graceful fallback for unmapped/unknown labels: keep concise Nepali grammar
            return f"{nepali_sector} {clean_class} छ।"
    else:
        # Default: English
        english_sector = SECTORS_EN.get(norm_sector, "ahead")
        return f"{clean_class.capitalize()}, {english_sector}."


def get_announcement_key(
    class_name: str,
    sector: str,
    language: str = DEFAULT_LANGUAGE
) -> str:
    """
    Generates a deterministic deduplication/cooldown key for a structured detection event.
    Keeps rate-limiting isolated per language, label, and spatial sector.
    """
    norm_sector = normalize_sector(sector)
    clean_class = class_name.strip().lower()
    lang = normalize_language(language) if is_supported_language(language) else language.strip().lower()
    return f"{lang}:{clean_class}:{norm_sector}"


def format_crowd_announcement(count: int, language: str = DEFAULT_LANGUAGE) -> str:
    """Formats crowd summary instead of narrating every person individually."""
    lang = normalize_language(language) if is_supported_language(language) else language.strip().lower()
    if lang == SupportedLanguage.NEPALI.value:
        return "अगाडि धेरै मान्छेहरू छन्।"
    return "Crowd ahead."


def format_approaching_announcement(class_name: str, sector: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Formats an approaching object announcement with verified directional movement."""
    norm_sector = normalize_sector(sector)
    clean_class = class_name.strip().lower()
    lang = normalize_language(language) if is_supported_language(language) else language.strip().lower()

    if lang == SupportedLanguage.NEPALI.value:
        nepali_sector = SECTORS_NE.get(norm_sector, "अगाडि")
        nepali_label = COCO_NEPALI_LABELS.get(clean_class, clean_class)
        return f"{nepali_sector} {nepali_label} नजिकिँदै छ।"
    else:
        english_sector = SECTORS_EN.get(norm_sector, "ahead")
        return f"{clean_class.capitalize()} approaching, {english_sector}."


def format_path_advisory(direction: Optional[str], language: str = DEFAULT_LANGUAGE) -> str:
    """
    Formats honest directional path advisory.
    Uses 'appears clear' to honestly distinguish camera estimation from absolute certification.
    """
    lang = normalize_language(language) if is_supported_language(language) else language.strip().lower()
    if direction == "left":
        return "बायाँतिर बाटो खुला देखिन्छ।" if lang == SupportedLanguage.NEPALI.value else "Left path appears clear."
    elif direction == "right":
        return "दायाँतिर बाटो खुला देखिन्छ।" if lang == SupportedLanguage.NEPALI.value else "Right path appears clear."
    elif direction == "ahead":
        return "अगाडि बाटो खुला देखिन्छ।" if lang == SupportedLanguage.NEPALI.value else "Path ahead appears clear."
    else:
        return "अगाडि बाटो अवरुद्ध छ।" if lang == SupportedLanguage.NEPALI.value else "Path blocked ahead."


def format_crossing_announcement(
    class_name: str,
    direction: str,
    language: str = DEFAULT_LANGUAGE
) -> str:
    """
    Formats a spoken announcement for an object crossing the field of view.
    Examples:
      - person + left_to_right (ne) -> "मान्छे दायाँतिर बाटो काट्दै छ।"
      - person + right_to_left (ne) -> "मान्छे बायाँतिर बाटो काट्दै छ।"
      - person + left_to_right (en) -> "Person crossing to the right."
      - person + right_to_left (en) -> "Person crossing to the left."
    """
    clean_class = class_name.strip().lower()
    lang = normalize_language(language) if is_supported_language(language) else language.strip().lower()
    norm_dir = direction.strip().lower()

    if lang == SupportedLanguage.NEPALI.value:
        nepali_label = COCO_NEPALI_LABELS.get(clean_class, clean_class)
        if norm_dir in ("right", "left_to_right"):
            return f"{nepali_label} दायाँतिर बाटो काट्दै छ।"
        else:
            return f"{nepali_label} बायाँतिर बाटो काट्दै छ।"
    else:
        if norm_dir in ("right", "left_to_right"):
            return f"{clean_class.capitalize()} crossing to the right."
        else:
            return f"{clean_class.capitalize()} crossing to the left."


def format_path_intersection_announcement(
    class_name: str,
    direction: Optional[str] = None,
    language: str = DEFAULT_LANGUAGE
) -> str:
    """
    Formats an announcement for an object intersecting the projected walking corridor.
    Conservative wording indicating presence in path rather than guaranteed physical collision.
    Examples:
      - person + left_to_right (ne) -> "मान्छे दायाँतिरबाट बाटोमा आउँदै छ।"
      - person + right_to_left (ne) -> "मान्छे बायाँतिरबाट बाटोमा आउँदै छ।"
      - person + None (ne)          -> "अगाडिको बाटोमा मान्छे आउँदै छ।"
      - person + left_to_right (en) -> "Person crossing into path from left."
      - person + right_to_left (en) -> "Person crossing into path from right."
      - person + None (en)          -> "Person crossing path ahead."
    """
    clean_class = class_name.strip().lower()
    lang = normalize_language(language) if is_supported_language(language) else language.strip().lower()
    norm_dir = direction.strip().lower() if direction else ""

    if lang == SupportedLanguage.NEPALI.value:
        nepali_label = COCO_NEPALI_LABELS.get(clean_class, clean_class)
        if norm_dir in ("left_to_right", "right"):
            return f"{nepali_label} दायाँतिरबाट बाटोमा आउँदै छ।"
        elif norm_dir in ("right_to_left", "left"):
            return f"{nepali_label} बायाँतिरबाट बाटोमा आउँदै छ।"
        else:
            return f"अगाडिको बाटोमा {nepali_label} आउँदै छ।"
    else:
        if norm_dir in ("left_to_right", "right"):
            return f"{clean_class.capitalize()} crossing into path from left."
        elif norm_dir in ("right_to_left", "left"):
            return f"{clean_class.capitalize()} crossing into path from right."
        else:
            return f"{clean_class.capitalize()} crossing path ahead."


def format_moving_away_announcement(
    class_name: str,
    sector: str = "ahead",
    language: str = DEFAULT_LANGUAGE
) -> str:
    """Formats an announcement for an object moving away from the user."""
    norm_sector = normalize_sector(sector)
    clean_class = class_name.strip().lower()
    lang = normalize_language(language) if is_supported_language(language) else language.strip().lower()

    if lang == SupportedLanguage.NEPALI.value:
        nepali_sector = SECTORS_NE.get(norm_sector, "अगाडि")
        nepali_label = COCO_NEPALI_LABELS.get(clean_class, clean_class)
        return f"{nepali_sector} {nepali_label} टाढिँदै छ।"
    else:
        english_sector = SECTORS_EN.get(norm_sector, "ahead")
        return f"{clean_class.capitalize()} moving away, {english_sector}."


def format_parallel_announcement(
    class_name: str,
    sector: str = "left",
    language: str = DEFAULT_LANGUAGE
) -> str:
    """Formats an announcement for an object moving parallel alongside the user."""
    norm_sector = normalize_sector(sector)
    clean_class = class_name.strip().lower()
    lang = normalize_language(language) if is_supported_language(language) else language.strip().lower()

    if lang == SupportedLanguage.NEPALI.value:
        nepali_sector = SECTORS_NE.get(norm_sector, "बायाँतिर")
        nepali_label = COCO_NEPALI_LABELS.get(clean_class, clean_class)
        return f"{nepali_sector} {nepali_label} समानान्तर जाँदै छ।"
    else:
        english_sector = SECTORS_EN.get(norm_sector, "left")
        return f"{clean_class.capitalize()} moving alongside, {english_sector}."


