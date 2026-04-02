# ChatbotWebsite/chatbot/safety.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple, Optional


# ---------------------------
# Utilities
# ---------------------------
def _norm(t: str) -> str:
    t = (t or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _matches_any(patterns: List[str], text: str) -> Optional[str]:
    """Returns the first matching pattern (string) if any matches, else None."""
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            return p
    return None


# ---------------------------
# Patterns
# ---------------------------

# ✅ Strong / direct self-harm intent (English)  -> HIGH
# ✅ Strong / direct self-harm intent (English) -> HIGH
EN_HIGH = [
    r"\bi\s*want\s*to\s*die\b",
    r"\bi\s*wanna\s*die\b",
    r"\bwant\s*to\s*die\b",
    r"\bwanna\s*die\b",
    r"\bkill\s*myself\b",
    r"\bi\s*want\s*to\s*kill\s*myself\b",
    r"\bi\s*wanna\s*kill\s*myself\b",
    r"\bcommit\s*suicide\b",
    r"\bend\s*my\s*life\b",
    r"\bend\s*it\s*all\b",
    r"\bhurt\s*myself\b",
    r"\bself[\s-]*harm\b",

    # ✅ cutting (THIS fixes your screenshot case)
    r"\bcut\s*(myself|me)\b",
    r"\bcutting\s*(myself|me)\b",
    r"\bshould\s+i\s+cut\s*(myself|me)\b",
    r"\bwant\s+to\s+cut\s*(myself|me)\b",
    r"\burge\s+to\s+cut\b",

    # extra robust patterns
    r"\b(i|i'm|im)\s*(will|gonna|going\s*to)\s*(die|kill\s*myself)\b",
    r"\b(i|i'm|im)\s*(want|wanna)\s*to\s*(die|kill\s*myself)\b",
    r"\b(i|i'm|im)\s*can't\s*go\s*on\b",
    r"\bno\s*reason\s*to\s*live\b",
]

# ✅ Vague ideation / passive thoughts -> MEDIUM
EN_MED = [
    r"\bi\s*wish\s*i\s*was\s*dead\b",
    r"\bi\s*wish\s*i\s*could\s*die\b",
    r"\bdon'?t\s*want\s*to\s*live\b",
    r"\bwant\s*to\s*disappear\b",
    # keep "suicide" here if you want it MEDIUM (avoid false alarms like "suicide prevention")
    r"\bsuicide\b",
]


# ✅ Extreme distress phrasing (for safety confirmation modal; NOT self-harm)
EN_EXTREME_DISTRESS = [
    r"\bextremely\s+(depressed|anxious|overwhelmed|stressed)\b",
    r"\bextreme\s+(depression|anxiety|stress)\b",
    r"\bso\s+(depressed|anxious|overwhelmed|stressed)\b",
    r"\bseverely\s+(depressed|anxious|overwhelmed|stressed)\b",
    r"\bi\s*can'?t\s*cope\b",
    r"\bi\s*can'?t\s*take\s*it\b",
    r"\bfeel\s+out\s+of\s+control\b",
]
# ✅ Roman Nepali / Nepali strong intent -> HIGH
NP_HIGH: List[str] = [
    # roman nepali
    r"\bmalai\s+marna\s+man\s+cha\b",
    r"\bmarna\s+man\s+cha\b",
    r"\bmarna\s+man\s+lagyo\b",
    r"\bafno\s+jyan\s+lina\b",
    r"\bjyan\s+linchu\b",
    r"\bma\s+marchu\b",
    r"\bma\s+marna\b",
    r"\bmarera\s+sakauchhu\b",
    # devanagari
    r"मर्न\s+मन\s+छ",
    r"मलाई\s+मर्न\s+मन\s+छ",
    r"आत्महत्या",
    r"आफ्नो\s+ज्यान",
]

# ✅ Negations / reassurance (should NOT trigger)
NEGATIONS: List[str] = [
    # english
    r"\bnot\s+suicidal\b",
    r"\bi\s*am\s*not\s*suicidal\b",
    r"\bi'?m\s*not\s*suicidal\b",
    r"\bi\s*don'?t\s*want\s*to\s*die\b",
    r"\bi\s*am\s*safe\b",
    r"\bi'?m\s*safe\b",
    r"\bi\s*would\s*never\s*kill\s*myself\b",
    # roman nepali
    r"\bmarna\s+man\s+chaina\b",
    r"\bmarna\s+man\s+xaina\b",
    r"\bma\s+mardina\b",
    r"\bma\s+marna\s+chahanna\b",
        # ✅ common negated variants (fix: "don't wanna die" etc.)
    r"\bi\s*(do\s*not|don'?t|dont)\s*wanna\s*die\b",
    r"\bi\s*(do\s*not|don'?t|dont)\s*want\s*to\s*die\b",
    r"\bi\s*(do\s*not|don'?t|dont)\s*want\s*to\s*die\s*now\b",
    r"\bi\s*(do\s*not|don'?t|dont)\s*want\s*to\s*kill\s*myself\b",
    r"\bi\s*(do\s*not|don'?t|dont)\s*wanna\s*kill\s*myself\b",
    # devanagari
    r"मर्न\s+मन\s+छैन",
    r"आत्महत्या\s+गर्दिन",
]

# ✅ Talking about someone else / general discussion (downgrade)
THIRD_PERSON_HINTS: List[str] = [
    r"\bmy\s+friend\b",
    r"\bfriend\b",
    r"\bmero\s+sathi\b",
    r"\bmero\s+saathi\b",
    r"\bsomeone\b",
    r"\bthey\b|\bhe\b|\bshe\b",
    r"\bnews\b|\bmovie\b|\bstory\b|\barticle\b",
    r"\bprevention\b|\bawareness\b|\bhelp\s*line\b|\bhelpline\b",
]


# ---------------------------
# Result type
# ---------------------------
@dataclass
class SelfHarmResult:
    hit: bool
    level: str   # "low" | "medium" | "high"
    reason: str
    match: Optional[str] = None


# ---------------------------
# MAIN detector (single source of truth)
# ---------------------------
def detect_self_harm(text: str) -> SelfHarmResult:
    """
    Detect self-harm intent from RAW user message.
    Returns SelfHarmResult.
    """
    t = _norm(text)
    if not t:
        return SelfHarmResult(False, "low", "empty")

    # 1) Negation first
    neg = _matches_any(NEGATIONS, t)
    if neg:
        return SelfHarmResult(False, "low", "negation", match=neg)

    # 2) Third-person hint
    third_person = bool(_matches_any(THIRD_PERSON_HINTS, t))

    # 3) High intent
    hit_high = _matches_any(EN_HIGH, t) or _matches_any(NP_HIGH, t)
    if hit_high:
        if third_person:
            return SelfHarmResult(True, "medium", "self_harm_third_person", match=hit_high)
        return SelfHarmResult(True, "high", "self_harm_direct", match=hit_high)

    # 4) Medium intent (vague)
    hit_med = _matches_any(EN_MED, t)
    if hit_med:
        if third_person:
            return SelfHarmResult(True, "low", "self_harm_third_person_vague", match=hit_med)
        return SelfHarmResult(True, "medium", "self_harm_vague", match=hit_med)

    return SelfHarmResult(False, "low", "none")


# ---------------------------
# Risk scoring used by routes.py
# ---------------------------
def classify_risk(
    final_score: float,
    self_harm: bool = False,
    trend_label: str = "stable",
    slope: float = 0.0
) -> Tuple[str, List[str]]:
    """
    final_score: sentiment final score in [0..1]
      - closer to 0 => negative
      - closer to 1 => positive
    Returns: (risk_level, reasons) where risk_level in {"low","medium","high"}.
    """
    reasons: List[str] = []

    try:
        score = float(final_score)
    except Exception:
        score = 0.5
        reasons.append("Invalid sentiment score; defaulted to 0.5")

    self_harm = bool(self_harm)
    trend_label = (trend_label or "stable").strip().lower()

    try:
        slope_val = float(slope)
    except Exception:
        slope_val = 0.0

    # 1) Hard escalation always wins
    if self_harm:
        return "high", ["Self-harm indicators detected."]

    # 2) Base risk from sentiment (sentiment alone should NEVER be HIGH)
    #    (This is the big fix: positive like 0.85 should NOT become high.)
    if score <= 0.20:
        risk = "medium"
        reasons.append(f"Very negative sentiment ({score:.2f}).")
    elif score <= 0.35:
        risk = "medium"
        reasons.append(f"Negative sentiment ({score:.2f}).")
    else:
        risk = "low"
        reasons.append(f"Non-negative sentiment ({score:.2f}).")

    # 3) Trend escalation (optional)
    if trend_label in ("worsening", "declining", "down", "negative") and slope_val < -0.15:
        if risk == "low":
            risk = "medium"
            reasons.append("Mood trend worsening.")
        elif risk == "medium":
            # keep at medium (do not escalate to high without explicit self-harm)
            reasons.append("Mood trend worsening.")

    return risk, reasons


# ---------------------------
# Optional legacy helper (if any old code expects bool)
# ---------------------------
def detect_self_harm_bool(text: str) -> bool:
    return bool(detect_self_harm(text).hit)

# ---------------------------
# Extreme distress helper (for confirmation modal)
# ---------------------------
def detect_extreme_distress(text: str) -> bool:
    t = _norm(text)
    if not t:
        return False
    # do not trigger if user is explicitly negating
    if _matches_any(NEGATIONS, t):
        return False
    return _matches_any(EN_EXTREME_DISTRESS, t) is not None
