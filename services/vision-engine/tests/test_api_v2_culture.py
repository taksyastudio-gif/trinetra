"""
Phase 4 Integration Tests: REST Endpoints for Culture, Speech Rate, and Conversational Chat.
"""
import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_api_culture_date(client):
    response = client.get("/api/culture/date")
    assert response.status_code == 200
    data = response.json()
    assert "year" in data
    assert "month" in data
    assert "month_name" in data
    assert "weekday" in data
    assert "formatted" in data
    assert "spoken_phrase" in data
    assert data["year"] == 2083


def test_api_speech_rate_get_and_set(client):
    # Initial rate
    get_res = client.get("/api/speech/rate")
    assert get_res.status_code == 200
    assert "rate" in get_res.json()

    # Set rate to 1.25x
    post_res = client.post("/api/speech/rate", json={"rate": 1.25})
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "ok"
    assert post_res.json()["rate"] == 1.25

    # Verify updated rate
    get_res2 = client.get("/api/speech/rate")
    assert get_res2.status_code == 200
    assert get_res2.json()["rate"] == 1.25


def test_api_assistant_chat_cultural_date(client):
    # Conversational chat asking for date in mixed English/Romanized
    res = client.post("/api/assistant/chat", json={
        "message": "aaja ko date k ho?",
        "speak": False
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "cultural_calendar"
    assert "२०८३" in data["text"] or "2083" in data["text"]
    assert "calendar" in data


def test_api_assistant_chat_emergency(client):
    res = client.post("/api/assistant/chat", json={
        "message": "emergency help me",
        "speak": False
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "emergency_guidance"
    assert "१००" in data["text"] or "100" in data["text"]
    assert "१०२" in data["text"] or "102" in data["text"]


def test_api_assistant_chat_lost_guidance(client):
    res = client.post("/api/assistant/chat", json={
        "message": "म हराएँ मलाई बाटो देखाउनुहोस्",
        "speak": False
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "lost_guidance"
    assert "नआत्तिनुहोस्" in data["text"]
