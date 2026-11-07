"""
Unit tests for TRINETRA v2 Nepal Perception Suite:
- NepalOverheadWireDetector & NepalHazardTaxonomyMapper
- NepaliNumeralParser & BusRouteMatcher
- QRPaymentService (FonePay, eSewa, Khalti, NepalQR)
"""

import os
import sys
import numpy as np
import pytest

# Ensure services/vision-engine is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.detection.nepal_hazards import NepalOverheadWireDetector, NepalHazardTaxonomyMapper
from app.ocr_enhancer import NepaliNumeralParser, BusRouteMatcher, EnamelSignboardPreprocessor
from app.qr_payment import QRPaymentService


# ============================================================================
# 1. NEPAL HAZARDS & OVERHEAD CABLES
# ============================================================================

def test_nepal_overhead_wire_detector():
    detector = NepalOverheadWireDetector()

    # Clean frame
    clean_frame = np.full((300, 400, 3), 200, dtype=np.uint8)
    res_clean = detector.analyze(clean_frame)
    assert res_clean.detected is False

    # Frame with 4 distinct horizontal wire lines in top 35%
    wire_frame = np.full((300, 400, 3), 200, dtype=np.uint8)
    import cv2
    cv2.line(wire_frame, (10, 30), (390, 30), (20, 20, 20), 2)
    cv2.line(wire_frame, (10, 50), (390, 52), (20, 20, 20), 2)
    cv2.line(wire_frame, (10, 70), (390, 70), (20, 20, 20), 2)
    cv2.line(wire_frame, (10, 90), (390, 88), (20, 20, 20), 2)

    res_wire = detector.analyze(wire_frame)
    assert res_wire.detected is True
    assert res_wire.hazard_class == "dangling_wire"
    assert "तार" in res_wire.message_ne


def test_nepal_taxonomy_mapper():
    res_bus = NepalHazardTaxonomyMapper.get_nepali_directive("bus")
    assert res_bus is not None
    assert res_bus[0] == "micro_bus"
    assert "बस" in res_bus[1]

    res_dog = NepalHazardTaxonomyMapper.get_nepali_directive("dog")
    assert res_dog is not None
    assert res_dog[0] == "stray_dog"
    assert "कुकुर" in res_dog[2]

    res_drain = NepalHazardTaxonomyMapper.get_nepali_directive("open_drain")
    assert res_drain is not None
    assert "नाला" in res_drain[1]


# ============================================================================
# 2. NUMERAL PARSER & BUS ROUTE MATCHER
# ============================================================================

def test_nepali_numeral_parser():
    dev_text = "बस नम्बर बा ४ ख १२३४"
    arabic = NepaliNumeralParser.to_arabic_str(dev_text)
    assert "4" in arabic
    assert "1234" in arabic

    nums = NepaliNumeralParser.extract_numbers(dev_text)
    assert 4 in nums
    assert 1234 in nums

    spoken_5 = NepaliNumeralParser.number_to_spoken_nepali(5)
    assert spoken_5 == "पाँच"
    spoken_15 = NepaliNumeralParser.number_to_spoken_nepali(15)
    assert spoken_15 == "पन्ध्र"


def test_bus_route_matcher():
    text1 = "साझा यातायात रत्नपार्क लगनखेल"
    m1 = BusRouteMatcher.match_route(text1)
    assert m1.matched is True
    assert m1.destination == "रत्नपार्क"
    assert m1.operator == "साझा यातायात"
    assert "रत्नपार्क" in m1.spoken_phrase_ne

    text2 = "भक्तपुर जाने द्रुत बस सेवा"
    m2 = BusRouteMatcher.match_route(text2)
    assert m2.matched is True
    assert m2.destination == "भक्तपुर"

    text_unrelated = "यहाँ जुत्ता चप्पल फुकाल्नुहोस्"
    m_none = BusRouteMatcher.match_route(text_unrelated)
    assert m_none.matched is False


def test_enamel_preprocessor():
    dummy = np.full((100, 200, 3), 128, dtype=np.uint8)
    processed = EnamelSignboardPreprocessor.preprocess_enamel(dummy)
    assert processed is not None
    assert processed.shape == (100, 200)


# ============================================================================
# 3. QR PAYMENT SERVICE
# ============================================================================

def test_qr_payment_service():
    service = QRPaymentService()

    # 1. FonePay EMVCo
    fonepay_emvco = "00020101021226320010np.fonepay0114984100000000005204599953035245802NP5916Himalayan Bakery6009Kathmandu6304ABCD"
    res1 = service.parse_payload(fonepay_emvco)
    assert res1.detected is True
    assert res1.scheme == "fonepay"
    assert res1.merchant_name == "Himalayan Bakery"
    assert "फोनपे" in res1.spoken_phrase_ne

    # 2. eSewa URI
    esewa_uri = "esewa://pay?merchantName=Everest+Mart&id=9841234567"
    res2 = service.parse_payload(esewa_uri)
    assert res2.detected is True
    assert res2.scheme == "esewa"
    assert res2.merchant_name == "Everest Mart"
    assert "इसेवा" in res2.spoken_phrase_ne

    # 3. Khalti URI
    khalti_uri = "https://khalti.com/pay/?merchantName=Patan+Books"
    res3 = service.parse_payload(khalti_uri)
    assert res3.detected is True
    assert res3.scheme == "khalti"
    assert res3.merchant_name == "Patan Books"
    assert "खल्ती" in res3.spoken_phrase_ne

    # 4. Empty payload
    res_empty = service.parse_payload("")
    assert res_empty.detected is False
