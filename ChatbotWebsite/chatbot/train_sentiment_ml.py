import os
import json
from collections import Counter
import joblib

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression


BASE_DIR = os.path.dirname(__file__)
MODEL_DIR = os.path.join(BASE_DIR, "models")
DATA_PATH = os.path.join(BASE_DIR, "..", "static", "data", "intents.json")
os.makedirs(MODEL_DIR, exist_ok=True)

# --------- auto tag mapping (keyword based) ----------
POS_KEYS = {"happy", "joy", "smile", "love", "great", "good", "excellent", "awesome", "gratitude", "proud", "relief", "calm"}
NEG_KEYS = {"sad", "angry", "mad", "depress", "lonely", "stress", "anx", "panic", "fear", "tired", "hopeless", "cry", "hurt", "upset", "suic"}
NEU_KEYS = {"greet", "hello", "hi", "bye", "goodbye", "thanks", "thank", "intro", "name", "help", "menu", "options", "what", "who"}


def tag_to_sentiment(tag: str) -> str:
    """
    Map an intent tag -> sentiment label using simple keyword rules.
    Neutral rules are checked FIRST to avoid 'goodbye' accidentally matching 'good'.
    """
    t = tag.lower().strip()

    # explicit neutral first (prevents "goodbye" -> positive via "good")
    if "goodbye" in t or t in {"bye", "bye_bye"}:
        return "neutral"

    if any(k in t for k in NEU_KEYS):
        return "neutral"
    if any(k in t for k in POS_KEYS):
        return "positive"
    if any(k in t for k in NEG_KEYS):
        return "negative"

    return "neutral"


def load_data(path: str):
    """
    Load intents.json and convert patterns into X(texts), y(labels).
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    X, y = [], []
    tag_counts = Counter()
    tag_label_map = {}

    for intent in data.get("intents", []):
        tag = (intent.get("tag") or "").strip()
        if not tag:
            continue

        label = tag_to_sentiment(tag)
        tag_label_map[tag] = label
        tag_counts[tag] += 1

        for p in intent.get("patterns", []):
            p = (p or "").strip()
            if not p:
                continue
            X.append(p)
            y.append(label)

    print("✅ intents.json loaded from:", path)
    print("Tags found:", len(tag_counts))
    print("Label distribution:", dict(Counter(y)))
    print("Sample tag→label:", list(tag_label_map.items())[:15])

    return X, y


def boost_positive_class(X, y, min_positive: int = 150):
    """
    Your intents.json is heavily neutral. This adds small safe positive samples so the ML model
    doesn't become 'always neutral'. This is simple augmentation suitable for academic demo.
    """
    current_pos = y.count("positive")
    if current_pos >= min_positive:
        return X, y

    extra_positive = [
        "I feel happy today",
        "I am doing great",
        "I feel calm and relaxed",
        "I am proud of myself",
        "I feel hopeful",
        "Things are getting better",
        "I feel motivated",
        "I am grateful today",
        "I feel good about my progress",
        "I feel strong and confident",
        "I am feeling much better now",
        "I am excited about today",
        "I feel relaxed and safe",
        "I feel positive and energized",
        "I am satisfied with my work",
    ]

    # replicate variations until we reach min_positive
    i = 0
    while y.count("positive") < min_positive:
        s = extra_positive[i % len(extra_positive)]
        X.extend([s, s + "!", "Really " + s.lower()])
        y.extend(["positive", "positive", "positive"])
        i += 1

    print(f"✅ Boosted positive samples: {current_pos} -> {y.count('positive')}")
    print("New label distribution:", dict(Counter(y)))
    return X, y


def main():
    X, y = load_data(DATA_PATH)

    # Ensure we have at least 2 classes
    classes = sorted(set(y))
    if len(classes) < 2:
        raise ValueError(
            f"Need at least 2 classes, got {classes}. "
            "Add more emotion intents or adjust mapping keywords."
        )

    # Optional (recommended): reduce extreme imbalance
    X, y = boost_positive_class(X, y, min_positive=150)

    tfidf = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=8000,
        stop_words="english"
    )
    X_vec = tfidf.fit_transform(X)

    clf = LogisticRegression(
        max_iter=300,
        class_weight="balanced"
    )
    clf.fit(X_vec, y)

    joblib.dump(tfidf, os.path.join(MODEL_DIR, "tfidf.joblib"))
    joblib.dump(clf, os.path.join(MODEL_DIR, "lr_sentiment.joblib"))

    print("✅ Trained Logistic Regression sentiment model")
    print("Classes:", clf.classes_)
    print("Saved to:", MODEL_DIR)


if __name__ == "__main__":
    main()
