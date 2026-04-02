# ChatbotWebsite/chatbot/rewriter.py
from __future__ import annotations

import random
import re

# quick offline keyword topic detection
_TOPIC_RULES = [
    ("doctor", {"doctor", "psychiatrist", "counselor", "therapist", "clinic", "hospital", "consult"}),
    ("sleep", {"sleep", "insomnia", "cant sleep", "no sleep", "restless"}),
    ("stress", {"stress", "stressed", "pressure", "overwhelmed", "burnout"}),
    ("tired", {"tired", "exhausted", "fatigue", "drained"}),
    ("exam", {"exam", "final", "assignment", "deadline", "study", "ioe", "nec"}),
]

_NEpali_slang_map = {
    # helps prevent translation misunderstanding
    "khai": "I don't know",
    "k vako": "what happened",
    "k bhako": "what happened",
    "taha xaina": "I don't know",
    "thaha chaina": "I don't know",
}

def _normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _detect_topic(text_en: str) -> str | None:
    t = _normalize_text(text_en)
    for name, keywords in _TOPIC_RULES:
        for k in keywords:
            if k in t:
                return name
    return None

def _sent_bucket(final_score: float | None, label: str | None) -> str:
    lab = (label or "").lower()
    if final_score is None:
        return lab or "neutral"

    if final_score <= 0.35:
        return "very_negative"
    if final_score <= 0.45:
        return "negative"
    if final_score >= 0.70:
        return "very_positive"
    if final_score >= 0.60:
        return "positive"
    return "neutral"

def _pepper_opening(bucket: str) -> str:
    # small variation in the first line
    bank = {
        "very_negative": [
            "That sounds really heavy.",
            "I’m sorry you’re carrying that right now.",
            "That’s a lot to deal with."
        ],
        "negative": [
            "I hear you.",
            "That sounds tiring.",
            "I’m with you on this."
        ],
        "neutral": [
            "Got it.",
            "Okay, I understand.",
            "Thanks for telling me."
        ],
        "positive": [
            "That’s good to hear.",
            "I’m glad you shared that.",
            "Nice."
        ],
        "very_positive": [
            "That’s really encouraging.",
            "Love that energy.",
            "That’s awesome."
        ],
    }
    return random.choice(bank.get(bucket, bank["neutral"]))

def rewrite_reply_en(
    user_raw: str,
    user_en: str,
    base_reply_en: str,
    sentiment: dict | None = None,
    source: str = "unknown",
) -> tuple[str, str]:
    """
    Returns (rewritten_reply_en, rewrite_tag)
    rewrite_tag can be used for debugging/logging.
    """

    # --- 0) Fix common Nepali slang BEFORE topic detection (safe, offline)
    raw_norm = _normalize_text(user_raw)
    user_en_fixed = user_en
    for k, v in _NEpali_slang_map.items():
        if k in raw_norm:
            # just append hint (don’t overwrite full message)
            user_en_fixed = (user_en_fixed + f" ({v})").strip()
            break

    # --- 1) topic detection
    topic = _detect_topic(user_en_fixed)

    # --- 2) sentiment bucket
    sentiment = sentiment or {}
    bucket = _sent_bucket(sentiment.get("final_score"), sentiment.get("label"))

    # --- 3) If user asked for doctors: don’t hallucinate names, route to your own page
    if topic == "doctor":
        reply = (
            f"{_pepper_opening(bucket)}\n\n"
            "If you want a professional in Nepal, please use the **Psychiatrist Consultation** page in Lumora "
            "so you get verified options.\n"
            "Do you want **psychiatrist**, **counselor/therapist**, or **general doctor**?"
        )
        return reply, "topic_doctor"

    # --- 4) Add small adaptive layer for tired/stress/sleep
    if topic in ("tired", "stress", "sleep"):
        tip_bank = {
            "tired": [
                "Try a 5–10 minute reset: drink water, stretch your neck/shoulders, and take 6 slow breaths.",
                "If you can, a short nap (15–25 minutes) can help without making you groggy.",
                "If this has been going on many days, tell me about your sleep + workload."
            ],
            "stress": [
                "One small step: write the top 1–2 things stressing you, then choose the *next doable action*.",
                "Try box breathing: 4 seconds in, hold 4, out 4, hold 4 (repeat 4 times).",
                "If it’s exam pressure, we can make a simple plan for today."
            ],
            "sleep": [
                "For tonight: avoid caffeine late, dim lights 1 hour before bed, and keep phone away from pillow.",
                "If thoughts keep running, write them down for 2 minutes, then return to breathing slowly.",
                "How many hours did you sleep last night?"
            ],
        }

        opening = _pepper_opening(bucket)

        # Keep base reply but add 1 short actionable line
        tip = random.choice(tip_bank[topic])
        rewritten = f"{opening} {base_reply_en.strip()}\n\nQuick help: {tip}"
        return rewritten, f"topic_{topic}"

    # --- 5) Default: just add a tiny varied opening (doesn’t change meaning)
    opening = _pepper_opening(bucket)
    rewritten = f"{opening} {base_reply_en.strip()}"
    return rewritten, "light_rewrite"
