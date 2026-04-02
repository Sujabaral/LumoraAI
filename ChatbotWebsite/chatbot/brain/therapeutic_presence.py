# ChatbotWebsite/chatbot/brain/therapeutic_presence.py
from __future__ import annotations

import random
import re
from typing import Optional, Dict, Any

# Supported modes:
# auto, listener, coach, therapist, balanced
MODES = ("auto", "listener", "coach", "therapist", "balanced")

_UNSURE_RE = re.compile(
    r"^(i\s*can't|i\s*cant|cant|can't|idk|i\s*don't\s*know|i\s*dont\s*know|not\s*sure)\s*[.!?]*$",
    re.IGNORECASE,
)

_SHORT_ACK_RE = re.compile(r"^(ok|okay|k|hm|hmm|alright|fine|sure)\s*[.!?]*$", re.IGNORECASE)

# Openers — short, natural, non-repetitive (removed “I’m glad you told me”)
OPENERS = {
    "coach": [
        "Okay.",
        "Got it.",
        "Alright — let’s make this practical.",
        "Cool, let’s break it down.",
        "Let’s keep it simple.",
    ],
    "therapist": [
        "I hear you.",
        "That sounds like a lot.",
        "Makes sense.",
        "Okay — let’s slow down a bit.",
        "I’m with you.",
    ],
    "listener": [
        "I hear you.",
        "That sounds really tough.",
        "Okay. I’m here.",
        "I’m listening.",
        "Makes sense.",
    ],
    "balanced": [
        "Got it.",
        "Okay.",
        "I hear you.",
        "Alright.",
        "Makes sense.",
    ],
}

# Pacing lines — optional, used less often to avoid “scripted therapist” vibe
PACING = {
    "high_intensity": [
        "No pressure — one small step at a time.",
        "We can go slowly.",
        "Let’s just focus on this moment first.",
    ],
    "coach": [
        "We’ll keep it practical.",
        "Let’s focus on what helps right now.",
    ],
    "therapist": [
        "We can understand it before we try to fix it.",
        "Let’s make sense of it together.",
    ],
    "listener": [
        "We can take this gently.",
        "We’ll go at your pace.",
    ],
    "balanced": [
        "We can go step by step.",
        "One thing at a time.",
    ],
}


def resolve_mode(profile: Optional[Dict[str, Any]] = None, user_obj=None) -> str:
    """User preference wins. Fallback to profile dict. Default auto."""
    m = None
    if user_obj is not None:
        m = getattr(user_obj, "preferred_mode", None)
    if not m and profile:
        m = profile.get("preferred_mode")
    m = (m or "auto").strip().lower()
    return m if m in MODES else "auto"


def auto_mode(emotion: str, intensity: int) -> str:
    e = (emotion or "").lower().strip()
    if int(intensity or 2) >= 4:
        return "listener"
    if e in ("panic",):
        return "listener"
    if e in ("overthinking", "guilt", "confusion", "shame"):
        return "therapist"
    if e in ("burnout", "stress"):
        return "coach"
    return "balanced"


def _pick(items: list[str]) -> str:
    return random.choice(items) if items else ""


def is_unsure_message(user_text: str) -> bool:
    return bool(_UNSURE_RE.match((user_text or "").strip()))


def _is_short_ack(user_text: str) -> bool:
    return bool(_SHORT_ACK_RE.match((user_text or "").strip()))


def _base_has_question(base: str) -> bool:
    return (base or "").count("?") >= 1


def _pick_nonrepeating(profile: Optional[Dict[str, Any]], key: str, pool: list[str]) -> str:
    """
    Avoid repeating the same opener line back-to-back.
    Stores in profile dict if available (safe; only affects current request unless you persist it).
    """
    if not pool:
        return ""
    last_key = f"_last_{key}"
    last = ""
    if profile is not None:
        last = str(profile.get(last_key) or "").strip()

    candidates = [x for x in pool if x.strip() and x.strip() != last] or pool
    chosen = random.choice(candidates).strip()

    if profile is not None:
        profile[last_key] = chosen
    return chosen


def _maybe_opener(profile: Optional[Dict[str, Any]], mode: str, intensity: int) -> str:
    """
    To sound less robotic, we do NOT always add an opener.
    Higher intensity -> more likely to add.
    """
    intensity = int(intensity or 2)

    # opener probability
    if intensity >= 4:
        p = 0.85
    elif mode == "coach":
        p = 0.55
    elif mode == "therapist":
        p = 0.55
    elif mode == "listener":
        p = 0.50
    else:  # balanced
        p = 0.45

    if random.random() > p:
        return ""

    pool = OPENERS.get(mode, OPENERS["balanced"])
    return _pick_nonrepeating(profile, "opener", pool)


