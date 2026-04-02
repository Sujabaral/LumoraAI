# ChatbotWebsite/chatbot/brain/risk.py
from __future__ import annotations

from typing import Literal
import re

RiskLevel = Literal["low", "medium", "high"]


# -------------------------
# English patterns
# -------------------------
NEGATIONS = [
    "not suicidal",
    "i am not suicidal",
    "i'm not suicidal",
    "i dont want to die",
    "i don't want to die",
    "i would never kill myself",
    "i am safe",
    "i'm safe",
    "i don't wanna die",
]

THIRD_PERSON_HINTS = [
    "my friend", "my brother", "my sister", "someone i know", "someone", "they", "he", "she",
    "news", "movie", "documentary", "article", "story", "case study",
]

ACTIVE_IDEATION = [
    "i want to die",
    "i want to kill myself",
    "i will kill myself",
    "i'm going to kill myself",
    "i am going to kill myself",
    "end my life",
    "commit suicide",
    "kill myself",
]

PASSIVE_IDEATION = [
    "i wish i was dead",
    "i wish i were dead",
    "i wish i could disappear",
    "i don't want to exist",
    "i dont want to exist",
    "no reason to live",
    "life is pointless",
    "everyone would be better without me",
    "better without me",
    "i want everything to stop",
]

HOPELESSNESS = [
    "hopeless",
    "can't go on",
    "cannot go on",
    "nothing matters",
    "worthless",
    "no way out",
    "give up",
    "tired of everything",
    "i can't do this anymore",
    "i cant do this anymore",
    "i'm done",
    "im done",
]

IMMINENCE = [
    "today", "tonight", "right now", "after this", "soon", "this is my last",
    "goodbye", "final message", "last message",
]

METHODS = [
    "rope", "knife", "pills", "poison", "jump", "bridge",
    "hang myself", "cut my wrist", "overdose", "od", "slit my wrist",
]


# -------------------------
# Nepali (Devanagari) + Romanized Nepali patterns
# -------------------------
# first-person hints to avoid misclassifying third-person discussion
FIRST_PERSON_HINTS_NE = [
    "ma ", "ma", "malai", "mero", "malaai", "malae", "malaai",
    "म ", "म", "मलाई", "मेरो", "मेरा", "मै",
]

THIRD_PERSON_HINTS_NE = [
    "sathi", "sathi ko", "mero sathi", "usko", "tiniharu", "uni", "uha", "usle",
    "साथी", "मेरो साथी", "उसको", "तिनीहरू", "उनी", "उहाँ", "उसले",
    "news", "movie", "story", "article", "case",
]

NEGATIONS_NE = [
    # Devanagari
    "म आत्महत्या गर्न चाहन्न",
    "आत्महत्या गर्न चाहन्न",
    "म मर्न चाहन्न",
    "मर्न चाहन्न",
    "म सुरक्षित छु",
    "म ठीक छु",
    # Romanized
    "ma aatmahathya garna chahanna",
    "aatmahathya garna chahanna",
    "ma marna chahanna",
    "marna chahanna",
    "ma safe chu",
    "ma thik chu",
]

ACTIVE_IDEATION_NE = [
    # Devanagari
    "म मर्न चाहन्छु",
    "म मर्नु चाहन्छु",
    "म आत्महत्या गर्न चाहन्छु",
    "म आफ्नो ज्यान लिन चाहन्छु",
    "म मरिदिन्छु",
    "म ज्यान दिन्छु",
    "म बाँच्न चाहन्न",   # sometimes used actively
    "मलाई मर्न मन छ",
    "मलाई मर्नु मन छ",
    "मलाई मर्न मन लाग्यो",
    "मलाई आत्महत्या गर्न मन छ",
    # Romanized
    "ma marna chahanchu",
    "ma marnu chahanchu",
    "ma aatmahathya garna chahanchu",
    "ma jyan linchhu",
    "ma maridinchu",
    "ma jyan dinchu",
    "malai marna man xa",
    "malai marnu man xa",
    "malai marna man lagyo",
    "malai aatmahathya garna man xa",
]

PASSIVE_IDEATION_NE = [
    # Devanagari
    "म बाँच्न मन छैन",
    "बाँच्न मन छैन",
    "जिउन मन छैन",
    "म हराउन चाहन्छु",
    "काश म मरेको भए",
    "म अस्तित्व चाहन्न",
    # Romanized
    "bachna man chaina",
    "jiuna man chaina",
    "ma harauna chahanchu",
    "kaas ma mareko bhaye",
    "ma exist garna chahanna",
]

HOPELESSNESS_NE = [
    # Devanagari
    "अब सक्दिन",
    "सक्दिन",
    "सबै सकियो",
    "केही काम छैन",
    "आशा छैन",
    "कुनै बाटो छैन",
    "थाकिसकेँ",
    # Romanized
    "aba sakdina",
    "sakdina",
    "sabai sakiyo",
    "aasha chaina",
    "kunai bato chaina",
    "thakisake",
    "thakisakee",
]

