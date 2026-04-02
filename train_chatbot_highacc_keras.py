# train_chatbot_highacc_keras.py
# --------------------------------------------------------------------------------------------
# HIGH-ACCURACY KERAS INTENT TRAINER (keeps full intent set; improves separability)
#  - Uses cleaned intents file (deduplicated across intents)
#  - Word TF-IDF + Char TF-IDF (handles typos/roman Nepali variations)
#  - Stronger Dense head with BatchNorm + Dropout
#  - Class weights + label smoothing
#  - Saves model + meta + curves
# --------------------------------------------------------------------------------------------

from __future__ import annotations

import os, json, pickle, random, re
from typing import List, Tuple
from collections import Counter

import numpy as np

import tensorflow as tf
from tensorflow.keras import layers
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau

# M1/M2 optimizer slowdown workaround (safe on Intel too)
try:
    from tensorflow.keras.optimizers.legacy import Adam as AdamOpt
except Exception:
    from tensorflow.keras.optimizers import Adam as AdamOpt

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.utils.class_weight import compute_class_weight
from scipy.sparse import hstack

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

# ---------------- Paths ----------------
# Put this file at project root and run: python train_chatbot_highacc_keras.py
INTENTS_PATH = "ChatbotWebsite/static/data/intents_augmented.json"  # <-- use cleaned file
OUT_DIR = "ChatbotWebsite/static/data"
os.makedirs(OUT_DIR, exist_ok=True)

MODEL_PATH = os.path.join(OUT_DIR, "chatbot-model.keras")
META_PATH  = os.path.join(OUT_DIR, "chatbot_meta.pkl")
ACC_PNG    = os.path.join(OUT_DIR, "accuracy_curve.png")
LOSS_PNG   = os.path.join(OUT_DIR, "loss_curve.png")

# ---------------- TF-IDF ----------------
WORD_MAX_FEATURES = 25000
CHAR_MAX_FEATURES = 15000

word_vec = TfidfVectorizer(
    lowercase=True,
    strip_accents="unicode",
    ngram_range=(1, 2),
    min_df=2,
    max_df=0.95,
    sublinear_tf=True,
    max_features=WORD_MAX_FEATURES,
)

char_vec = TfidfVectorizer(
    analyzer="char_wb",
    ngram_range=(3, 5),
    min_df=2,
    max_df=0.98,
    sublinear_tf=True,
    max_features=CHAR_MAX_FEATURES,
)

# ---------------- Training ----------------
EPOCHS = 60
BATCH_SIZE = 32
LR = 8e-4
LABEL_SMOOTH = 0.05


def _norm_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def load_intents(path: str) -> Tuple[List[str], List[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    texts, labels = [], []
    for intent in data.get("intents", []):
        tag = (intent.get("tag") or "").strip().lower()
        for p in intent.get("patterns", []) or []:
            t = _norm_text(p).lower()
            if len(t) < 2:
                continue
            texts.append(t)
            labels.append(tag)
    return texts, labels


def main():
    texts, labels = load_intents(INTENTS_PATH)
    print(f"Loaded {len(texts)} samples across {len(set(labels))} intents")

    le = LabelEncoder()
    y = le.fit_transform(labels)

    # Stratified split (prevents class collapse)
    X_train_txt, X_val_txt, y_train, y_val = train_test_split(
        texts, y, test_size=0.20, random_state=SEED, stratify=y
    )

    Xw_train = word_vec.fit_transform(X_train_txt)
    Xc_train = char_vec.fit_transform(X_train_txt)
    X_train = hstack([Xw_train, Xc_train]).astype(np.float32)

    Xw_val = word_vec.transform(X_val_txt)
    Xc_val = char_vec.transform(X_val_txt)
    X_val = hstack([Xw_val, Xc_val]).astype(np.float32)

    # Keras dense expects dense arrays. If memory is tight, reduce MAX_FEATURES.
    X_train = X_train.toarray()
    X_val = X_val.toarray()

    num_classes = len(le.classes_)
    y_train_oh = tf.keras.utils.to_categorical(y_train, num_classes=num_classes)
    y_val_oh   = tf.keras.utils.to_categorical(y_val,   num_classes=num_classes)

    # Class weights (helps rare intents)
    classes = np.unique(y_train)
    weights = compute_class_weight(class_weight="balanced", classes=classes, y=y_train)
    class_weight = {int(c): float(w) for c, w in zip(classes, weights)}

    # Stronger dense head
    model = tf.keras.Sequential([
        layers.Input(shape=(X_train.shape[1],)),
        layers.Dense(1024, activation="relu"),
        layers.BatchNormalization(),
        layers.Dropout(0.45),
        layers.Dense(512, activation="relu"),
        layers.BatchNormalization(),
        layers.Dropout(0.35),
        layers.Dense(num_classes, activation="softmax"),
    ])

    loss_fn = tf.keras.losses.CategoricalCrossentropy(label_smoothing=LABEL_SMOOTH)

    model.compile(
        optimizer=AdamOpt(learning_rate=LR),
        loss=loss_fn,
        metrics=["accuracy"]
    )

    callbacks = [
        EarlyStopping(monitor="val_accuracy", patience=8, restore_best_weights=True),
        ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3, min_lr=1e-5),
    ]

    hist = model.fit(
        X_train, y_train_oh,
        validation_data=(X_val, y_val_oh),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        class_weight=class_weight,
        callbacks=callbacks,
        verbose=1
    )

    # Evaluate
    val_probs = model.predict(X_val, verbose=0)
    y_pred = np.argmax(val_probs, axis=1)
    val_acc = accuracy_score(y_val, y_pred)
    print("\nValidation Accuracy:", round(val_acc * 100, 2), "%\n")

    print("Classification Report:\n")
    print(classification_report(y_val, y_pred, target_names=le.classes_))

    print("Confusion Matrix:\n")
    print(confusion_matrix(y_val, y_pred))

    # Save artifacts
    model.save(MODEL_PATH)
    with open(META_PATH, "wb") as f:
        pickle.dump({
            "label_encoder": le,
            "word_vectorizer": word_vec,
            "char_vectorizer": char_vec,
        }, f)

    # Curves
    import matplotlib.pyplot as plt
    plt.figure(figsize=(8,5))
    plt.plot(hist.history["accuracy"], label="Train Accuracy")
    plt.plot(hist.history["val_accuracy"], label="Val Accuracy")
    plt.title("Intent Classification Accuracy")
    plt.xlabel("Epoch"); plt.ylabel("Accuracy"); plt.legend()
    plt.tight_layout(); plt.savefig(ACC_PNG); plt.close()

    plt.figure(figsize=(8,5))
    plt.plot(hist.history["loss"], label="Train Loss")
    plt.plot(hist.history["val_loss"], label="Val Loss")
    plt.title("Intent Classification Loss")
    plt.xlabel("Epoch"); plt.ylabel("Loss"); plt.legend()
    plt.tight_layout(); plt.savefig(LOSS_PNG); plt.close()

    print("\nSaved:")
    print(" -", MODEL_PATH)
    print(" -", META_PATH)
    print(" -", ACC_PNG)
    print(" -", LOSS_PNG)


if __name__ == "__main__":
    main()
