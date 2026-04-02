# dataset_builder.py
from __future__ import annotations

import os, json, random, re
from typing import List, Dict, Any
from collections import defaultdict

import numpy as np
import nltk
from nltk.stem import WordNetLemmatizer

# ---- config (match train_chatbot.py) ----
SEED = 42
INTENTS_PATH = "ChatbotWebsite/static/data/intents.json"
N_HISTORY = 10
INTENTS_REPEAT = 1
DB_REPEAT = 10
USE_CORE_INTENTS = True
INTENTS_CAP_PER_LABEL = 150
INTENTS_MIN_PER_LABEL = 40
SKIP_LABELS = {
    "mistral", "mistral_direct", "brain+mistral",
    "rule_greeting", "rule_short", "rule_uncertainty",
}

# ---- NLTK ----
def _ensure_nltk():
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt")
    try:
        nltk.data.find("corpora/wordnet")
    except LookupError:
        nltk.download("wordnet")

_ensure_nltk()
lemmatizer = WordNetLemmatizer()

# ---- helpers copied from your trainer ----
def norm_tag(tag: str) -> str:
    return (tag or "").strip().lower()

CORE_MAP: Dict[str, str] = {
    "greeting": "greeting",
    "goodbye": "goodbye",
    "thanks": "thanks",
    "general": "general",
    "fun": "fun",
    "jokes": "fun",
    "anxiety": "anxiety",
    "panic_attack": "anxiety",
    "stress": "stress",
    "procrastination": "stress",
    "anger": "anger",
    "sadness": "depression",
    "depression_definition": "depression",
    "depression_feeling": "depression",
    "depression_help": "depression",
    "loneliness_definition": "loneliness",
    "loneliness_feeling": "loneliness",
    "loneliness_help": "loneliness",
    "relationship_issues": "relationship",
    "crisis": "crisis",
    "suicidal": "crisis",
    "immediate_danger": "crisis",
    "coping_skills": "coping",
    "breathing_exercises": "coping",
    "mindfulness_grounding": "coping",
    "sleep_issues": "sleep",
    "journaling": "journaling",
    "professional_help": "professional_help",
    "services_nepal": "professional_help",
    "book_appointment": "professional_help",
    "addiction_definition": "addiction",
    "addiction_help": "addiction",
    "addiction_signs": "addiction",
    "bipolar_definition": "bipolar",
    "ocd_definition": "ocd",
    "ptsd_definition": "ptsd",
    "schizophrenia_definition": "schizophrenia",
    "borderline_personality_disorder": "personality",
    "psychosis_general": "psychosis",
    "eating_disorders": "eating_disorders",
    "cultural_mental_health": "culture",
    "racism_mental_health": "culture",
    "motivation_goals": "motivation",
}

def _heuristic_core(t: str) -> str:
    if "addiction" in t: return "addiction"
    if "bipolar" in t: return "bipolar"
    if "ocd" in t: return "ocd"
    if "ptsd" in t: return "ptsd"
    if "schizophrenia" in t: return "schizophrenia"
    if "psychosis" in t: return "psychosis"
    if "eating" in t: return "eating_disorders"
    if "culture" in t or "racism" in t: return "culture"
    if "motivation" in t or "goal" in t: return "motivation"
    if "anger" in t: return "anger"
    return "general"

def to_label(tag: str) -> str:
    t = norm_tag(tag)
    if not USE_CORE_INTENTS:
        return t
    if t in CORE_MAP:
        return CORE_MAP[t]
    return _heuristic_core(t)

_CONTRACTIONS = [
    (r"can't", "can not"),
    (r"won't", "will not"),
    (r"n't", " not"),
    (r"'re", " are"),
    (r"'s", " is"),
    (r"'m", " am"),
    (r"'ll", " will"),
    (r"'ve", " have"),
]
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_MULTI_SPACE = re.compile(r"\s+")

def clean_text(text: str) -> str:
    text = (text or "").lower().strip()
    for pat, rep in _CONTRACTIONS:
        text = re.sub(pat, rep, text)
    text = _NON_ALNUM.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text).strip()
    if not text:
        return ""
    tokens = nltk.word_tokenize(text)
    tokens = [lemmatizer.lemmatize(t) for t in tokens]
    return " ".join(tokens).strip()

def should_skip_message(raw: str) -> bool:
    if not raw:
        return True
    low = raw.strip().lower()
    if low.startswith("(guidance)") or low.startswith("error:") or low.startswith("sorry,"):
        return True
    if "couldn't process that message" in low:
        return True
    if "gemini couldn’t process" in low or "gemini couldn't process" in low:
        return True
    return False

def balance_patterns(pats_by_label: Dict[str, List[str]]) -> Dict[str, List[str]]:
    rng = random.Random(SEED)
    out = {}
    for label, pats in pats_by_label.items():
        pats = list(pats)
        rng.shuffle(pats)
        if len(pats) > INTENTS_CAP_PER_LABEL:
            pats = pats[:INTENTS_CAP_PER_LABEL]
        if 0 < len(pats) < INTENTS_MIN_PER_LABEL:
            need = INTENTS_MIN_PER_LABEL - len(pats)
            pats = pats + [rng.choice(pats) for _ in range(need)]
        out[label] = pats
    return out

def build_texts_labels() -> tuple[list[str], list[str]]:
    if not os.path.exists(INTENTS_PATH):
        raise FileNotFoundError(f"Missing intents.json at: {INTENTS_PATH}")

    with open(INTENTS_PATH, "r", encoding="utf-8") as f:
        intents = json.load(f)
    intents_list = intents.get("intents", []) or []

    patterns_by_label: Dict[str, List[str]] = defaultdict(list)

    for it in intents_list:
        raw_tag = it.get("tag")
        if not raw_tag:
            continue
        label = to_label(raw_tag)
        if norm_tag(raw_tag) in SKIP_LABELS or label in SKIP_LABELS:
            continue
        for p in (it.get("patterns") or []):
            t = clean_text(p)
            if t:
                patterns_by_label[label].append(t)

    patterns_by_label = balance_patterns(patterns_by_label)

    # ✅ DB labeled messages
    from train_app_min import create_train_app
    from ChatbotWebsite.models import ChatMessage

    app = create_train_app()
    samples: List[Dict[str, Any]] = []

    # A) intents patterns
    for label, pats in patterns_by_label.items():
        for t in pats:
            for _ in range(INTENTS_REPEAT):
                samples.append({"text": t, "label": label})

    # B) DB messages
    with app.app_context():
        msgs = (
            ChatMessage.query
            .filter(ChatMessage.session_id.isnot(None))
            .order_by(ChatMessage.session_id.asc(), ChatMessage.timestamp.asc())
            .all()
        )
        for m in msgs:
            if getattr(m, "role", None) != "user":
                continue
            label_raw = getattr(m, "intent_tag", None)
            if not label_raw:
                continue
            raw_norm = norm_tag(label_raw)
            label = to_label(label_raw)
            if raw_norm in SKIP_LABELS or label in SKIP_LABELS:
                continue
            raw_msg = (getattr(m, "message", "") or "").strip()
            if should_skip_message(raw_msg):
                continue
            curr_text = clean_text(raw_msg)
            if not curr_text:
                continue
            for _ in range(DB_REPEAT):
                samples.append({"text": curr_text, "label": label})

    texts = [s["text"] for s in samples]
    labels = [s["label"] for s in samples]
    return texts, labels