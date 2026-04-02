# ChatbotWebsite/chatbot/brain/style.py
from __future__ import annotations

from typing import List, Optional, Dict, Tuple
import re


# ---------------------------- Lexicons ----------------------------

PROBLEM_SOLVER_PHRASES = [
    "what should i do", "what do i do", "how do i", "give me steps", "give steps",
    "solution", "fix this", "help me solve", "make a plan", "plan for", "roadmap",
    "how can i", "what is the best way", "tell me how", "guide me"
]

LONELY_PHRASES = [
    "i feel alone", "i am alone", "i'm alone", "lonely", "no one", "nobody",
    "left me", "no friends", "no friend", "ignored", "no one cares", "i have no one",
    "everyone left", "alone again"
]

VALIDATION_PHRASES = [
    "idk", "i don't know", "i dont know", "i can't", "i cant", "i'm tired", "im tired",
    "so tired", "done", "hopeless", "empty", "sad", "exhausted", "drained",
    "i'm not okay", "im not okay", "i am not okay", "it hurts", "help"
]

OVERTHINKER_PHRASES = [
    "what if", "why me", "why does", "why do", "overthinking", "i keep thinking",
    "can't stop thinking", "cant stop thinking", "it keeps looping", "my mind won't stop",
    "my mind wont stop", "thinking too much"
]

# Romanized Nepali / Hinglish (lightweight)
NP_PROBLEM_SOLVER = [
    "kasari", "ke garne", "ke garum", "upaya", "solution", "tarika", "plan banauna"
]
NP_LONELY = [
    "eklo", "eklai", "sathi chaina", "sathi chhaina", "sathi haru chainan",
    "kasai chaina", "koi chaina", "koi chhaina"
]
NP_VALIDATION = [
    "dikka", "maan dukha", "man dukha", "dukha", "thakai", "thakyo",
    "runcha", "runa man", "basna man chaina", "sakdina", "garna sakdina"
]
NP_OVERTHINK = [
    "dherai soch", "sochiraheko", "sochera", "chinta", "tension", "ke hola",
    "k ho yesto", "kina", "kati soch"
]

# Helpful patterns
QUESTION_MARK_HEAVY = re.compile(r"\?{2,}")  # "??", "???"
ALL_CAPS_WORD = re.compile(r"\b[A-Z]{4,}\b")


# ---------------------------- Helpers ----------------------------

def _norm(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("’", "'")
    t = re.sub(r"\s+", " ", t)
    return t

def _lower(text: str) -> str:
    return _norm(text).lower()

def _contains_any(hay: str, needles: List[str]) -> bool:
    return any(n in hay for n in needles)

def _count_any(hay: str, needles: List[str]) -> int:
    return sum(1 for n in needles if n in hay)

def _word_count(text: str) -> int:
    return len(_lower(text).split())

def _recency_weighted_history(history_last_n: Optional[List[str]], max_chars: int = 1200) -> str:
    """
    Join last messages with recency bias (last message repeated more).
    Keeps a max char length so it stays fast.
    """
    if not history_last_n:
        return ""
    msgs = [m for m in history_last_n if isinstance(m, str) and m.strip()]
    if not msgs:
        return ""

    # recency bias: last messages more weight
    weighted = []
    for i, m in enumerate(msgs[-6:]):  # last 6 messages is enough
        rep = 1 + i // 2  # older=1, newer=2/3
        weighted.append((" " + m) * rep)

    out = _lower(" ".join(weighted))
    return out[-max_chars:]


# ---------------------------- Main ----------------------------

def detect_style(text: str, history_last_n: Optional[List[str]] = None) -> str:
    """
    Returns one of:
      - problem_solver
      - lonely
      - validation_seeker
      - overthinker
      - neutral
    """
    t_raw = _norm(text)
    t = t_raw.lower()
    hist = _recency_weighted_history(history_last_n)

    wc = _word_count(t_raw)
    short = wc <= 6
    longish = wc >= 35

    # Score-based approach (more stable than early-return)
    scores: Dict[str, float] = {
        "problem_solver": 0.0,
        "lonely": 0.0,
        "validation_seeker": 0.0,
        "overthinker": 0.0,
        "neutral": 0.0,
    }

    # ---------------- Problem solver ----------------
    scores["problem_solver"] += 2.5 * _count_any(t, PROBLEM_SOLVER_PHRASES)
    scores["problem_solver"] += 1.5 * _count_any(t, NP_PROBLEM_SOLVER)
    if t.endswith("?"):
        scores["problem_solver"] += 0.4
    if "steps" in t or "plan" in t:
        scores["problem_solver"] += 0.6

    # ---------------- Lonely ----------------
    # Guard: avoid catching “no one method works” etc by requiring emotional context words
    lonely_hits = _count_any(t, LONELY_PHRASES) + _count_any(t, NP_LONELY)
    if lonely_hits:
        scores["lonely"] += 2.3 * lonely_hits
        if any(w in t for w in ["feel", "feeling", "sad", "hurt", "cry", "miss", "alone", "lonely", "eklo", "dukha"]):
            scores["lonely"] += 0.8

    # ---------------- Validation seeker ----------------
    val_hits = _count_any(t, VALIDATION_PHRASES) + _count_any(t, NP_VALIDATION)
    if short and val_hits:
        scores["validation_seeker"] += 2.2 + 1.2 * val_hits
    else:
        scores["validation_seeker"] += 1.0 * val_hits

    # Very low-energy signals
    if short and re.fullmatch(r"(ok|okay|fine|idk|hmm|nah|no|yes|yup|k|.)", t.strip()):
        scores["validation_seeker"] += 1.2

    # ---------------- Overthinker ----------------
    over_hits = _count_any(t, OVERTHINKER_PHRASES) + _count_any(t, NP_OVERTHINK)
    scores["overthinker"] += 1.8 * over_hits

    # Multi-why + many questions
    if t.count("why") >= 2 or "kina" in t:
        scores["overthinker"] += 1.2
    if QUESTION_MARK_HEAVY.search(t_raw):
        scores["overthinker"] += 0.6
    if longish:
        scores["overthinker"] += 0.8

    # History cues
    if hist:
        scores["overthinker"] += 0.8 * _count_any(hist, ["what if", "overthink", "why", "kina", "ke hola", "chinta"])
        scores["lonely"] += 0.6 * _count_any(hist, ["alone", "lonely", "no one cares", "eklo", "koi chaina"])
        scores["validation_seeker"] += 0.4 * _count_any(hist, ["tired", "done", "hopeless", "empty", "thakai", "dikka"])
        scores["problem_solver"] += 0.4 * _count_any(hist, ["steps", "plan", "how do i", "kasari", "ke garne"])

    # ---------------- Tie-breaking rules ----------------
    # If user is short + distressed: validation tends to be best style
    if short and (scores["validation_seeker"] >= 2.0) and scores["problem_solver"] < 2.0:
        return "validation_seeker"

    # Choose best score
    best = max(scores.items(), key=lambda kv: kv[1])[0]
    best_score = scores[best]

    # If nothing strong matched, neutral
    if best_score < 1.2:
        return "neutral"

    return best