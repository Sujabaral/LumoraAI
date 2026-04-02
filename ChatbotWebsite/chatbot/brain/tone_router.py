# ChatbotWebsite/chatbot/brain/tone_router.py
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Literal, Optional

Mode = Literal["crisis", "support", "fun", "info", "social", "unknown"]

@dataclass
class ToneDecision:
    mode: Mode
    reason: str
    confidence: float

_LAUGH = re.compile(r"\b(lol|lmao|rofl|haha+|hehe+)\b|[😂🤣😹]", re.I)
_FUN_REQ = re.compile(r"\b(joke|meme|riddle|roast|pickup line|fun fact|would you rather|truth or dare)\b", re.I)
_GAMEY = re.compile(r"\b(who wins|vs\.?|versus|battle|fight|duel)\b", re.I)

_DISTRESS = re.compile(
    r"\b(i feel|i'm feeling|i am feeling|depressed|sad|anxious|stress|stressed|panic|worried|"
    r"can't sleep|insomnia|hopeless|overwhelmed|lonely|hurt|cry)\b",
    re.I
)
_HELP = re.compile(r"\b(help me|what should i do|i need help|advise me)\b", re.I)

_GREET = re.compile(r"^(hi|hello|hey|yo|namaste|sup|wassup)\b", re.I)

def route_tone(text: str) -> ToneDecision:
    t = (text or "").strip()
    if not t:
        return ToneDecision("unknown", "empty", 0.0)

    tl = t.lower()

    # Social
    if _GREET.search(t) and len(tl.split()) <= 3:
        return ToneDecision("social", "greeting", 0.9)

    # Support signals
    has_distress = bool(_DISTRESS.search(t)) or bool(_HELP.search(t))

    # Fun signals
    has_fun = bool(_LAUGH.search(t)) or bool(_FUN_REQ.search(t)) or bool(_GAMEY.search(t))

    # Disambiguation
    if has_fun and not has_distress:
        return ToneDecision("fun", "fun_signals_no_distress", 0.85)

    if has_distress:
        return ToneDecision("support", "distress_or_help", 0.85)

    # Default: looks like info question (heuristic: question mark or starts with wh/how)
    if "?" in t or re.match(r"^(what|why|how|when|where|who)\b", tl):
        return ToneDecision("info", "question_form", 0.65)

    return ToneDecision("unknown", "no_clear_signals", 0.4)