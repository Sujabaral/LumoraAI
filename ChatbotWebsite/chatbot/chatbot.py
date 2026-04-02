# ChatbotWebsite/chatbot/chatbot.py
from __future__ import annotations

import os
import re
import pickle
import random
from typing import Optional, List, Tuple, Dict, Any

import numpy as np
import nltk
from nltk.stem import WordNetLemmatizer
import tensorflow as tf

from scipy.sparse import hstack

# ✅ IMPORTANT: match training history source (used for DB history fetch; hybrid may use it)
from ChatbotWebsite.models import ChatMessage


# =========================================================
# Paths (match training script)
# =========================================================
OUT_DIR = "ChatbotWebsite/static/data"
MODEL_PATH_KERAS = os.path.join(OUT_DIR, "chatbot-model.keras")
MODEL_PATH_H5 = os.path.join(OUT_DIR, "chatbot-model.h5")
META_PATH = os.path.join(OUT_DIR, "chatbot_meta.pkl")


# =========================================================
# NLTK setup (download only if missing)
# =========================================================
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


# =========================================================
# Meta + globals
# =========================================================
meta: Dict[str, Any] = {}
word_vectorizer = None
char_vectorizer = None
label_enc = None
responses_map: Dict[str, List[str]] = {}

# Defaults (kept for backward compatibility; hybrid can still use history_last_n)
N_HISTORY = 10
HISTORY_K = 6
HISTORY_FEATURE_NAMES: List[str] = [
    "hist_count", "avg_tokens", "max_tokens", "min_tokens", "std_tokens", "last_tokens"
]

USE_CORE_INTENTS = False
CORE_MAP: Dict[str, str] = {}

# If any of these ever leak into labels, we refuse them (let hybrid do Brain/Mistral)
SKIP_LABELS = {
    "mistral",
    "mistral_direct",
    "brain+mistral",
    "rule_greeting",
    "rule_short",
    "rule_uncertainty",
}

try:
    with open(META_PATH, "rb") as f:
        meta = pickle.load(f)

    # ✅ NEW: trainer saves word_vectorizer + char_vectorizer
    word_vectorizer = meta.get("word_vectorizer")
    char_vectorizer = meta.get("char_vectorizer")
    label_enc = meta.get("label_encoder")

    # Optional (if present)
    responses_map = meta.get("responses_map", {}) or {}

    # Backward-compatible fields (may not exist in new trainer meta)
    N_HISTORY = int(meta.get("history_window", N_HISTORY))
    HISTORY_K = int(meta.get("history_k", HISTORY_K))
    HISTORY_FEATURE_NAMES = meta.get("history_feature_names", HISTORY_FEATURE_NAMES) or HISTORY_FEATURE_NAMES

    USE_CORE_INTENTS = bool(meta.get("use_core_intents", False))
    CORE_MAP = meta.get("core_map", {}) or {}

    print("✅ Loaded chatbot_meta.pkl (vectorizers + label encoder).")
    print("   use_core_intents:", USE_CORE_INTENTS)
except Exception as e:
    print(f"⚠️ Could not load metadata '{META_PATH}': {e}")
    meta = {}
    word_vectorizer = None
    char_vectorizer = None
    label_enc = None
    responses_map = {}
    USE_CORE_INTENTS = False
    CORE_MAP = {}


# =========================================================
# Load model
# =========================================================
keras_model = None
keras_available = False


def _pick_model_path() -> str:
    if os.path.exists(MODEL_PATH_KERAS):
        return MODEL_PATH_KERAS
    return MODEL_PATH_H5


try:
    _model_path = _pick_model_path()
    # ✅ compile=False avoids optimizer/TF serialization issues
    keras_model = tf.keras.models.load_model(_model_path, compile=False)
    keras_available = True
    print(f"✅ Keras TF-IDF model loaded successfully: {_model_path}")
except Exception as e:
    keras_model = None
    keras_available = False
    print(f"⚠️ Could not load Keras model: {e}")


# =========================================================
# Tag normalization / core label helpers
# =========================================================
def norm_tag(tag: str) -> str:
    return (tag or "").strip().lower()


def to_core_label(tag: str) -> str:
    """
    If core intents were enabled during training, label_enc already contains core labels.
    But this function safely maps legacy tags -> core labels if ever needed.
    """
    t = norm_tag(tag)
    if not USE_CORE_INTENTS:
        return t
    return CORE_MAP.get(t, t)


# =========================================================
# Text cleaning (safe for Nepali + Roman Nepali)
# =========================================================
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

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")  # Nepali/Hindi block


