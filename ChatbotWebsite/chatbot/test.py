from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

# ----------------------------
# Load tests.json safely (works regardless of working directory)
# This file lives at: ChatbotWebsite/chatbot/test.py
# tests.json lives at: ChatbotWebsite/static/data/tests.json
# ----------------------------
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_TESTS_JSON = os.path.normpath(os.path.join(_BASE_DIR, "..", "static", "data", "tests.json"))

with open(_TESTS_JSON, "r", encoding="utf-8") as file:
    tests: Dict[str, Any] = json.load(file)


def _norm(s: str) -> str:
    """Normalize titles/keys so small formatting differences don't break lookups."""
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("-", "").replace("_", "")
    return s


# ----------------------------
# Get test questions
# ----------------------------
def get_questions(title: str) -> List[Dict[str, Any]]:
    """Return a list of question dicts; returns [] when not found."""
    key = _norm(title)
    for test in (tests.get("tests") or []):
        if _norm(test.get("title", "")) == key:
            return list(test.get("questions") or [])
    return []


# ----------------------------
# Helpers for scoring/safety
# ----------------------------
def _phq9_band(score: int) -> str:
    # PHQ-9 total 0–27
    if score >= 20:
        return "Severe"
    if score >= 15:
        return "Moderately Severe"
    if score >= 10:
        return "Moderate"
    if score >= 5:
        return "Mild"
    return "Minimal"


def _gad7_band(score: int) -> str:
    # GAD-7 total 0–21
    if score >= 15:
        return "Severe"
    if score >= 10:
        return "Moderate"
    if score >= 5:
        return "Mild"
    return "Minimal"


def needs_immediate_danger_check(title: str, score) -> bool:
    """True when we should ask the user about immediate danger (high depression score)."""
    try:
        s = int(score)
    except Exception:
        return False
    t = _norm(title)
    return ("depression" in t) and (s >= 20)


# ----------------------------
# Get test score message
# ----------------------------
def get_test_messages(title: str, score) -> str:
    score = int(score)
    t = _norm(title)

    if "depression" in t:
        band = _phq9_band(score)
        message = f"Depression Test: {band} Depression - Score: {score}/27"

        # Add urgent wording only for severe scores
        if score >= 20:
            message += (
                ". Your score is quite high. If you feel you may harm yourself or are in immediate danger, "
                "please use the SOS button (top right) for urgent support options."
            )
        else:
            message += "."

    elif "anxiety" in t:
        band = _gad7_band(score)
        message = f"Anxiety Test: {band} Anxiety - Score: {score}/21."

    else:
        message = "Test title not found."

    message += (
        " These results are not meant to be a diagnosis. If you're concerned, consider speaking with a qualified "
        "doctor or therapist. Sharing these results with someone you trust can be a helpful first step."
    )
    return message
