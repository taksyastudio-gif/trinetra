"""
Unit tests for Trinetra Localization Layer.
Validates mapping of structured detection events to natural Nepali (Devanagari)
and English phrases, sector normalization, unmapped label handling, and cooldown keys.
"""

import pytest
from app.localization import (
    SupportedLanguage,
    format_announcement,
    format_crossing_announcement,
    format_moving_away_announcement,
    format_parallel_announcement,
    format_path_intersection_announcement,
    get_announcement_key,
    normalize_sector,
)


def test_nepali_canonical_examples():
    """Validates the exact canonical examples required for Nepali assistive vision."""
    # 1. person + ahead -> "अगाडि मान्छे छ।"
    assert format_announcement("person", "ahead", language="ne") == "अगाडि मान्छे छ।"
    assert format_announcement("person", "center", language="ne") == "अगाडि मान्छे छ।"

    # 2. dog + left -> "बायाँतिर कुकुर छ।"
    assert format_announcement("dog", "left", language="ne") == "बायाँतिर कुकुर छ।"

    # 3. car + right -> "दायाँतिर गाडी छ।"
    assert format_announcement("car", "right", language="ne") == "दायाँतिर गाडी छ।"


def test_english_canonical_examples():
    """Validates English output formatting for standard spatial detections."""
    assert format_announcement("person", "ahead", language="en") == "Person, ahead."
    assert format_announcement("person", "center", language="en") == "Person, ahead."
    assert format_announcement("dog", "left", language="en") == "Dog, left."
    assert format_announcement("car", "right", language="en") == "Car, right."


def test_unmapped_labels_handled_gracefully():
    """Validates that unknown/unmapped classes are formatted cleanly without crashing."""
    # Nepali with unmapped class
    assert format_announcement("unknown_obstacle", "ahead", language="ne") == "अगाडि unknown_obstacle छ।"
    assert format_announcement("fire hydrant", "left", language="ne") == "बायाँतिर ट्राफिक बत्ती छ।" or "fire hydrant" in format_announcement("fire hydrant", "left", language="ne")

    # English with unknown class
    assert format_announcement("unknown_obstacle", "left", language="en") == "Unknown_obstacle, left."


def test_sector_normalization():
    """Verifies sector synonyms normalize properly."""
    assert normalize_sector("ahead") == "center"
    assert normalize_sector("center") == "center"
    assert normalize_sector("front") == "center"
    assert normalize_sector("left") == "left"
    assert normalize_sector("right") == "right"
    assert normalize_sector("  LEFT  ") == "left"


def test_announcement_keys_are_unique_and_consistent():
    """Verifies that cooldown keys isolate language, class, and sector."""
    k_ne = get_announcement_key("dog", "left", language="ne")
    k_en = get_announcement_key("dog", "left", language="en")
    k_ne_right = get_announcement_key("dog", "right", language="ne")

    assert k_ne == "ne:dog:left"
    assert k_en == "en:dog:left"
    assert k_ne != k_en
    assert k_ne != k_ne_right


def test_crossing_and_path_intersection_localization():
    """Validates bilingual formatting for crossing, path intersection, moving away, and parallel events."""
    # Crossing
    assert format_crossing_announcement("person", "left_to_right", language="ne") == "मान्छे दायाँतिर बाटो काट्दै छ।"
    assert format_crossing_announcement("person", "right_to_left", language="ne") == "मान्छे बायाँतिर बाटो काट्दै छ।"
    assert format_crossing_announcement("person", "left_to_right", language="en") == "Person crossing to the right."
    assert format_crossing_announcement("person", "right_to_left", language="en") == "Person crossing to the left."

    # Path intersection
    assert format_path_intersection_announcement("person", "left_to_right", language="ne") == "मान्छे दायाँतिरबाट बाटोमा आउँदै छ।"
    assert format_path_intersection_announcement("person", "right_to_left", language="ne") == "मान्छे बायाँतिरबाट बाटोमा आउँदै छ।"
    assert format_path_intersection_announcement("person", None, language="ne") == "अगाडिको बाटोमा मान्छे आउँदै छ।"
    assert format_path_intersection_announcement("person", "left_to_right", language="en") == "Person crossing into path from left."
    assert format_path_intersection_announcement("person", None, language="en") == "Person crossing path ahead."

    # Moving away
    assert format_moving_away_announcement("person", "ahead", language="ne") == "अगाडि मान्छे टाढिँदै छ।"
    assert format_moving_away_announcement("car", "right", language="en") == "Car moving away, right."

    # Parallel
    assert format_parallel_announcement("person", "left", language="ne") == "बायाँतिर मान्छे समानान्तर जाँदै छ।"
    assert format_parallel_announcement("person", "left", language="en") == "Person moving alongside, left."