IMMINENCE_NE = [
    # Devanagari
    "आज", "आजै", "आज राति", "अहिले", "तुरुन्त", "अबै",
    "बिदा", "अन्तिम", "यो मेरो अन्तिम",
    # Romanized
    "aaja", "aile", "ahile", "turunt", "aba", "aaja rati", "goodbye", "final",
]

METHODS_NE = [
    # Devanagari
    "डोरी", "चक्कु", "ब्लेड", "औषधि", "विष", "झुण्डिन",
    "काट्ने", "ओभरडोज", "पुलबाट हाम्फाल्ने",
    # Romanized
    "dori", "chakku", "blade", "ausadhi", "bisha", "jhundin",
    "katne", "overdose", "bridge bata haamfaalne",
]


# -------------------------
# Helpers
# -------------------------
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

def _contains_any(t: str, terms: list[str]) -> bool:
    return any(term in t for term in terms)

def _has_first_person(t: str) -> bool:
    # English first-person
    if re.search(r"\b(i|i'm|im|my|me)\b", t):
        return True
    # Nepali first-person (roman + devanagari)
    return _contains_any(t, FIRST_PERSON_HINTS_NE)

def _likely_third_person(t: str) -> bool:
    # If there are many third-person hints and no first-person markers, treat as discussion
    if (_contains_any(t, THIRD_PERSON_HINTS) or _contains_any(t, THIRD_PERSON_HINTS_NE)) and not _has_first_person(t):
        return True
    return False

def _rule_based_risk(t: str) -> RiskLevel:
    # Negation/reassurance should down-weight to low
    if _contains_any(t, NEGATIONS) or _contains_any(t, NEGATIONS_NE):
        return "low"

    third_person = _likely_third_person(t)

    active = _contains_any(t, ACTIVE_IDEATION) or _contains_any(t, ACTIVE_IDEATION_NE)
    passive = _contains_any(t, PASSIVE_IDEATION) or _contains_any(t, PASSIVE_IDEATION_NE)
    hopeless = _contains_any(t, HOPELESSNESS) or _contains_any(t, HOPELESSNESS_NE)

    imminence = _contains_any(t, IMMINENCE) or _contains_any(t, IMMINENCE_NE)
    method = _contains_any(t, METHODS) or _contains_any(t, METHODS_NE)

    # High risk rules
    if active and (method or imminence):
        level: RiskLevel = "high"
    elif active:
        level = "high"
    elif passive and (method or imminence):
        level = "high"
    elif passive or hopeless:
        level = "medium"
    else:
        level = "low"

    # If it looks like third-person discussion (and no first-person), downshift
    if third_person:
        if level == "high":
            return "medium"
        if level == "medium":
            return "low"
        return "low"

    return level

def _max_level(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    order = {"low": 0, "medium": 1, "high": 2}
    inv = {0: "low", 1: "medium", 2: "high"}
    return inv[max(order[a], order[b])]


# -------------------------
# Model fallback (your existing emotion-based risk)
# -------------------------
from ChatbotWebsite.chatbot.brain.emotion import detect_risk as _detect_risk


def assess_risk(text: str) -> RiskLevel:
    """
    Single source of truth for risk level.
    Returns: "low" | "medium" | "high"

    Combines:
    1) Rule-based detection (English + Nepali + romanized Nepali)
    2) Your existing emotion.detect_risk model
    Uses the higher of the two.
    """
    t = _norm(text)

    rule_level: RiskLevel = _rule_based_risk(t)

    # model fallback
    rr = _detect_risk(text or "")
    model_level: RiskLevel
    if rr.level == "high":
        model_level = "high"
    elif rr.level == "medium":
        model_level = "medium"
    else:
        model_level = "low"

    return _max_level(rule_level, model_level)

# -------------------------
# Unified classifier used by routes.py
# -------------------------

def classify_risk(final_score: float, self_harm: bool, trend_label: str, slope: float):
    reasons = []
    # HIGH only if explicit self harm
    if self_harm:
        reasons.append("Explicit self-harm indicators.")
        return "high", reasons

    # sentiment score should never produce HIGH
    if final_score >= 0.75:
        risk = "medium"
        reasons.append(f"Very negative sentiment ({final_score:.2f}).")
    elif final_score >= 0.45:
        risk = "medium"
        reasons.append(f"Moderate distress ({final_score:.2f}).")
    else:
        risk = "low"
        reasons.append(f"Low distress ({final_score:.2f}).")

    if trend_label in ("worsening","declining") and slope < -0.2:
        if risk=="low":
            risk="medium"
            reasons.append("Mood worsening trend.")

    return risk, reasons
