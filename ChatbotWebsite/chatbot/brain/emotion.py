# ChatbotWebsite/chatbot/brain/emotion.py
"""
LUMORA Emotion & Risk Detector (rule-based, no external APIs)

Goals:
- Detect a primary emotion and intensity score (1-5)
- Detect crisis / self-harm risk level separately
- Work well with Nepali users (basic romanized Nepali + Hinglish)
- Be robust to negations ("not sad", "not anxious")
- Provide explainable outputs (why it detected)

You can start using:
    emotion, intensity, details = detect_emotion(message)

If you want to keep your old signature:
    emotion, intensity = detect_emotion_simple(message)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import re


# ---------------------------- Utilities ----------------------------

_WORD_RE = re.compile(r"[a-z0-9']+")

NEGATIONS = {
    "not", "no", "never", "dont", "don't", "doesnt", "doesn't", "didnt", "didn't",
    "cant", "can't", "cannot", "wont", "won't", "without"
}

INTENSIFIERS_HIGH = {
    "extremely", "really", "so", "very", "super", "too", "terribly", "hugely",
    "insanely", "unbearably", "absolutely", "completely"
}
INTENSIFIERS_MED = {"quite", "pretty", "rather"}
DIMINISHERS = {"slightly", "a bit", "bit", "little", "somewhat", "kinda", "kind of", "sort of"}

# Romanized Nepali / common Nepali-English phrases (keep lightweight)
NP_ANXIETY = {"ghabrahat", "ghabrahat", "dar", "darr", "chinta", "tension", "attincha", "attiyeko", "aatinchha", "ghabrai"}
NP_SAD = {"mandukha", "man dukha", "dukha", "dikka", "nirash", "nirasha", "runcha", "runa", "aansu", "aanshu"}
NP_ANGER = {"ris", "risutcha", "jhyau", "jhyaau", "chidh", "chidhyo", "chidhyeko"}
NP_STRESS = {"pressure", "parixa", "pariksha", "thakai", "thakyo", "thakcha", "thakai lagyo", "burnout"}
NP_LONELY = {"eklo", "eklai", "aklo", "alone", "sathi chaina", "sathiko kami", "sathi haru chainan"}

# Basic emoticons
EMOJI_SAD = {":(", ":'(", "😢", "😭", "☹", "🙁", "😞", "😔"}
EMOJI_ANX = {"😰", "😟", "😣", "😖", "😨", "😱"}
EMOJI_ANGER = {"😡", "🤬", "😠"}

# ---------------------------- Risk / Crisis phrases ----------------------------

# High intent self-harm phrases
CRISIS_HIGH_PHRASES = [
    "i want to die", "i want to kill myself", "i will kill myself", "i'm going to kill myself",
    "i am going to kill myself", "i want to end my life", "end my life", "suicide", "suicidal",
    "i want to self harm", "i want to hurt myself", "i want to cut myself", "i cut myself",
    "i want to overdose", "overdose", "jump off", "hang myself", "poison myself"
]

# Medium risk phrases (passive ideation / hopelessness)
CRISIS_MED_PHRASES = [
    "i don't want to live", "i dont want to live", "life is not worth it", "life isn't worth it",
    "i can't go on", "i cannot go on", "i can't do this anymore", "i cant do this anymore",
    "everyone would be better without me", "i am a burden", "i'm a burden", "i feel like giving up on life"
]

# Protective / negation phrases that reduce risk
CRISIS_NEGATION_HINTS = [
    "not suicidal", "i am not suicidal", "i'm not suicidal", "i am not going to", "i'm not going to",
    "i don't want to die", "i dont want to die"
]


# ---------------------------- Emotion lexicon ----------------------------

@dataclass
class EmotionSpec:
    keywords: set
    phrases: List[str]
    base_weight: float


EMOTIONS: Dict[str, EmotionSpec] = {
    "anxiety": EmotionSpec(
        keywords={
            "anxious", "anxiety", "panic", "panicky", "scared", "afraid", "nervous", "worried",
            "worry", "overthink", "overthinking", "dread", "uneasy", "restless", "onedge", "on-edge",
            "fear", "terrified", "phobia", "paranoid"
        } | NP_ANXIETY,
        phrases=[
            "heart is racing", "tight chest", "can't breathe", "cant breathe",
            "feel like i'm dying", "feel like i am dying", "i am panicking", "i'm panicking",
            "anxiety attack", "panic attack"
        ],
        base_weight=1.0
    ),
    "sadness": EmotionSpec(
        keywords={
            "sad", "down", "depressed", "depression", "empty", "numb", "hopeless",
            "cry", "crying", "tear", "tears", "lonely", "alone", "miserable", "heartbroken",
            "grief", "grieving", "lost", "worthless"
        } | NP_SAD | NP_LONELY,
        phrases=[
            "nothing matters", "no motivation", "don't enjoy", "dont enjoy",
            "can't stop crying", "cant stop crying", "life feels pointless"
        ],
        base_weight=1.0
    ),
    "anger": EmotionSpec(
        keywords={
            "angry", "mad", "furious", "irritated", "annoyed", "rage",
            "hate", "pissed", "frustrated"
        } | NP_ANGER,
        phrases=[
            "want to break", "lose my temper", "can't control my anger", "cant control my anger"
        ],
        base_weight=0.9
    ),
    "guilt": EmotionSpec(
        keywords={"guilty", "guilt", "ashamed", "shame", "my fault", "regret", "regretting", "blame myself"} | {"galti", "गल्ती"},
        phrases=["i blame myself", "it's my fault", "it is my fault", "i feel ashamed"],
        base_weight=0.85
    ),
    "burnout": EmotionSpec(
        keywords={"burnout", "burnt", "burned", "exhausted", "tired", "drained", "overwhelmed", "stressed", "stress"} | NP_STRESS,
        phrases=["mentally exhausted", "emotionally exhausted", "can't keep up", "cant keep up", "too much pressure"],
        base_weight=0.95
    ),
    "calm": EmotionSpec(
        keywords={"calm", "okay", "fine", "relaxed", "peaceful", "good", "alright", "better"},
        phrases=["i feel better", "i am okay now", "i'm okay now"],
        base_weight=0.6
    ),
}


# ---------------------------- Core scoring ----------------------------

def _normalize(text: str) -> str:
    t = (text or "").lower().strip()
    # normalize apostrophes and whitespace
    t = t.replace("’", "'")
    t = re.sub(r"\s+", " ", t)
    return t

def _tokens(text: str) -> List[str]:
    return _WORD_RE.findall(text.lower())

def _has_negation_near(tokens: List[str], idx: int, window: int = 3) -> bool:
    start = max(0, idx - window)
    for j in range(start, idx):
        if tokens[j] in NEGATIONS:
            return True
    return False

def _count_intensity_markers(t: str) -> float:
    score = 0.0
    # punctuation intensity
    exclaims = t.count("!")
    score += min(1.5, exclaims * 0.3)
    # caps intensity
    if re.search(r"\b[A-Z]{4,}\b", t):
        score += 0.5
    # elongations like "soooo"
    if re.search(r"(.)\1{2,}", t):
        score += 0.4
    # emoji
    if any(e in t for e in EMOJI_SAD | EMOJI_ANX | EMOJI_ANGER):
        score += 0.4
    # intensifier words
    toks = _tokens(t)
    for w in toks:
        if w in INTENSIFIERS_HIGH:
            score += 0.6
        elif w in INTENSIFIERS_MED:
            score += 0.3
    # diminishers reduce
    for phrase in DIMINISHERS:
        if phrase in t:
            score -= 0.3
    return score

def _score_emotions(text: str) -> Tuple[Dict[str, float], Dict[str, List[str]]]:
    """
    Returns:
      scores: emotion -> float
      hits: emotion -> list of matched evidence strings
    """
    t = _normalize(text)
    toks = _tokens(t)

    scores: Dict[str, float] = {k: 0.0 for k in EMOTIONS.keys()}
    hits: Dict[str, List[str]] = {k: [] for k in EMOTIONS.keys()}

    # Phrase matches
    for emo, spec in EMOTIONS.items():
        for ph in spec.phrases:
            if ph in t:
                scores[emo] += 2.2 * spec.base_weight
                hits[emo].append(f'phrase:"{ph}"')

    # Keyword matches with negation handling
    for i, w in enumerate(toks):
        for emo, spec in EMOTIONS.items():
            if w in spec.keywords:
                if _has_negation_near(toks, i):
                    # "not sad" reduces contribution
                    scores[emo] -= 0.6 * spec.base_weight
                    hits[emo].append(f'negated:"{w}"')
                else:
                    scores[emo] += 1.0 * spec.base_weight
                    hits[emo].append(f'keyword:"{w}"')

    # Add emoji-specific hints
    if any(e in t for e in EMOJI_SAD):
        scores["sadness"] += 1.0
        hits["sadness"].append("emoji:sad")
    if any(e in t for e in EMOJI_ANX):
        scores["anxiety"] += 1.0
        hits["anxiety"].append("emoji:anx")
    if any(e in t for e in EMOJI_ANGER):
        scores["anger"] += 1.0
        hits["anger"].append("emoji:anger")

    # If loneliness keywords show up strongly but sadness is low, boost sadness slightly
    if any(k in t for k in ["lonely", "alone", "isolated", "eklo", "eklai"]):
        scores["sadness"] += 0.4
        hits["sadness"].append("hint:loneliness->sadness")

    return scores, hits


# ---------------------------- Crisis detection ----------------------------

@dataclass
class RiskResult:
    level: str  # "none" | "low" | "medium" | "high"
    score: int  # 0-10
    reasons: List[str]

def detect_risk(text: str) -> RiskResult:
    t = _normalize(text)

    # negation hints reduce false positives
    for ph in CRISIS_NEGATION_HINTS:
        if ph in t:
            return RiskResult(level="low", score=2, reasons=[f'negation:"{ph}"'])

    reasons: List[str] = []

    high = any(ph in t for ph in CRISIS_HIGH_PHRASES)
    med = any(ph in t for ph in CRISIS_MED_PHRASES)

    # also detect "plan-ish" words
    plan_words = ["plan", "method", "rope", "knife", "pills", "poison", "bridge", "jump", "hang"]
    plan = any(w in t for w in plan_words)

    if high:
        reasons.append("self-harm/suicide explicit phrase")
    if med:
        reasons.append("passive suicidal ideation/hopelessness phrase")
    if plan:
        reasons.append("possible plan/method indicators")

    # scoring
    score = 0
    if med:
        score += 4
    if high:
        score += 7
    if plan and (high or med):
        score += 2

    # clamp
    score = max(0, min(10, score))

    if score >= 8:
        return RiskResult(level="high", score=score, reasons=reasons)
    if score >= 5:
        return RiskResult(level="medium", score=score, reasons=reasons)
    if score >= 2:
        return RiskResult(level="low", score=score, reasons=reasons)
    return RiskResult(level="none", score=0, reasons=[])


# ---------------------------- Public API ----------------------------

@dataclass
class EmotionResult:
    emotion: str          # e.g. "anxiety"
    intensity: int        # 1-5
    confidence: float     # 0-1 (rule-based estimate)
    evidence: List[str]   # matched keywords/phrases
    risk: RiskResult


# ---------------------------- Panic (separate from general anxiety) ----------------------------
# We treat panic as its own emotion because it needs a different response style
# (co-regulation + reassurance before techniques).
PANIC_PHRASES = {
    "can't breathe", "cant breathe", "cannot breathe",
    "i can't breathe", "i cant breathe", "i cannot breathe",
    "short of breath", "breathless",
    "about to faint", "going to faint", "i will faint", "feel like i'm going to faint",
    "feel like i am going to faint", "i'm about to faint", "im about to faint",
    "my heart is racing", "heart racing", "palpitations",
    "chest tight", "chest tightness", "tight chest",
    "panic attack", "having a panic attack", "panicking", "i'm panicking", "im panicking",
    "i feel like i'm dying", "i feel like i am dying",
    "hands are tingling", "tingling", "numb", "shaking", "trembling"
}

_NEGATION_RE = re.compile(
    r"\b("
    r"not|no|never|none|nothing|nowhere|neither|nor|cannot|can't|dont|don't|didnt|didn't|"
    r"wont|won't|isnt|isn't|arent|aren't|wasnt|wasn't|werent|weren't|"
    r"without|hardly|barely|rarely"
    r")\b"
)

def _has_negation(text: str) -> bool:
    """
    Simple negation detector for emotion/risk phrase rules.
    Example: 'I am not panicking' should not trigger panic phrases.
    """
    if not text:
        return False
    return bool(_NEGATION_RE.search(text.lower()))

def detect_emotion(text: str) -> Tuple[str, int, EmotionResult]:
    """
    Main function for LUMORA.

    Returns:
        emotion, intensity, details
    """
    t = _normalize(text)
    risk = detect_risk(t)

    # ✅ Panic override (needs different support than generic anxiety)
    if any(p in t for p in PANIC_PHRASES) and not _has_negation(t):
        intensity = 5 if (
            "can't breathe" in t or "cant breathe" in t
            or "about to faint" in t or "going to faint" in t
        ) else 4

        matched = [p for p in PANIC_PHRASES if p in t][:5]  # short + explainable
        evidence = [f'panic_phrase:"{p}"' for p in matched] or ["panic_phrase"]

        details = EmotionResult(
            emotion="panic",
            intensity=intensity,
            confidence=0.85,
            evidence=evidence,
            risk=risk
        )
        return "panic", intensity, details

    scores, hits = _score_emotions(t)

    # Remove "calm" if there are strong negative emotions
    if scores["calm"] > 0 and max(scores["anxiety"], scores["sadness"], scores["anger"], scores["burnout"]) >= 2.5:
        scores["calm"] -= 0.8
        hits["calm"].append("adjust:calm_reduced_due_to_negative")

    # Choose best emotion (ignore calm unless it's clearly dominant)
    sorted_emotions = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_emo, best_score = sorted_emotions[0]

    # If nothing strongly matched, neutral
    if best_score < 1.0:
        best_emo = "neutral"
        best_score = 0.0

    # intensity mapping: base score + intensity markers
    marker_boost = _count_intensity_markers(text or "")
    raw = best_score + marker_boost

    # If risk is high, bump intensity (because user is distressed)
    if risk.level == "high":
        raw += 1.0
    elif risk.level == "medium":
        raw += 0.5

    # Convert to 1-5
    if best_emo == "neutral":
        intensity = 2
    else:
        if raw < 2.0:
            intensity = 2
        elif raw < 3.5:
            intensity = 3
        elif raw < 5.5:
            intensity = 4
        else:
            intensity = 5

    # confidence estimate: depends on gap between top 2 scores
    second_score = sorted_emotions[1][1] if len(sorted_emotions) > 1 else 0.0
    gap = max(0.0, best_score - second_score)
    confidence = min(1.0, 0.45 + gap * 0.15 + (0.1 if best_score >= 3 else 0.0))

    evidence = hits.get(best_emo, []) if best_emo in hits else []

    details = EmotionResult(
        emotion=best_emo,
        intensity=intensity,
        confidence=confidence,
        evidence=evidence[:12],
        risk=risk
    )
    return best_emo, intensity, details


# Backwards-compatible simple signature (like your current file)
def detect_emotion_simple(text: str) -> Tuple[str, int]:
    emo, intensity, _ = detect_emotion(text)
    return emo, intensity


# ---------------------------- Quick manual test ----------------------------
if __name__ == "__main__":
    tests = [
        "I can't breathe, my heart is racing, I think I'm having a panic attack!!!",
        "malai dherai chinta cha parixa ko lagi, nidra lagdaina",
        "i feel empty and hopeless lately 😢",
        "im angry and i want to break things",
        "i want to die and end my life",
        "i am not suicidal, i just feel sad sometimes",
        "i feel okay today, a bit tired"
    ]
    for s in tests:
        emo, inten, det = detect_emotion(s)
        print("\nTEXT:", s)
        print("EMO:", emo, "INT:", inten, "CONF:", round(det.confidence, 2))
        print("RISK:", det.risk.level, det.risk.score, det.risk.reasons)
        print("EVIDENCE:", det.evidence)