"""
Unit tests for AssistantDialogueManager and multi-turn conversational scene reasoning.
"""
import os
import sys
from types import SimpleNamespace
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.assistant import AssistantDialogueManager


def make_dummy_detection(class_name: str, sector: str = "center", y_min: float = 0.3, y_max: float = 0.7):
    box = SimpleNamespace(y_min=y_min, y_max=y_max, area=(y_max - y_min) * 0.4)
    return SimpleNamespace(class_name=class_name, sector=sector, box=box, confidence=0.88)


def test_dialogue_manager_empty_observations():
    mgr = AssistantDialogueManager()
    res = mgr.query("वरिपरि के छ?", [])
    assert res["status"] == "uncertain"
    assert "छुट्याउन गाह्रो" in res["text"]
    assert "सुरक्षित" in res["safety_note"]


def test_dialogue_manager_general_scene_observation():
    mgr = AssistantDialogueManager()
    dets = [
        make_dummy_detection("person", "center", 0.1, 0.9),
        make_dummy_detection("chair", "left", 0.4, 0.6),
    ]
    res = mgr.query("के छ?", dets)
    assert res["status"] == "observed"
    assert "मान्छे" in res["text"]
    assert "कुर्सी" in res["text"]


def test_dialogue_manager_sector_filtering():
    mgr = AssistantDialogueManager()
    dets = [
        make_dummy_detection("person", "center", 0.1, 0.9),
        make_dummy_detection("chair", "left", 0.4, 0.6),
    ]
    # Update state
    mgr.query("के छ?", dets)

    # Follow-up: What is on the left?
    res_left = mgr.query("बायाँ के छ?", [])
    assert res_left["status"] == "sector_resolved"
    assert "कुर्सी" in res_left["text"]

    # Follow-up: What is on the right?
    res_right = mgr.query("दायाँ के छ?", [])
    assert res_right["status"] == "clear"


def test_dialogue_manager_repeat_last():
    mgr = AssistantDialogueManager()
    dets = [make_dummy_detection("bottle", "center")]
    res1 = mgr.query("के छ?", dets)
    assert "बोत्तल" in res1["text"]

    res_repeat = mgr.query("फेरि भन्नुहोस्", [])
    assert res_repeat["status"] == "repeated"
    assert "बोत्तल" in res_repeat["text"]


def test_dialogue_manager_currency_memory():
    mgr = AssistantDialogueManager()
    import time
    mgr.update_telemetry(currency={
        "denomination": 500,
        "nepali_text": "पाँच सय",
        "confidence": 0.92,
        "time": time.time(),
    })

    res = mgr.query("पैसा कति हो?", [])
    assert res["status"] == "currency_memory"
    assert "५००" in res["text"] or "500" in res["text"]