def _maybe_pacing(profile: Optional[Dict[str, Any]], mode: str, intensity: int) -> str:
    """
    Pacing is useful but can feel scripted if always present.
    Use less often; more often only for high intensity.
    """
    intensity = int(intensity or 2)

    if intensity >= 4:
        p = 0.60
        pool = PACING["high_intensity"]
    else:
        # lower frequency to reduce “therapist script”
        if mode in ("therapist", "listener"):
            p = 0.25
        elif mode == "coach":
            p = 0.20
        else:
            p = 0.18
        pool = PACING.get(mode, PACING["balanced"])

    if random.random() > p:
        return ""

    return _pick_nonrepeating(profile, "pacing", pool)


def _microstep_for_unsure() -> str:
    return _pick([
        "Let’s make it tiny: one slow breath in… and out.",
        "Just 10 seconds: relax your shoulders and exhale slowly.",
        "Press your feet into the floor for 5 seconds — notice the support.",
    ])


def _question(mode: str, emotion: str, intensity: int) -> str:
    """Return at most ONE gentle question. Sometimes none."""
    intensity = int(intensity or 2)
    e = (emotion or "").lower().strip()

    if intensity >= 4:
        return _pick([
            "What feels strongest right now — body, thoughts, or emotions?",
            "What’s the hardest part of this moment?",
            "Are you somewhere safe right now?",
        ])

    if mode == "coach":
        return _pick([
            "What’s the most urgent part to handle first?",
            "What’s one small thing you can do in the next 10 minutes?",
            "Do you want comfort, clarity, or a plan right now?",
        ])

    if mode == "therapist":
        return _pick([
            "What do you think you need most underneath this feeling?",
            "What’s the story your mind keeps repeating here?",
            "What would feel like a little relief today?",
        ])

    if e == "sad":
        return _pick([
            "What’s been weighing on you most lately?",
            "Is this more about loss, loneliness, or feeling stuck?",
        ])

    if e == "anger":
        return _pick([
            "What felt unfair or crossed a line for you?",
            "What do you wish they understood?",
        ])

    if e == "overthinking":
        return _pick([
            "What’s the thought your mind keeps looping on?",
            "What would feel like enough clarity here?",
        ])

    return _pick([
        "What part of this feels hardest right now?",
        "What do you need most right now — comfort, clarity, or a next step?",
    ])


def humanize_reply(
    *,
    user_text: str,
    base_reply: str,
    emotion: str,
    intensity: int,
    profile: Optional[Dict[str, Any]] = None,
    user_obj=None,
) -> str:
    """
    Wrap the base reply with warmth + optional pacing + optional question.
    Less robotic rules:
    - Don’t ALWAYS add an opener.
    - Don’t ALWAYS add pacing.
    - Don’t ALWAYS end with a question.
    - Never add a question if base already has one.
    """
    base = (base_reply or "").strip()
    if not base:
        return ""

    chosen = resolve_mode(profile, user_obj=user_obj)
    if chosen == "auto":
        chosen = auto_mode(emotion=emotion, intensity=intensity)

    intensity = int(intensity or 2)

    # Unsure: microstep + no interrogation
    if is_unsure_message(user_text):
        parts = []
        op = _maybe_opener(profile, mode="listener", intensity=max(intensity, 4))
        if op:
            parts.append(op)
        pace = _maybe_pacing(profile, mode="listener", intensity=max(intensity, 4))
        if pace:
            parts.append(pace)
        parts.append(_microstep_for_unsure())
        parts.append(base)
        return "\n\n".join([p.strip() for p in parts if p and p.strip()]).replace("**", "").strip()

    # Short ack: don’t add extra questions
    if _is_short_ack(user_text):
        parts = []
        op = _maybe_opener(profile, mode=chosen, intensity=intensity)
        if op:
            parts.append(op)
        parts.append(base)
        return "\n\n".join([p.strip() for p in parts if p and p.strip()]).replace("**", "").strip()

    parts = []

    op = _maybe_opener(profile, mode=chosen, intensity=intensity)
    if op:
        parts.append(op)

    pace = _maybe_pacing(profile, mode=chosen, intensity=intensity)
    if pace:
        parts.append(pace)

    parts.append(base)

    # Questions: reduce frequency so it doesn’t feel like an interview
    add_question = (not _base_has_question(base))

    q = ""
    if add_question:
        q = _question(mode=chosen, emotion=emotion, intensity=intensity)

    if chosen == "coach":
        q_prob = 0.35
    elif chosen == "therapist":
        q_prob = 0.40
    elif chosen == "listener":
        q_prob = 0.30
    else:  # balanced
        q_prob = 0.32

    if q and random.random() < q_prob:
        parts.append(q)

    out = "\n\n".join([p.strip() for p in parts if p and p.strip()]).strip()
    return out.replace("**", "").strip()