# ChatbotWebsite/chatbot/sentiment.py
from __future__ import annotations

import os
import joblib
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

BASE_DIR = os.path.dirname(__file__)
MODEL_DIR = os.path.join(BASE_DIR, "models")

TFIDF_PATH = os.path.join(MODEL_DIR, "tfidf.joblib")
LR_PATH = os.path.join(MODEL_DIR, "lr_sentiment.joblib")

_analyzer = SentimentIntensityAnalyzer()
_tfidf = None
_lr = None


def _models_available() -> bool:
    return os.path.exists(TFIDF_PATH) and os.path.exists(LR_PATH)


def _load_models() -> bool:
    """
    Loads TF-IDF + LR models if available.
    Returns True if loaded, False if not available.
    """
    global _tfidf, _lr
    if _tfidf is not None and _lr is not None:
        return True

    if not _models_available():
        return False

    _tfidf = joblib.load(TFIDF_PATH)
    _lr = joblib.load(LR_PATH)
    return True


def _normalize_01_from_minus1_1(x: float) -> float:
    # [-1, +1] -> [0, 1]
    return (x + 1.0) / 2.0


def analyze_sentiment(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {
            "vader_score": 0.0,
            "ml_prob": {},
            "final_score": 0.5,
            "label": "neutral",
            "confidence": 0.0,
            "top_tokens": [],
        }

    # -------------------
    # 1) VADER
    # -------------------
    v = _analyzer.polarity_scores(text)
    vader_compound = float(v["compound"])           # [-1..1]
    vader_norm = _normalize_01_from_minus1_1(vader_compound)  # [0..1]
    vader_strength = abs(vader_compound)            # [0..1]

    # -------------------
    # 2) ML (TFIDF + LR) if available
    # -------------------
    loaded = _load_models()
    ml_prob = {}
    ml_norm = 0.5
    ml_conf = 0.0
    top_tokens = []

    if loaded:
        X = _tfidf.transform([text])

        proba = _lr.predict_proba(X)[0]
        classes = list(_lr.classes_)
        ml_prob = {classes[i]: float(proba[i]) for i in range(len(classes))}
        ml_conf = float(max(ml_prob.values())) if ml_prob else 0.0

        p_pos = ml_prob.get("positive", 0.0)
        p_neg = ml_prob.get("negative", 0.0)

        # Convert ML probs into a sentiment score in [-1..1], then normalize to [0..1]
        ml_raw = float(p_pos - p_neg)               # [-1..1] approx
        ml_norm = _normalize_01_from_minus1_1(ml_raw)

        # Explain tokens (top TF-IDF features for this text)
        try:
            feature_names = _tfidf.get_feature_names_out()
            row = X.tocoo()
            pairs = sorted(
                [(feature_names[j], val) for j, val in zip(row.col, row.data)],
                key=lambda x: x[1],
                reverse=True
            )
            top_tokens = [t for t, _ in pairs[:8]]
        except Exception:
            top_tokens = []
    else:
        # If ML missing, we still provide a stable structure
        ml_prob = {}
        ml_norm = 0.5
        ml_conf = 0.0
        top_tokens = []

    # -------------------
    # 3) Hybrid fusion (report-friendly rule)
    # final = 0.6 * ML + 0.4 * VADER
    # -------------------
    final = 0.6 * ml_norm + 0.4 * vader_norm

    # -------------------
    # 4) Label from final
    # -------------------
    if final >= 0.60:
        label = "positive"
    elif final <= 0.40:
        label = "negative"
    else:
        label = "neutral"

    # -------------------
    # 5) Confidence (simple hybrid)
    # -------------------
    confidence = 0.6 * ml_conf + 0.4 * vader_strength

    return {
        "vader_score": vader_compound,
        "ml_prob": ml_prob,
        "final_score": float(final),
        "label": label,
        "confidence": float(confidence),
        "top_tokens": top_tokens,
    }
