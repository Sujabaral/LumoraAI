# train_baseline.py
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC
from sklearn.metrics import accuracy_score, classification_report

SEED = 42
TEST_SIZE = 0.2

# ✅ Use recent augmented dataset
INTENTS_PATH = "ChatbotWebsite/static/data/intents_augmented.json"


def load_intents_texts_labels(intents_path: str) -> tuple[list[str], list[str]]:
    """
    Loads texts + labels from intents JSON.

    Supported JSON shapes:
      A) {"intents":[{"tag":"...", "patterns":[...]}]}
      B) [{"tag":"...", "patterns":[...]}]
    """
    p = Path(intents_path)
    if not p.exists():
        raise FileNotFoundError(f"INTENTS_PATH not found: {p.resolve()}")

    with p.open("r", encoding="utf-8") as f:
        obj = json.load(f)

    intents = obj.get("intents") if isinstance(obj, dict) else obj
    if not isinstance(intents, list):
        raise ValueError("Invalid intents file format: expected list or {'intents': [...]}")

    texts: list[str] = []
    labels: list[str] = []

    for it in intents:
        tag = it.get("tag") or it.get("intent") or it.get("name")
        patterns = it.get("patterns") or it.get("examples") or it.get("texts")

        if not tag or not patterns:
            continue

        for pat in patterns:
            if not isinstance(pat, str):
                continue
            t = pat.strip()
            if not t:
                continue
            texts.append(t)
            labels.append(tag)

    if not texts:
        raise ValueError("No training samples found in intents file (patterns empty).")

    return texts, labels


def main():
    texts, labels = load_intents_texts_labels(INTENTS_PATH)

    print("\nDATASET CHECK (Baseline)")
    print("INTENTS_PATH:", INTENTS_PATH)
    print("Total samples:", len(texts))
    print("Unique labels:", len(set(labels)))
    print("Top label counts:", Counter(labels).most_common(8))

    X_train, X_val, y_train, y_val = train_test_split(
        texts,
        labels,
        test_size=TEST_SIZE,
        random_state=SEED,
        stratify=labels,
    )

    nb = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=8000,
            ngram_range=(1, 2),
            min_df=2,
            sublinear_tf=True
        )),
        ("clf", MultinomialNB())
    ])
    nb.fit(X_train, y_train)
    pred_nb = nb.predict(X_val)
    print("\n=== Naive Bayes (TF-IDF) ===")
    print("Accuracy:", accuracy_score(y_val, pred_nb))
    print(classification_report(y_val, pred_nb, digits=3, zero_division=0))

    svm = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=8000,
            ngram_range=(1, 2),
            min_df=2,
            sublinear_tf=True
        )),
        ("clf", LinearSVC())
    ])
    svm.fit(X_train, y_train)
    pred_svm = svm.predict(X_val)
    print("\n=== Linear SVM (TF-IDF) ===")
    print("Accuracy:", accuracy_score(y_val, pred_svm))
    print(classification_report(y_val, pred_svm, digits=3, zero_division=0))


if __name__ == "__main__":
    main()