def clean_text(text: str) -> str:
    """
    Important:
    - Do NOT strip Nepali characters.
    - WordNet lemmatizer is English-only, so apply it only to ASCII tokens.
    """
    text = (text or "").strip().lower()
    if not text:
        return ""

    # English contractions (harmless for Nepali too)
    for pat, rep in _CONTRACTIONS:
        text = re.sub(pat, rep, text)

    # Keep: letters/numbers/underscore/space + Devanagari block
    # Remove punctuation/symbols while preserving Nepali script.
    text = re.sub(r"[^\w\s\u0900-\u097F]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    # If Nepali is present, skip English lemmatization (avoid damaging Nepali)
    if _DEVANAGARI_RE.search(text):
        return text

    # English tokenization + lemmatization
    tokens = nltk.word_tokenize(text)
    tokens = [lemmatizer.lemmatize(t) for t in tokens]
    return " ".join(tokens).strip()


# =========================================================
# Feature building (MUST match train_chatbot_highacc_keras.py)
#   X = [word_tfidf] + [char_tfidf]
# =========================================================
def make_features(curr_text: str) -> np.ndarray:
    if word_vectorizer is None or char_vectorizer is None:
        return np.zeros((1, 0), dtype=np.float32)

    xw = word_vectorizer.transform([curr_text]).astype("float32")
    xc = char_vectorizer.transform([curr_text]).astype("float32")
    x = hstack([xw, xc]).toarray().astype("float32")
    return x


# =========================================================
# History retrieval (still useful for hybrid context; not used in TF-IDF features now)
# =========================================================
def _fetch_history_texts(
    *,
    user_id: Optional[int],
    session_id: Optional[int],
    limit: int
) -> List[str]:
    """
    Returns cleaned last N user messages in chronological order.
    Uses ChatMessage by session_id.
    Safe: if no app context / DB not ready -> return [].
    """
    if session_id is None:
        return []

    try:
        rows = (
            ChatMessage.query
            .filter_by(session_id=session_id, role="user")
            .order_by(ChatMessage.timestamp.desc())
            .limit(limit)
            .all()
        )
    except Exception:
        return []

    hist: List[str] = []
    for m in reversed(rows):
        t = clean_text(getattr(m, "message", "") or "")
        if t:
            hist.append(t)
    return hist


# =========================================================
# Intent prediction (TF-IDF) - production gating
# =========================================================
def predict_class(
    message: str,
    *,
    user_id: Optional[int] = None,
    session_id: Optional[int] = None,
    prob_threshold: float = 0.60,
    margin_threshold: float = 0.15,
    top_k: int = 3,
) -> List[Tuple[str, float]]:
    """
    Returns list of (intent_tag, probability) sorted desc.

    If not confident -> return [] so hybrid pipeline uses Brain/Mistral.
    """
    if (not keras_available) or (keras_model is None) or (word_vectorizer is None) or (char_vectorizer is None) or (label_enc is None):
        return []

    curr = clean_text(message)
    if not curr:
        return []

    x = make_features(curr)

    expected = int(keras_model.input_shape[-1])
    got = int(x.shape[1])
    if got != expected:
        raise ValueError(
            f"Feature mismatch: expected {expected}, got {got}. "
            f"Check chatbot_meta.pkl + chatbot-model are from same training run "
            f"and make_features/clean_text match training."
        )

    probs = keras_model.predict(x, verbose=0)[0]
    order = np.argsort(probs)[::-1]

    top1_i = int(order[0])
    top1_p = float(probs[top1_i])
    top2_p = float(probs[int(order[1])]) if len(order) > 1 else 0.0
    margin = top1_p - top2_p

    # gating
    if top1_p < prob_threshold or margin < margin_threshold:
        return []

    out: List[Tuple[str, float]] = []
    for i in order[:max(1, top_k)]:
        tag = str(label_enc.classes_[int(i)])
        tag = to_core_label(tag)  # safe even if already core
        if norm_tag(tag) in SKIP_LABELS:
            continue
        out.append((tag, float(probs[int(i)])))

    return out if out else []


# =========================================================
# Response selection helper (canned replies)
# =========================================================
def pick_response(tag: str) -> Optional[str]:
    """
    Pick a canned response from responses_map for predicted tag.
    With core intents enabled, tag should already be core.
    """
    t = to_core_label(tag)
    t = norm_tag(t)
    if t in SKIP_LABELS:
        return None

    pool = responses_map.get(t) or []
    if not pool:
        return None
    return random.choice(pool)


# =========================================================
# Main entrypoint used by routes (delegates to chatbot_logic)
# =========================================================
def get_chatbot_reply(
    user_id: Optional[int],
    session_id: Optional[int],
    user_message: str,
    history_last_n: Optional[List[str]] = None,
) -> str:
    """
    Returns assistant message as a JSON string:
      {"text": "...", "meta": {...}}

    Delegates to chatbot_logic.get_hybrid_response (single source of truth).
    """
    import json as _json
    from ChatbotWebsite.chatbot.chatbot_logic import get_hybrid_response

    user_message = (user_message or "").strip()
    if not user_message:
        return _json.dumps({"text": "Tell me what’s on your mind — I’m here.", "meta": {"risk_level": "low"}})

    # Keep passing history_last_n if your routes provide it.
    result = get_hybrid_response(
        user_message=user_message,
        user_id=user_id if user_id is not None else "anon",
        session_id=session_id,
        history_last_n=history_last_n,
    )

    text = result.get("text") or "I’m here with you."
    meta_out = result.get("meta") or {}
    meta_out["source"] = result.get("source")
    meta_out["crisis"] = bool(result.get("crisis", False))

    return _json.dumps({"text": text, "meta": meta_out})